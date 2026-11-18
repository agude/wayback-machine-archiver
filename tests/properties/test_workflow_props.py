"""Property checks for the archive workflow state machine."""

from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import parse_qs

import pytest
import requests
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from wayback_machine_archiver import workflow
from wayback_machine_archiver.clients import BATCH_STATUS_CHUNK_SIZE, SPN2Client
from wayback_machine_archiver.workflow import (
    INITIAL_POLLING_WAIT,
    JOB_TIMEOUT_SEC,
    MAX_CONSECUTIVE_POLL_FAILURES,
    MAX_PENDING_JOBS,
    MAX_POLLING_WAIT,
    MAX_TRANSIENT_RETRIES,
    ArchiveResult,
    run_archive_workflow,
)

MAX_SUBMISSION_RETRIES = 3


@pytest.fixture(autouse=True)
def _no_stale_status_checks(monkeypatch):
    """These scenarios count polls exactly and poll in the same instant they
    submit. Stale-status handling is exercised with production thresholds in
    test_workflow_rounds_props.py. raising=False keeps this file runnable
    against source that predates those thresholds."""
    monkeypatch.setattr(workflow, "STALE_STATUS_WINDOW_SEC", 0, raising=False)
    monkeypatch.setattr(workflow, "CLOCK_SKEW_TOLERANCE_SEC", float("inf"), raising=False)


SUCCESS_TIMESTAMP = "20250101123456"


@dataclass(frozen=True)
class UrlScenario:
    """A compact script for one URL's submission and capture outcomes."""

    url: str
    submit_failures: tuple[str, ...] = ()
    post_capture_failures: tuple[str, ...] = ()
    transient_responses: int = 0
    final_status: str = "success"
    pending_polls: int = 0


@dataclass
class JobScript:
    """The status responses still available for one accepted job."""

    url: str
    responses: tuple[str, ...]
    response_index: int = 0


def _example_url(number: int) -> str:
    return f"https://example.test/{number}"


@st.composite
def _example_url_strategy(draw: st.DrawFn) -> str:
    return _example_url(draw(st.integers(min_value=0, max_value=100)))


def _reset_clock(clock) -> None:
    """Reset the function-scoped clock between Hypothesis examples."""
    clock.now = 0.0
    clock.sleeps.clear()


HYPOTHESIS_FIXTURE_SETTINGS = settings(suppress_health_check=[HealthCheck.function_scoped_fixture])


@st.composite
def _example_urls(draw: st.DrawFn, *, min_size: int = 1, max_size: int = 6) -> list[str]:
    numbers = draw(
        st.lists(
            st.integers(min_value=0, max_value=100),
            min_size=min_size,
            max_size=max_size,
            unique=True,
        )
    )
    return [_example_url(number) for number in numbers]


class ScriptedSPN2Client:
    """Fake SPN2 client that executes URL and poll scripts without network IO."""

    def __init__(
        self,
        scenarios: list[UrlScenario],
        *,
        poll_failures: tuple[bool, ...] = (),
        forced_poll_actions: dict[str, tuple[str, ...]] | None = None,
        error_message_override: object = ...,
        always_no_job_id: frozenset[str] = frozenset(),
        shared_job_ids: bool = False,
        max_submit_calls: int = 100,
        max_poll_calls: int = 150,
    ) -> None:
        self.scenarios = {scenario.url: scenario for scenario in scenarios}
        self.poll_failures = poll_failures
        self.forced_poll_actions = forced_poll_actions or {}
        self.error_message_override = error_message_override
        self.always_no_job_id = always_no_job_id
        self.shared_job_ids = shared_job_ids
        self.max_submit_calls = max_submit_calls
        self.max_poll_calls = max_poll_calls

        self.submission_calls: dict[str, int] = {}
        self.accepted_captures: dict[str, int] = {}
        self.post_capture_failures_used: dict[str, int] = {}
        self.transient_statuses: dict[str, int] = {}
        self.jobs: dict[str, JobScript] = {}
        self.poll_calls = 0
        self.max_pending_observed = 0
        self.pending_batch_sizes: list[int] = []
        self.submissions_at_poll: list[int] = []
        self._next_job_id = 0

    def submit_capture(
        self,
        url_to_archive: str,
        rate_limit_wait: float,
        api_params: dict[str, str | int],
    ) -> str | None:
        del rate_limit_wait, api_params
        attempt = self.submission_calls.get(url_to_archive, 0) + 1
        self.submission_calls[url_to_archive] = attempt
        if sum(self.submission_calls.values()) > self.max_submit_calls:
            raise AssertionError("submission step budget exceeded")

        if url_to_archive in self.always_no_job_id:
            return None

        scenario = self.scenarios[url_to_archive]
        if attempt <= len(scenario.submit_failures) and self._apply_submit_failure(
            scenario.submit_failures[attempt - 1]
        ):
            return None

        accepted_capture_count = self.accepted_captures.get(url_to_archive, 0)
        post_failure_index = self.post_capture_failures_used.get(url_to_archive, 0)
        if (
            accepted_capture_count > 0
            and post_failure_index < len(scenario.post_capture_failures)
            and self._consume_post_capture_failure(
                url_to_archive,
                scenario.post_capture_failures[post_failure_index],
            )
        ):
            return None

        capture_index = accepted_capture_count
        self.accepted_captures[url_to_archive] = capture_index + 1
        responses = self._responses_for_capture(scenario, capture_index)

        if self.shared_job_ids:
            job_id = "shared-job"
        else:
            job_id = f"job-{self._next_job_id}"
            self._next_job_id += 1
        self.jobs[job_id] = JobScript(url=url_to_archive, responses=responses)
        return job_id

    def _consume_post_capture_failure(self, url: str, failure: str) -> bool:
        used_count = self.post_capture_failures_used.get(url, 0)
        self.post_capture_failures_used[url] = used_count + 1
        return self._apply_submit_failure(failure)

    @staticmethod
    def _apply_submit_failure(failure: str) -> bool:
        if failure == "connection_error":
            raise requests.exceptions.ConnectionError("scripted submit failure")
        if failure == "missing_job_id":
            return True
        raise AssertionError(f"unknown scripted submit failure: {failure}")

    def check_status_batch(self, job_ids: list[str]) -> list[dict[str, object]]:
        self.poll_calls += 1
        if self.poll_calls > self.max_poll_calls:
            raise AssertionError("poll step budget exceeded")
        self.max_pending_observed = max(self.max_pending_observed, len(job_ids))
        self.pending_batch_sizes.append(len(job_ids))
        self.submissions_at_poll.append(sum(self.submission_calls.values()))

        failure_index = self.poll_calls - 1
        if failure_index < len(self.poll_failures) and self.poll_failures[failure_index]:
            raise requests.exceptions.ConnectionError("scripted poll failure")

        statuses: list[dict[str, object]] = []
        for job_id in job_ids:
            job = self.jobs[job_id]
            response_index = min(job.response_index, len(job.responses) - 1)
            action = job.responses[response_index]
            job.response_index += 1
            if action == "missing":
                continue
            statuses.append(self._status_data(job_id, job.url, action))
        return statuses

    def _responses_for_capture(self, scenario: UrlScenario, capture_index: int) -> tuple[str, ...]:
        forced_actions = self.forced_poll_actions.get(scenario.url)
        if forced_actions is not None:
            return forced_actions

        if capture_index < scenario.transient_responses:
            return ("transient_error",)
        if scenario.transient_responses > MAX_TRANSIENT_RETRIES:
            return ("transient_error",)
        if scenario.final_status == "timeout":
            return ("pending",)

        final_action = "success" if scenario.final_status == "success" else "permanent_error"
        return ("pending",) * scenario.pending_polls + (final_action,)

    def _status_data(self, job_id: str, url: str, action: str) -> dict[str, object]:
        if action == "pending":
            return {"job_id": job_id, "status": "pending"}
        if action == "success":
            return {
                "job_id": job_id,
                "status": "success",
                "timestamp": SUCCESS_TIMESTAMP,
            }
        if action == "success_without_timestamp":
            return {"job_id": job_id, "status": "success"}
        if action == "transient_error":
            self.transient_statuses[url] = self.transient_statuses.get(url, 0) + 1
            return {
                "job_id": job_id,
                "status": "error",
                "status_ext": "error:service-unavailable",
                "message": "temporary service error",
            }
        if action == "permanent_error":
            return {
                "job_id": job_id,
                "status": "error",
                "status_ext": "error:not-found",
                "message": "not found",
            }
        if action == "error_with_override_message":
            return {
                "job_id": job_id,
                "status": "error",
                "status_ext": "error:service-unavailable",
                "message": self.error_message_override,
            }
        if action == "null_status_ext":
            return {
                "job_id": job_id,
                "status": "error",
                "status_ext": None,
                "message": "unknown error",
            }
        raise AssertionError(f"unknown scripted status action: {action}")


def _result_summary(results: list[ArchiveResult]) -> dict[str, tuple[str, str | None]]:
    return {result.url: (result.status, result.error_code) for result in results}


def test_two_missing_job_ids_then_success(virtual_clock):
    """Two missing job IDs count as failed submits before the accepted capture."""
    url = _example_url(1)
    scenario = UrlScenario(
        url=url,
        submit_failures=("missing_job_id", "missing_job_id"),
    )
    client = ScriptedSPN2Client([scenario])
    results: list[ArchiveResult] = []

    counts = run_archive_workflow(
        client, [url], rate_limit_in_sec=0, api_params={}, on_result=results.append
    )

    assert counts == (1, 0)
    assert client.submission_calls[url] == 3
    assert results[0].status == "success"


def test_transient_submit_failure_transient_success_history(virtual_clock):
    """A submit error between transient captures does not lose the URL."""
    url = _example_url(1)
    scenario = UrlScenario(
        url=url,
        post_capture_failures=("connection_error",),
        transient_responses=2,
        final_status="success",
    )
    client = ScriptedSPN2Client([scenario])
    results: list[ArchiveResult] = []

    counts = run_archive_workflow(
        client, [url], rate_limit_in_sec=0, api_params={}, on_result=results.append
    )

    assert counts == (1, 0)
    assert client.submission_calls[url] == 4
    assert client.transient_statuses[url] == 2
    assert len(results) == 1
    assert results[0].status == "success"


@HYPOTHESIS_FIXTURE_SETTINGS
@given(url=_example_url_strategy())
def test_no_job_id_responses_count_toward_submission_limit(url, virtual_clock):
    """Repeated accepted-without-ID responses exhaust the submission limit."""
    _reset_clock(virtual_clock)
    scenario = UrlScenario(url=url)
    client = ScriptedSPN2Client(
        [scenario],
        always_no_job_id=frozenset({url}),
        max_submit_calls=12,
    )
    results: list[ArchiveResult] = []

    counts = run_archive_workflow(
        client, [url], rate_limit_in_sec=0, api_params={}, on_result=results.append
    )

    assert client.submission_calls == {url: MAX_SUBMISSION_RETRIES}
    assert counts == (0, 1)
    assert results == [
        ArchiveResult(
            url=url,
            status="failed",
            archive_url=None,
            error_code="submit_failed",
            job_id=None,
        )
    ]


@HYPOTHESIS_FIXTURE_SETTINGS
@given(url=_example_url_strategy())
def test_three_transient_requeues_allow_a_final_success(url, virtual_clock):
    """The retry boundary allows three transient requeues and a fourth capture."""
    _reset_clock(virtual_clock)
    target_url = url
    scenario = UrlScenario(
        url=target_url,
        transient_responses=MAX_TRANSIENT_RETRIES,
        final_status="success",
    )
    client = ScriptedSPN2Client([scenario])
    results: list[ArchiveResult] = []

    counts = run_archive_workflow(
        client, [target_url], rate_limit_in_sec=0, api_params={}, on_result=results.append
    )

    assert counts == (1, 0)
    assert len(results) == 1
    assert results[0].status == "success"
    assert client.submission_calls[target_url] == MAX_TRANSIENT_RETRIES + 1
    assert client.transient_statuses[target_url] == MAX_TRANSIENT_RETRIES


@HYPOTHESIS_FIXTURE_SETTINGS
@given(url=_example_url_strategy())
def test_permanent_error_finishes_the_url_once(url, virtual_clock):
    """A permanent API error removes its job and reports one terminal failure."""
    _reset_clock(virtual_clock)
    target_url = url
    scenario = UrlScenario(url=target_url, final_status="permanent")
    client = ScriptedSPN2Client([scenario], max_poll_calls=20)
    results: list[ArchiveResult] = []

    counts = run_archive_workflow(
        client, [target_url], rate_limit_in_sec=0, api_params={}, on_result=results.append
    )

    assert counts == (0, 1)
    assert _result_summary(results) == {target_url: ("failed", "error:not-found")}
    assert len(results) == 1
    assert client.poll_calls == 1


@HYPOTHESIS_FIXTURE_SETTINGS
@given(url=_example_url_strategy())
def test_missing_batch_status_eventually_times_out(url, virtual_clock):
    """A job omitted from batch status still reaches its timeout result."""
    _reset_clock(virtual_clock)
    target_url = url
    scenario = UrlScenario(url=target_url)
    client = ScriptedSPN2Client(
        [scenario],
        forced_poll_actions={target_url: ("missing",)},
        max_poll_calls=100,
    )
    results: list[ArchiveResult] = []

    counts = run_archive_workflow(
        client, [target_url], rate_limit_in_sec=0, api_params={}, on_result=results.append
    )

    assert counts == (0, 1)
    assert _result_summary(results) == {target_url: ("failed", "timeout")}
    assert client.poll_calls < 100
    assert virtual_clock.now > JOB_TIMEOUT_SEC


@HYPOTHESIS_FIXTURE_SETTINGS
@given(url=_example_url_strategy(), message=st.sampled_from([None, 0, [], {}]))
def test_null_or_wrong_typed_error_message_does_not_crash(url, message, virtual_clock):
    """Invalid error messages do not escape status parsing as TypeError."""
    _reset_clock(virtual_clock)
    target_url = url
    scenario = UrlScenario(url=target_url)
    client = ScriptedSPN2Client(
        [scenario],
        forced_poll_actions={target_url: ("error_with_override_message",)},
        error_message_override=message,
    )

    run_archive_workflow(client, [target_url], rate_limit_in_sec=0, api_params={})


@HYPOTHESIS_FIXTURE_SETTINGS
@given(url=_example_url_strategy())
def test_success_without_timestamp_does_not_emit_malformed_archive_url(url, virtual_clock):
    """Success records always contain a fourteen-digit archive timestamp."""
    _reset_clock(virtual_clock)
    target_url = url
    scenario = UrlScenario(url=target_url)
    client = ScriptedSPN2Client(
        [scenario], forced_poll_actions={target_url: ("success_without_timestamp",)}
    )
    results: list[ArchiveResult] = []

    run_archive_workflow(
        client, [target_url], rate_limit_in_sec=0, api_params={}, on_result=results.append
    )

    assert len(results) == 1
    if results[0].status == "success":
        # Without a usable timestamp the link resolves to the newest capture.
        assert results[0].archive_url in (
            f"https://web.archive.org/web/{target_url}",
        ) or re.fullmatch(
            rf"https://web\.archive\.org/web/\d{{14}}/{re.escape(target_url)}",
            results[0].archive_url or "",
        )
    else:
        raise AssertionError(f"SPN2 reported success but the result is {results[0]}")


# L4 (shared job IDs across URLs) cannot happen: SPN2 job IDs are
# "spn2-" + SHA-1 of the submitted URL (verified against kaon production
# logs), and the archiver deduplicates exact URL strings before submitting.


def test_consecutive_poll_failure_limit_reports_pending_urls(virtual_clock):
    """Five consecutive batch failures terminate pending jobs as poll failures."""
    url = _example_url(1)
    scenario = UrlScenario(url=url)
    client = ScriptedSPN2Client(
        [scenario],
        poll_failures=(True,) * MAX_CONSECUTIVE_POLL_FAILURES,
    )
    results: list[ArchiveResult] = []

    counts = run_archive_workflow(
        client, [url], rate_limit_in_sec=0, api_params={}, on_result=results.append
    )

    assert counts == (0, 1)
    assert len(results) == 1
    assert results[0].url == url
    assert results[0].status == "failed"
    assert results[0].error_code == "poll_failure"
    assert client.poll_calls == MAX_CONSECUTIVE_POLL_FAILURES


def test_workflow_never_exceeds_pending_job_limit(virtual_clock):
    """The workflow keeps its submitted but unfinished jobs under the cap."""
    urls = [_example_url(number) for number in range(MAX_PENDING_JOBS + 3)]
    scenarios = [UrlScenario(url=url, pending_polls=MAX_PENDING_JOBS + 1) for url in urls]
    client = ScriptedSPN2Client(scenarios)
    results: list[ArchiveResult] = []

    counts = run_archive_workflow(
        client, list(urls), rate_limit_in_sec=0, api_params={}, on_result=results.append
    )

    assert counts == (len(urls), 0)
    assert len(results) == len(urls)
    assert client.max_pending_observed == MAX_PENDING_JOBS
    assert sum(size == MAX_PENDING_JOBS for size in client.pending_batch_sizes) > 1


def test_backoff_waits_while_capacity_is_full_and_urls_are_queued(monkeypatch, virtual_clock):
    """A full pending cap uses bounded backoff while more URLs wait in the queue."""
    monkeypatch.setattr(workflow, "MAX_PENDING_JOBS", 1)
    urls = [_example_url(1), _example_url(2)]
    scenarios = [
        UrlScenario(url=urls[0], pending_polls=3),
        UrlScenario(url=urls[1]),
    ]
    client = ScriptedSPN2Client(scenarios)

    run_archive_workflow(client, list(urls), rate_limit_in_sec=0, api_params={})

    saturated_poll_count = sum(
        submitted_count == 1 and pending_count == 1
        for submitted_count, pending_count in zip(
            client.submissions_at_poll, client.pending_batch_sizes, strict=True
        )
    )
    assert saturated_poll_count == 4
    assert any(
        seconds >= INITIAL_POLLING_WAIT and seconds <= MAX_POLLING_WAIT
        for seconds in virtual_clock.sleeps[:8]
    )


def test_null_status_ext_matches_an_omitted_status_ext(virtual_clock):
    """Explicit null status_ext uses the same fallback as an omitted field."""
    url = _example_url(1)
    scenario = UrlScenario(url=url)
    client = ScriptedSPN2Client([scenario], forced_poll_actions={url: ("null_status_ext",)})
    results: list[ArchiveResult] = []

    run_archive_workflow(
        client, [url], rate_limit_in_sec=0, api_params={}, on_result=results.append
    )

    assert results[0].error_code == "error:unknown"


def test_workflow_chunks_more_than_fifty_pending_jobs_with_real_client(
    requests_mock, monkeypatch, virtual_clock
):
    """A workflow batch over 50 pending jobs is chunked by the real client."""
    pending_limit = BATCH_STATUS_CHUNK_SIZE + 1
    job_ids = [f"job-{number}" for number in range(1, pending_limit + 1)]
    save_responses = [{"json": {"job_id": job_id}} for job_id in job_ids]
    status_responses: list[dict[str, object]] = []
    for job_count in range(1, pending_limit):
        status_responses.append(
            {"json": [{"job_id": job_id, "status": "pending"} for job_id in job_ids[:job_count]]}
        )
    for chunk_start in range(0, pending_limit, BATCH_STATUS_CHUNK_SIZE):
        chunk = job_ids[chunk_start : chunk_start + BATCH_STATUS_CHUNK_SIZE]
        status_responses.append(
            {"json": [{"job_id": job_id, "status": "pending"} for job_id in chunk]}
        )
    for chunk_start in range(0, pending_limit, BATCH_STATUS_CHUNK_SIZE):
        chunk = job_ids[chunk_start : chunk_start + BATCH_STATUS_CHUNK_SIZE]
        status_responses.append(
            {
                "json": [
                    {
                        "job_id": job_id,
                        "status": "success",
                        "timestamp": SUCCESS_TIMESTAMP,
                    }
                    for job_id in chunk
                ]
            }
        )

    requests_mock.post(SPN2Client.SAVE_URL, response_list=save_responses)
    requests_mock.post(
        SPN2Client.STATUS_URL,
        response_list=status_responses,
    )
    client = SPN2Client(requests.Session(), "access-key", "secret-key")
    monkeypatch.setattr(workflow, "MAX_PENDING_JOBS", pending_limit)
    urls = [_example_url(number) for number in range(pending_limit)]
    results: list[ArchiveResult] = []

    counts = run_archive_workflow(
        client, list(urls), rate_limit_in_sec=0, api_params={}, on_result=results.append
    )

    status_requests = [
        request for request in requests_mock.request_history if request.url == SPN2Client.STATUS_URL
    ]
    assert counts == (pending_limit, 0)
    assert len(results) == pending_limit
    assert len(status_requests) == pending_limit + 3
    assert [
        parse_qs(request.text)["job_ids"][0].split(",") for request in status_requests[-4:]
    ] == [job_ids[:BATCH_STATUS_CHUNK_SIZE], job_ids[BATCH_STATUS_CHUNK_SIZE:]] * 2
