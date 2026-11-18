"""Round-based property check for the archive workflow.

Each URL gets a script of capture rounds. A round is the submit attempts that
lead to one accepted job (or to giving up), followed by that job's status
responses. The reference model walks the rounds per URL without any shared
state, so it has no counters to forget to reset.
"""

from __future__ import annotations

import hashlib
import re
import time
from dataclasses import dataclass, field

import pytest
import requests
from hypothesis import HealthCheck, event, given, settings
from hypothesis import strategies as st

from wayback_machine_archiver import workflow
from wayback_machine_archiver.workflow import (
    JOB_TIMEOUT_SEC,
    MAX_CONSECUTIVE_POLL_FAILURES,
    MAX_TRANSIENT_RETRIES,
    PERMANENT_ERROR_MESSAGES,
    REQUEUE_ERRORS,
    TRANSIENT_ERROR_MESSAGES,
    ArchiveResult,
    run_archive_workflow,
)

MAX_SUBMISSION_RETRIES = 3
# Virtual clock start: a realistic epoch (2027-01-15), so capture timestamps
# compare sensibly with submit times.
CLOCK_START = 1_800_000_000.0
# The kaon logs show stale results only within 2 seconds of a resubmit.
STALE_REPLAY_SEC = 2
EARLIER_CAPTURE_EPOCH = CLOCK_START - 3 * 3600


def _stamp(epoch: float) -> str:
    return time.strftime("%Y%m%d%H%M%S", time.gmtime(epoch))


def _job_id(url: str) -> str:
    """SPN2's real derivation: "spn2-" + SHA-1 of the submitted URL."""
    return "spn2-" + hashlib.sha1(url.encode()).hexdigest()


UNKNOWN_CODE = "error:not-a-documented-code"

TRANSIENT_CODES = sorted(REQUEUE_ERRORS)
PERMANENT_CODES = [*sorted(PERMANENT_ERROR_MESSAGES), UNKNOWN_CODE]


# ---------------------------------------------------------------------------
# Script data
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Terminal:
    """How one accepted job ends.

    kind is one of: success, error, timeout.
    For error, code is the raw status_ext and message the raw message.
    For timeout, idle is the response repeated forever: pending or missing.
    """

    kind: str
    code: str | None = None
    message: str = "scripted error"
    idle: str = "pending"


@dataclass(frozen=True)
class Round:
    submit_failures: tuple[str, ...]  # each: connection_error | missing_job_id
    idle_polls: tuple[str, ...]  # each: pending | missing, before the terminal
    terminal: Terminal


@dataclass(frozen=True)
class UrlScript:
    url: str
    rounds: tuple[Round, ...]
    # A status left in SPN2 by an earlier run: none, success, transient, permanent.
    prior: str = "none"

    def round(self, index: int) -> Round:
        # Past the end of the script, the last round repeats.
        return self.rounds[min(index, len(self.rounds) - 1)]


@dataclass(frozen=True)
class Expected:
    status: str
    error_code: str | None
    submit_calls: int
    accepted_jobs: int


# ---------------------------------------------------------------------------
# Reference model
# ---------------------------------------------------------------------------


def _effective_code(terminal: Terminal) -> str | None:
    if "RecursionError" in terminal.message:
        return "error:recursion-error"
    return terminal.code


def reference(script: UrlScript, *, stale_success_seen: bool = False) -> Expected:
    """Expected terminal result and call counts for one URL.

    Stale statuses must not change anything, with one exception: if the first
    job was shown an earlier run's success and then timed out, the earlier
    capture is reported as a success.
    """
    submit_calls = 0
    accepted = 0
    transient_seen = 0
    index = 0
    while True:
        rnd = script.round(index)
        index += 1
        failures = len(rnd.submit_failures)
        if failures >= MAX_SUBMISSION_RETRIES:
            return Expected(
                "failed", "submit_failed", submit_calls + MAX_SUBMISSION_RETRIES, accepted
            )
        submit_calls += failures + 1
        accepted += 1

        terminal = rnd.terminal
        if terminal.kind == "success":
            return Expected("success", None, submit_calls, accepted)
        if terminal.kind == "timeout":
            if accepted == 1 and stale_success_seen:
                return Expected("success", None, submit_calls, accepted)
            return Expected("failed", "timeout", submit_calls, accepted)

        code = _effective_code(terminal)
        if code in REQUEUE_ERRORS:
            transient_seen += 1
            if transient_seen > MAX_TRANSIENT_RETRIES:
                return Expected("failed", code, submit_calls, accepted)
            continue
        return Expected("failed", code, submit_calls, accepted)


# ---------------------------------------------------------------------------
# Fake client
# ---------------------------------------------------------------------------


@dataclass
class _Job:
    url: str
    responses: tuple[tuple[str, ...], ...]
    submitted_at: float
    stale_row: dict[str, object] | None = None
    cursor: int = 0


@dataclass
class RoundScriptClient:
    scripts: dict[str, UrlScript]
    clock: object
    poll_failures: tuple[bool, ...] = ()
    max_submit_calls: int = 300
    max_poll_calls: int = 2000

    submit_calls: dict[str, int] = field(default_factory=dict)
    accepted_jobs: dict[str, int] = field(default_factory=dict)
    poll_calls: int = 0
    max_pending_observed: int = 0
    failed_poll_streak: int = 0
    _round_index: dict[str, int] = field(default_factory=dict)
    _attempt_in_round: dict[str, int] = field(default_factory=dict)
    _jobs: dict[str, _Job] = field(default_factory=dict)
    _last_terminal_row: dict[str, dict[str, object]] = field(default_factory=dict)
    stale_rows_served: int = 0
    stale_success_served: set[str] = field(default_factory=set)

    def submit_capture(
        self,
        url_to_archive: str,
        rate_limit_wait: float,
        api_params: dict[str, str | int],
    ) -> str | None:
        del rate_limit_wait, api_params
        url = url_to_archive
        self.submit_calls[url] = self.submit_calls.get(url, 0) + 1
        if sum(self.submit_calls.values()) > self.max_submit_calls:
            raise AssertionError("submit step budget exceeded")

        rnd = self.scripts[url].round(self._round_index.get(url, 0))
        attempt = self._attempt_in_round.get(url, 0)
        if attempt < len(rnd.submit_failures):
            self._attempt_in_round[url] = attempt + 1
            if rnd.submit_failures[attempt] == "connection_error":
                raise requests.exceptions.ConnectionError("scripted submit failure")
            return None

        self._round_index[url] = self._round_index.get(url, 0) + 1
        self._attempt_in_round[url] = 0
        self.accepted_jobs[url] = self.accepted_jobs.get(url, 0) + 1
        job_id = _job_id(url)
        stale_row = self._last_terminal_row.get(job_id) or _prior_row(
            job_id, self.scripts[url].prior
        )
        self._jobs[job_id] = _Job(
            url=url, responses=_responses(rnd), submitted_at=self.clock.now, stale_row=stale_row
        )
        return job_id

    def check_status_batch(self, job_ids: list[str]) -> list[dict[str, object]]:
        self.poll_calls += 1
        if self.poll_calls > self.max_poll_calls:
            raise AssertionError("poll step budget exceeded")
        self.max_pending_observed = max(self.max_pending_observed, len(job_ids))
        index = self.poll_calls - 1
        if index < len(self.poll_failures) and self.poll_failures[index]:
            self.failed_poll_streak += 1
            raise requests.exceptions.ConnectionError("scripted poll failure")
        self.failed_poll_streak = 0

        rows: list[dict[str, object]] = []
        for job_id in job_ids:
            job = self._jobs[job_id]
            if job.stale_row is not None and self.clock.now - job.submitted_at <= STALE_REPLAY_SEC:
                # SPN2 still answers with the previous job's result.
                self.stale_rows_served += 1
                if job.stale_row["status"] == "success":
                    self.stale_success_served.add(job.url)
                rows.append(job.stale_row)
                continue
            response = job.responses[min(job.cursor, len(job.responses) - 1)]
            job.cursor += 1
            row = _status_row(job_id, response, self.clock.now)
            if row is not None:
                rows.append(row)
                if row["status"] in ("success", "error"):
                    self._last_terminal_row[job_id] = row
        return rows


def _prior_row(job_id: str, prior: str) -> dict[str, object] | None:
    if prior == "success":
        return {"job_id": job_id, "status": "success", "timestamp": _stamp(EARLIER_CAPTURE_EPOCH)}
    if prior == "transient":
        return {
            "job_id": job_id,
            "status": "error",
            "status_ext": "error:job-failed",
            "message": "old",
        }
    if prior == "permanent":
        return {
            "job_id": job_id,
            "status": "error",
            "status_ext": "error:not-found",
            "message": "old",
        }
    return None


def _responses(rnd: Round) -> tuple[tuple[str, ...], ...]:
    idle = tuple((kind,) for kind in rnd.idle_polls)
    terminal = rnd.terminal
    if terminal.kind == "success":
        return (*idle, ("success",))
    if terminal.kind == "timeout":
        return (*idle, (terminal.idle,))  # repeated forever
    return (*idle, ("error", terminal.code or "", terminal.message))


def _status_row(job_id: str, response: tuple[str, ...], now: float) -> dict[str, object] | None:
    kind = response[0]
    if kind == "missing":
        return None
    if kind == "pending":
        return {"job_id": job_id, "status": "pending"}
    if kind == "success":
        return {"job_id": job_id, "status": "success", "timestamp": _stamp(now)}
    _, code, message = response
    return {"job_id": job_id, "status": "error", "status_ext": code, "message": message}


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

_terminals = st.one_of(
    st.just(Terminal("success")),
    st.builds(Terminal, kind=st.just("error"), code=st.sampled_from(TRANSIENT_CODES)),
    st.builds(Terminal, kind=st.just("error"), code=st.sampled_from(PERMANENT_CODES)),
    st.builds(
        Terminal,
        kind=st.just("error"),
        code=st.sampled_from(TRANSIENT_CODES + PERMANENT_CODES),
        message=st.just("Traceback ... RecursionError: maximum recursion depth exceeded"),
    ),
    st.builds(Terminal, kind=st.just("timeout"), idle=st.sampled_from(["pending", "missing"])),
)

_rounds = st.builds(
    Round,
    submit_failures=st.lists(
        st.sampled_from(["connection_error", "missing_job_id"]),
        max_size=MAX_SUBMISSION_RETRIES + 1,
    ).map(tuple),
    idle_polls=st.lists(st.sampled_from(["pending", "missing"]), max_size=3).map(tuple),
    terminal=_terminals,
)


@st.composite
def _url_scripts(draw: st.DrawFn) -> list[UrlScript]:
    # Small pool: 1-6 URLs.
    numbers = draw(st.lists(st.integers(0, 50), min_size=1, max_size=6, unique=True))
    return [
        UrlScript(
            url=f"https://example.test/{number}",
            rounds=tuple(draw(st.lists(_rounds, min_size=1, max_size=MAX_TRANSIENT_RETRIES + 2))),
            prior=draw(st.sampled_from(["none", "success", "transient", "permanent"])),
        )
        for number in numbers
    ]


@st.composite
def _poll_failures(draw: st.DrawFn) -> tuple[bool, ...]:
    """Runs of failed polls, each shorter than the give-up limit, split by a success."""
    runs = draw(st.lists(st.integers(0, MAX_CONSECUTIVE_POLL_FAILURES - 1), max_size=6))
    pattern: list[bool] = []
    for length in runs:
        gap = draw(st.integers(1, 3))
        pattern.extend([False] * gap + [True] * length)
    return tuple(pattern)


def _record_events(scripts: list[UrlScript], expected: dict[str, Expected]) -> None:
    for script in scripts:
        result = expected[script.url]
        event(
            f"outcome: {result.status} / {result.error_code if result.error_code in ('submit_failed', 'timeout', None) else 'api-code'}"
        )
        event(f"accepted jobs: {result.accepted_jobs}")
        for rnd in script.rounds:
            event(f"submit failures in round: {len(rnd.submit_failures)}")
            if rnd.terminal.kind == "timeout":
                event(f"timeout via {rnd.terminal.idle}")
            if "RecursionError" in rnd.terminal.message:
                event("RecursionError message")


# ---------------------------------------------------------------------------
# Properties
# ---------------------------------------------------------------------------


def _reset_clock(clock) -> None:
    clock.now = CLOCK_START
    clock.sleeps.clear()


@settings(suppress_health_check=[HealthCheck.function_scoped_fixture, HealthCheck.too_slow])
@given(
    scripts=_url_scripts(),
    poll_failures=_poll_failures(),
    pending_cap=st.integers(1, 10),
)
def test_round_scripts_match_reference_model(
    scripts, poll_failures, pending_cap, virtual_clock, monkeypatch
):
    """Every URL ends exactly once, with the reference outcome and call counts.

    Poll failure runs stay below MAX_CONSECUTIVE_POLL_FAILURES, so they must
    not change any outcome.
    """
    _reset_clock(virtual_clock)
    monkeypatch.setattr(workflow, "MAX_PENDING_JOBS", pending_cap)
    event(f"pending cap: {'saturable' if pending_cap < len(scripts) else 'never full'}")
    event(f"poll failures: {sum(poll_failures)}")

    client = RoundScriptClient(
        {s.url: s for s in scripts}, clock=virtual_clock, poll_failures=poll_failures
    )
    results: list[ArchiveResult] = []
    urls = [s.url for s in scripts]

    success_count, failure_count = run_archive_workflow(
        client, list(urls), rate_limit_in_sec=0, api_params={}, on_result=results.append
    )

    # Which stale successes were shown depends on poll timing, so the fake
    # client, not the script, records it.
    expected = {
        s.url: reference(s, stale_success_seen=s.url in client.stale_success_served)
        for s in scripts
    }
    _record_events(scripts, expected)
    event(f"stale rows served: {'yes' if client.stale_rows_served else 'no'}")

    scripts_by_url = {s.url: s for s in scripts}
    # One result per URL.
    assert sorted(r.url for r in results) == sorted(urls)
    by_url = {r.url: r for r in results}

    # Counts agree with callbacks.
    assert success_count == sum(r.status == "success" for r in results)
    assert failure_count == sum(r.status == "failed" for r in results)
    assert success_count + failure_count == len(urls)

    for url, want in expected.items():
        got = by_url[url]
        assert (got.status, got.error_code) == (want.status, want.error_code), url
        assert client.submit_calls.get(url, 0) == want.submit_calls, url
        assert client.accepted_jobs.get(url, 0) == want.accepted_jobs, url
        assert want.submit_calls <= (MAX_TRANSIENT_RETRIES + 1) * MAX_SUBMISSION_RETRIES
        if got.status == "success":
            match = re.fullmatch(
                rf"https://web\.archive\.org/web/(\d{{14}})/{re.escape(url)}", got.archive_url or ""
            )
            assert match, got.archive_url
            if (
                want.error_code is None
                and url in client.stale_success_served
                and (match.group(1) == _stamp(EARLIER_CAPTURE_EPOCH))
            ):
                # Only the earlier-capture fallback may report the old capture.
                assert scripts_by_url[url].rounds[0].terminal.kind == "timeout"
            else:
                assert match.group(1) >= _stamp(CLOCK_START), "stale capture reported as new"
        else:
            assert got.archive_url is None
        if want.error_code == "timeout":
            assert virtual_clock.now > CLOCK_START + JOB_TIMEOUT_SEC

    assert client.max_pending_observed <= pending_cap


@settings(suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(scripts=_url_scripts(), lead_in=st.integers(0, 3))
def test_poll_give_up_reports_every_url_once(scripts, lead_in, virtual_clock):
    """Hitting the consecutive poll failure limit still ends every URL exactly once."""
    _reset_clock(virtual_clock)
    failures = (False,) * lead_in + (True,) * (MAX_CONSECUTIVE_POLL_FAILURES * 50)
    client = RoundScriptClient(
        {s.url: s for s in scripts}, clock=virtual_clock, poll_failures=failures
    )
    results: list[ArchiveResult] = []
    urls = [s.url for s in scripts]
    give_up_streaks: list[int] = []

    def on_result(result: ArchiveResult) -> None:
        # The first poll_failure result of each give-up burst records how many
        # consecutive failed polls preceded it.
        if result.error_code == "poll_failure" and client.failed_poll_streak:
            give_up_streaks.append(client.failed_poll_streak)
            client.failed_poll_streak = 0
        results.append(result)

    success_count, failure_count = run_archive_workflow(
        client, list(urls), rate_limit_in_sec=0, api_params={}, on_result=on_result
    )

    assert all(streak == MAX_CONSECUTIVE_POLL_FAILURES for streak in give_up_streaks)

    assert sorted(r.url for r in results) == sorted(urls)
    assert success_count + failure_count == len(urls)
    for result in results:
        if result.error_code == "poll_failure":
            assert result.status == "failed"
            assert result.job_id is not None


# ---------------------------------------------------------------------------
# Error table consistency
# ---------------------------------------------------------------------------


def test_transient_codes_all_have_messages():
    assert set(TRANSIENT_ERROR_MESSAGES) == REQUEUE_ERRORS


def test_transient_and_permanent_codes_are_disjoint():
    assert not REQUEUE_ERRORS & set(PERMANENT_ERROR_MESSAGES)


@pytest.mark.parametrize("code", sorted(REQUEUE_ERRORS | set(PERMANENT_ERROR_MESSAGES)))
def test_error_codes_are_well_formed(code):
    assert re.fullmatch(r"error:[a-z0-9]+(-[a-z0-9]+)*", code)
