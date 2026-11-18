"""Properties for URL gathering and command-line option handling."""

import argparse
import io
import json
import string
from pathlib import Path
from unittest import mock
from urllib.parse import urlparse

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from wayback_machine_archiver import archiver
from wayback_machine_archiver.cli import create_parser
from wayback_machine_archiver.workflow import ArchiveResult


def _url_strategy() -> st.SearchStrategy[str]:
    return st.integers(min_value=0, max_value=10_000).map(
        lambda suffix: f"https://example.test/{suffix}"
    )


@given(urls=st.sets(st.text(max_size=100), max_size=20))
def test_filter_valid_urls_is_idempotent_and_returns_only_http_urls(urls: set[str]) -> None:
    filtered_urls = archiver._filter_valid_urls(urls)

    assert archiver._filter_valid_urls(filtered_urls) == filtered_urls
    assert filtered_urls <= urls
    for url in filtered_urls:
        parsed_url = urlparse(url)
        assert parsed_url.scheme in {"http", "https"}
        assert parsed_url.netloc


@settings(suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(
    command_line_urls=st.lists(_url_strategy(), max_size=8),
    sitemap_urls=st.sets(_url_strategy(), max_size=8),
    file_lines=st.lists(
        st.one_of(
            st.just(""),
            st.just(" "),
            st.tuples(
                st.text(alphabet=" \t", max_size=3),
                _url_strategy(),
                st.text(alphabet=" \t", max_size=3),
            ).map(lambda parts: "".join(parts)),
        ),
        max_size=8,
    ),
    sitemap_refs=st.lists(
        st.tuples(st.booleans(), st.integers(min_value=0, max_value=5)),
        max_size=6,
    ),
    archive_sitemap=st.booleans(),
)
def test_gather_urls_matches_the_source_union(
    command_line_urls: list[str],
    sitemap_urls: set[str],
    file_lines: list[str],
    sitemap_refs: list[tuple[bool, int]],
    archive_sitemap: bool,
    tmp_path: Path,
) -> None:
    sitemap_locations = [
        f"file:///tmp/sitemap-{number}.xml"
        if is_local
        else f"https://sitemaps.example/{number}.xml"
        for is_local, number in sitemap_refs
    ]
    # The file is rewritten for each example, so reusing the fixture is safe.
    file_path = tmp_path / "urls.txt"
    file_path.write_text("\n".join(file_lines), encoding="utf-8")
    args = argparse.Namespace(
        urls=command_line_urls,
        sitemaps=sitemap_locations,
        archive_sitemap=archive_sitemap,
        file=str(file_path),
    )

    expected_urls = set(command_line_urls)
    if sitemap_locations:
        expected_urls |= sitemap_urls
    expected_urls |= {line.strip() for line in file_lines if line.strip()}
    if archive_sitemap:
        expected_urls |= {
            location for location in sitemap_locations if not location.startswith("file://")
        }

    with (
        mock.patch.object(archiver, "_create_session_with_retries", return_value=object()),
        mock.patch.object(archiver, "process_sitemaps", return_value=sitemap_urls),
    ):
        assert archiver._gather_urls(args) == expected_urls


@given(
    capture_all=st.booleans(),
    capture_outlinks=st.booleans(),
    capture_screenshot=st.booleans(),
    delay_wb_availability=st.booleans(),
    force_get=st.booleans(),
    skip_first_archive=st.booleans(),
    email_result=st.booleans(),
    if_not_archived_within=st.one_of(
        st.none(),
        st.text(
            alphabet=string.ascii_letters + string.digits + " ./=", min_size=1, max_size=20
        ).filter(str.strip),
    ),
    js_behavior_timeout=st.one_of(st.none(), st.integers(min_value=0, max_value=30)),
    capture_cookie=st.one_of(
        st.none(),
        st.text(
            alphabet=string.ascii_letters + string.digits + " ./=", min_size=1, max_size=20
        ).filter(str.strip),
    ),
    use_user_agent=st.one_of(
        st.none(),
        st.text(
            alphabet=string.ascii_letters + string.digits + " ./=", min_size=1, max_size=20
        ).filter(str.strip),
    ),
)
def test_build_api_params_includes_every_provided_flag_value(
    capture_all: bool,
    capture_outlinks: bool,
    capture_screenshot: bool,
    delay_wb_availability: bool,
    force_get: bool,
    skip_first_archive: bool,
    email_result: bool,
    if_not_archived_within: str | None,
    js_behavior_timeout: int | None,
    capture_cookie: str | None,
    use_user_agent: str | None,
) -> None:
    boolean_options = {
        "capture_all": capture_all,
        "capture_outlinks": capture_outlinks,
        "capture_screenshot": capture_screenshot,
        "delay_wb_availability": delay_wb_availability,
        "force_get": force_get,
        "skip_first_archive": skip_first_archive,
        "email_result": email_result,
    }
    value_options = {
        "if_not_archived_within": if_not_archived_within,
        "js_behavior_timeout": js_behavior_timeout,
        "capture_cookie": capture_cookie,
        "use_user_agent": use_user_agent,
    }
    option_flags = {
        "capture_all": "--capture-all",
        "capture_outlinks": "--capture-outlinks",
        "capture_screenshot": "--capture-screenshot",
        "delay_wb_availability": "--delay-wb-availability",
        "force_get": "--force-get",
        "skip_first_archive": "--skip-first-archive",
        "email_result": "--email-result",
        "if_not_archived_within": "--if-not-archived-within",
        "js_behavior_timeout": "--js-behavior-timeout",
        "capture_cookie": "--capture-cookie",
        "use_user_agent": "--user-agent",
    }

    argv: list[str] = []
    for name, is_enabled in boolean_options.items():
        if is_enabled:
            argv.append(option_flags[name])
    for name, value in value_options.items():
        if value is not None:
            argv.extend((option_flags[name], str(value)))

    parsed_args = create_parser().parse_args(argv)
    expected_params = {name: "1" for name, is_enabled in boolean_options.items() if is_enabled}
    expected_params.update(
        {name: value for name, value in value_options.items() if value is not None}
    )

    assert archiver._build_api_params(parsed_args) == expected_params


@pytest.mark.parametrize(
    ("option_flag", "parameter_name"),
    [
        ("--if-not-archived-within", "if_not_archived_within"),
        ("--capture-cookie", "capture_cookie"),
        ("--user-agent", "use_user_agent"),
    ],
)
@given(value=st.text(alphabet=" \t", max_size=3))
def test_empty_api_option_values_are_rejected(
    option_flag: str, parameter_name: str, value: str
) -> None:
    """An empty value would otherwise be dropped silently from the API request."""
    del parameter_name
    with pytest.raises(SystemExit):
        create_parser().parse_args([option_flag, value])


@given(rate_limit=st.integers(min_value=-1_000_000, max_value=1_000_000))
def test_enforce_rate_limit_is_minimum_clamped_and_idempotent(rate_limit: int) -> None:
    enforced_rate_limit = archiver._enforce_rate_limit(rate_limit)

    assert enforced_rate_limit >= 9
    assert enforced_rate_limit == max(rate_limit, 9)
    assert archiver._enforce_rate_limit(enforced_rate_limit) == enforced_rate_limit


@given(
    results=st.lists(
        st.tuples(
            _url_strategy(),
            st.sampled_from(["success", "failed"]),
        ),
        max_size=10,
    )
)
def test_json_output_writes_one_valid_record_per_result(
    results: list[tuple[str, str]],
) -> None:
    output = io.StringIO()
    with mock.patch.object(archiver.sys, "stdout", output):
        for url, status in results:
            archiver._write_json_result(
                ArchiveResult(
                    url=url,
                    status=status,
                    archive_url="https://web.archive.org/" if status == "success" else None,
                    error_code=None if status == "success" else "failed",
                    job_id="job-id",
                )
            )

    output_lines = output.getvalue().splitlines()
    records = [json.loads(line) for line in output_lines]

    assert len(records) == len(results)
    assert [(record["url"], record["status"]) for record in records] == results
    assert all(record["status"] in {"success", "failed"} for record in records)
