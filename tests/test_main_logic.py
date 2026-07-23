"""Tests for main() logic in archiver.py."""

import json
import logging
import os
import sys
from datetime import datetime, timezone
from unittest import mock

import pytest

from wayback_machine_archiver.archiver import _write_json_result, main
from wayback_machine_archiver.clients import SPN2Client
from wayback_machine_archiver.workflow import ArchiveResult, _NOOP_CALLBACK

# Test constants
DUMMY_CREDENTIALS = "dummy_key"
TEST_JOB_ID = "test-job-123"
TEST_TIMESTAMP = "20250115120000"
EXTRACTED_PAGE_URL = "https://example.com/page1"


@pytest.fixture
def cli_args(monkeypatch):
    """Fixture to safely set sys.argv for CLI tests."""

    def _set(args):
        monkeypatch.setattr(sys, "argv", args)

    return _set


CREDENTIAL_ENV_VARS = ("INTERNET_ARCHIVE_ACCESS_KEY", "INTERNET_ARCHIVE_SECRET_KEY")


@pytest.fixture
def mock_credentials(monkeypatch):
    """Mock environment credentials for Internet Archive API."""
    monkeypatch.setattr(
        "wayback_machine_archiver.archiver.os.getenv",
        lambda key, default=None: (
            DUMMY_CREDENTIALS if key in CREDENTIAL_ENV_VARS else default
        ),
    )


# --- Tests for URL gathering and shuffling ---


@mock.patch("wayback_machine_archiver.archiver.process_sitemaps", return_value=set())
@mock.patch(
    "wayback_machine_archiver.archiver.run_archive_workflow", return_value=(0, 0)
)
@mock.patch("wayback_machine_archiver.archiver.random.shuffle")
def test_random_order_flag_shuffles_urls(
    mock_shuffle, mock_workflow, mock_sitemaps, cli_args, mock_credentials
):
    """Verify that when --random-order is passed, random.shuffle is called."""
    urls_to_archive = ["http://test.com/a", "http://test.com/b"]
    cli_args(["archiver", "--random-order"] + urls_to_archive)
    main()
    mock_shuffle.assert_called_once()

    passed_urls = mock_workflow.call_args[0][1]
    assert set(passed_urls) == set(urls_to_archive)


@mock.patch("wayback_machine_archiver.archiver.process_sitemaps", return_value=set())
@mock.patch(
    "wayback_machine_archiver.archiver.run_archive_workflow", return_value=(0, 0)
)
@mock.patch("wayback_machine_archiver.archiver.random.shuffle")
def test_default_order_does_not_shuffle(
    mock_shuffle, mock_workflow, mock_sitemaps, cli_args, mock_credentials
):
    """Verify that without --random-order, shuffle is not called."""
    urls_to_archive = ["http://test.com/a", "http://test.com/b"]
    cli_args(["archiver"] + urls_to_archive)
    main()
    mock_shuffle.assert_not_called()

    passed_urls = mock_workflow.call_args[0][1]
    assert set(passed_urls) == set(urls_to_archive)


@mock.patch("wayback_machine_archiver.archiver.process_sitemaps", return_value=set())
@mock.patch(
    "wayback_machine_archiver.archiver.run_archive_workflow", return_value=(0, 0)
)
def test_main_builds_and_passes_api_params(
    mock_workflow, mock_sitemaps, cli_args, mock_credentials
):
    """
    Verify that main() correctly constructs the api_params dictionary from CLI
    flags and passes it to the workflow.
    """
    cli_args(
        [
            "archiver",
            "http://test.com",
            "--capture-screenshot",
            "--js-behavior-timeout",
            "10",
            "--if-not-archived-within",
            "5d",
            "--user-agent",
            "TestBot/1.0",
        ]
    )
    main()

    passed_params = mock_workflow.call_args[0][3]
    expected_params = {
        "capture_screenshot": "1",
        "js_behavior_timeout": 10,
        "if_not_archived_within": "5d",
        "use_user_agent": "TestBot/1.0",
    }
    assert passed_params == expected_params


# --- Tests for exit codes ---


@mock.patch("wayback_machine_archiver.archiver.process_sitemaps", return_value=set())
@mock.patch(
    "wayback_machine_archiver.archiver.run_archive_workflow", return_value=(0, 3)
)
def test_main_exits_with_code_1_on_failures(
    mock_workflow, mock_sitemaps, cli_args, mock_credentials
):
    """Verify that main() calls sys.exit(1) when any captures fail."""
    cli_args(["archiver", "http://test.com"])
    with pytest.raises(SystemExit) as exc_info:
        main()
    assert exc_info.value.code == 1


@mock.patch("wayback_machine_archiver.archiver.process_sitemaps", return_value=set())
@mock.patch(
    "wayback_machine_archiver.archiver.run_archive_workflow", return_value=(5, 0)
)
def test_main_exits_cleanly_on_success(
    mock_workflow, mock_sitemaps, cli_args, mock_credentials
):
    """Verify that main() exits normally (no SystemExit) when all captures succeed."""
    cli_args(["archiver", "http://test.com"])
    main()


# --- Integration test for full main() flow ---


@mock.patch("wayback_machine_archiver.workflow.time.sleep")
@mock.patch("wayback_machine_archiver.clients.time.sleep")
def test_main_end_to_end_with_mocked_timing(
    _mock_client_sleep, _mock_workflow_sleep, cli_args, mock_credentials, requests_mock
):
    """
    End-to-end test verifying the full flow from CLI args through API calls.
    Time.sleep is mocked to avoid delays; HTTP layer is mocked via requests-mock.
    """
    url_to_archive = "http://integration-test.com"

    # Mock the SPN2 API: submission endpoint
    requests_mock.post(
        SPN2Client.SAVE_URL,
        json={"job_id": TEST_JOB_ID},
        status_code=200,
    )

    # Mock the SPN2 API: status endpoint (returns success immediately)
    requests_mock.post(
        SPN2Client.STATUS_URL,
        json=[
            {
                "status": "success",
                "job_id": TEST_JOB_ID,
                "timestamp": TEST_TIMESTAMP,
            }
        ],
        status_code=200,
    )

    cli_args(["archiver", url_to_archive])

    # Should complete without raising
    main()

    # Verify the API was called correctly
    history = requests_mock.request_history

    # First call should be the submission
    submit_request = history[0]
    assert submit_request.method == "POST"
    assert submit_request.url == SPN2Client.SAVE_URL
    assert "url=http" in submit_request.text
    assert (
        f"LOW {DUMMY_CREDENTIALS}:{DUMMY_CREDENTIALS}"
        in submit_request.headers["Authorization"]
    )

    # Second call should be the status check
    status_request = history[1]
    assert status_request.method == "POST"
    assert status_request.url == SPN2Client.STATUS_URL
    assert TEST_JOB_ID in status_request.text


# --- Tests for --archive-sitemap-also flag ---


@pytest.mark.parametrize(
    "sitemaps,use_flag,expected_urls",
    [
        # Remote sitemap with flag: sitemap URL should be included
        (
            ["https://example.com/sitemap.xml"],
            True,
            {EXTRACTED_PAGE_URL, "https://example.com/sitemap.xml"},
        ),
        # Local sitemap with flag: local path should NOT be included
        (
            ["file:///tmp/sitemap.xml"],
            True,
            {EXTRACTED_PAGE_URL},
        ),
        # Mixed sitemaps with flag: only remote sitemap should be included
        (
            ["https://example.com/sitemap.xml", "file:///tmp/sitemap.xml"],
            True,
            {EXTRACTED_PAGE_URL, "https://example.com/sitemap.xml"},
        ),
        # Remote sitemap without flag: sitemap URL should NOT be included
        (
            ["https://example.com/sitemap.xml"],
            False,
            {EXTRACTED_PAGE_URL},
        ),
    ],
    ids=[
        "remote_with_flag_includes_sitemap",
        "local_with_flag_excludes_sitemap",
        "mixed_with_flag_includes_only_remote",
        "without_flag_excludes_sitemap",
    ],
)
@mock.patch(
    "wayback_machine_archiver.archiver.process_sitemaps",
    return_value={EXTRACTED_PAGE_URL},
)
@mock.patch(
    "wayback_machine_archiver.archiver.run_archive_workflow", return_value=(0, 0)
)
def test_archive_sitemap_also_behavior(
    mock_workflow,
    mock_process_sitemaps,
    sitemaps,
    use_flag,
    expected_urls,
    cli_args,
    mock_credentials,
):
    """
    Verify that --archive-sitemap-also correctly includes remote sitemap URLs
    in the archive list while excluding local file paths.
    """
    args = ["archiver", "--sitemaps"] + sitemaps
    if use_flag:
        args.append("--archive-sitemap-also")

    cli_args(args)
    main()

    passed_urls = mock_workflow.call_args[0][1]
    assert set(passed_urls) == expected_urls


# --- Tests for --json output ---


@mock.patch("wayback_machine_archiver.archiver.process_sitemaps", return_value=set())
@mock.patch(
    "wayback_machine_archiver.archiver.run_archive_workflow", return_value=(1, 0)
)
def test_json_flag_passes_callback(mock_workflow, mock_sitemaps, cli_args, mock_credentials):
    """Verify that --json passes _write_json_result as the on_result callback."""
    cli_args(["archiver", "--json", "http://test.com"])
    main()

    call_kwargs = mock_workflow.call_args[1]
    assert call_kwargs["on_result"] is not None
    assert callable(call_kwargs["on_result"])


@mock.patch("wayback_machine_archiver.archiver.process_sitemaps", return_value=set())
@mock.patch(
    "wayback_machine_archiver.archiver.run_archive_workflow", return_value=(1, 0)
)
def test_no_json_flag_uses_default(mock_workflow, mock_sitemaps, cli_args, mock_credentials):
    """Verify that without --json, on_result is the module-level no-op."""
    cli_args(["archiver", "http://test.com"])
    main()

    call_kwargs = mock_workflow.call_args[1]
    assert call_kwargs["on_result"] is _NOOP_CALLBACK


@mock.patch("wayback_machine_archiver.workflow.time.sleep")
@mock.patch("wayback_machine_archiver.clients.time.sleep")
def test_json_end_to_end(
    _mock_client_sleep, _mock_workflow_sleep, cli_args, mock_credentials, requests_mock, capsys
):
    """
    End-to-end test: --json emits a valid JSONL line to stdout on success.
    """
    url_to_archive = "http://json-test.com"

    requests_mock.post(
        SPN2Client.SAVE_URL,
        json={"job_id": TEST_JOB_ID},
        status_code=200,
    )
    requests_mock.post(
        SPN2Client.STATUS_URL,
        json=[
            {
                "status": "success",
                "job_id": TEST_JOB_ID,
                "timestamp": TEST_TIMESTAMP,
            }
        ],
        status_code=200,
    )

    cli_args(["archiver", "--json", url_to_archive])
    main()

    captured = capsys.readouterr()
    lines = [line for line in captured.out.strip().split("\n") if line]
    assert len(lines) == 1

    record = json.loads(lines[0])
    assert record["url"] == url_to_archive
    assert record["status"] == "success"
    assert record["archive_url"] == f"https://web.archive.org/web/{TEST_TIMESTAMP}/{url_to_archive}"
    assert record["error_code"] is None
    assert record["job_id"] == TEST_JOB_ID
    assert "recorded_at" in record


# --- Tests for _write_json_result ---


def test_write_json_result_success(capsys):
    """Verify _write_json_result produces valid JSONL with correct keys for success."""
    before = datetime.now(timezone.utc)
    _write_json_result(ArchiveResult(
        url="http://example.com",
        status="success",
        archive_url="https://web.archive.org/web/20250101/http://example.com",
        error_code=None,
        job_id="job-abc",
    ))

    captured = capsys.readouterr()
    record = json.loads(captured.out.strip())
    assert record["url"] == "http://example.com"
    assert record["job_id"] == "job-abc"
    assert record["status"] == "success"
    assert record["archive_url"] == "https://web.archive.org/web/20250101/http://example.com"
    assert record["error_code"] is None
    recorded = datetime.fromisoformat(record["recorded_at"])
    assert before <= recorded <= datetime.now(timezone.utc)


def test_write_json_result_failure(capsys):
    """Verify _write_json_result serializes null archive_url and error_code for failures."""
    before = datetime.now(timezone.utc)
    _write_json_result(ArchiveResult(
        url="http://gone.com",
        status="failed",
        archive_url=None,
        error_code="error:not-found",
        job_id="job-xyz",
    ))

    captured = capsys.readouterr()
    record = json.loads(captured.out.strip())
    assert record["url"] == "http://gone.com"
    assert record["job_id"] == "job-xyz"
    assert record["status"] == "failed"
    assert record["archive_url"] is None
    assert record["error_code"] == "error:not-found"
    recorded = datetime.fromisoformat(record["recorded_at"])
    assert before <= recorded <= datetime.now(timezone.utc)


def test_write_json_result_timeout(capsys):
    """Verify _write_json_result handles timeout as a failure with error_code."""
    _write_json_result(ArchiveResult(
        url="http://slow.com",
        status="failed",
        archive_url=None,
        error_code="timeout",
        job_id="job-stuck",
    ))

    captured = capsys.readouterr()
    record = json.loads(captured.out.strip())
    assert record["status"] == "failed"
    assert record["archive_url"] is None
    assert record["error_code"] == "timeout"
    assert record["job_id"] == "job-stuck"


def test_write_json_result_no_job_id(capsys):
    """Verify _write_json_result handles null job_id for submit failures."""
    _write_json_result(ArchiveResult(
        url="http://doomed.com",
        status="failed",
        archive_url=None,
        error_code="submit_failed",
        job_id=None,
    ))

    captured = capsys.readouterr()
    record = json.loads(captured.out.strip())
    assert record["job_id"] is None
    assert record["status"] == "failed"


# --- End-to-end test for failure JSON output ---


@mock.patch("wayback_machine_archiver.workflow.time.sleep")
@mock.patch("wayback_machine_archiver.clients.time.sleep")
def test_json_end_to_end_failure(
    _mock_client_sleep, _mock_workflow_sleep, cli_args, mock_credentials, requests_mock, capsys
):
    """End-to-end: --json emits correct JSONL for a permanent failure."""
    url_to_archive = "http://blocked-test.com"

    requests_mock.post(
        SPN2Client.SAVE_URL,
        json={"job_id": TEST_JOB_ID},
        status_code=200,
    )
    requests_mock.post(
        SPN2Client.STATUS_URL,
        json=[
            {
                "status": "error",
                "job_id": TEST_JOB_ID,
                "status_ext": "error:blocked",
                "message": "Blocked by robots.txt",
            }
        ],
        status_code=200,
    )

    cli_args(["archiver", "--json", url_to_archive])
    with pytest.raises(SystemExit):
        main()

    captured = capsys.readouterr()
    lines = [line for line in captured.out.strip().split("\n") if line]
    assert len(lines) == 1

    record = json.loads(lines[0])
    assert record["url"] == url_to_archive
    assert record["status"] == "failed"
    assert record["archive_url"] is None
    assert record["error_code"] == "error:blocked"
    assert record["job_id"] == TEST_JOB_ID


# --- Multi-URL test ---


@mock.patch("wayback_machine_archiver.workflow.time.sleep")
@mock.patch("wayback_machine_archiver.clients.time.sleep")
def test_json_multi_url(
    _mock_client_sleep, _mock_workflow_sleep, cli_args, mock_credentials, requests_mock, capsys
):
    """End-to-end: --json with multiple URLs produces one JSONL line per URL."""
    from urllib.parse import parse_qs

    urls = ["http://a.com", "http://b.com", "http://c.com"]
    job_counter = iter(range(len(urls)))

    def submit_handler(request, context):
        idx = next(job_counter)
        return {"job_id": f"job-{idx}"}

    def status_handler(request, context):
        requested_ids = parse_qs(request.text).get("job_ids", [""])[0].split(",")
        return [
            {"status": "success", "job_id": jid, "timestamp": f"2025010{jid.split('-')[1]}"}
            for jid in requested_ids
        ]

    requests_mock.post(SPN2Client.SAVE_URL, json=submit_handler, status_code=200)
    requests_mock.post(SPN2Client.STATUS_URL, json=status_handler, status_code=200)

    cli_args(["archiver", "--json"] + urls)
    main()

    captured = capsys.readouterr()
    lines = [line for line in captured.out.strip().split("\n") if line]
    assert len(lines) == len(urls)

    output_urls = set()
    for line in lines:
        record = json.loads(line)
        assert record["status"] == "success"
        assert record["archive_url"] is not None
        assert record["error_code"] is None
        assert record["job_id"] is not None
        assert "recorded_at" in record
        output_urls.add(record["url"])

    assert output_urls == set(urls)


# --- BrokenPipeError handling ---


@mock.patch("wayback_machine_archiver.archiver.os.close")
@mock.patch("wayback_machine_archiver.archiver.os.dup2")
@mock.patch("wayback_machine_archiver.archiver.os.open", return_value=99)
@mock.patch("wayback_machine_archiver.archiver.process_sitemaps", return_value=set())
@mock.patch(
    "wayback_machine_archiver.archiver.run_archive_workflow",
    side_effect=BrokenPipeError,
)
def test_broken_pipe_exits_cleanly(
    mock_workflow, mock_sitemaps, mock_os_open, mock_dup2, mock_os_close, cli_args, mock_credentials
):
    """Verify that BrokenPipeError (e.g., piping to `head`) exits with code 1."""
    cli_args(["archiver", "--json", "http://test.com"])
    with pytest.raises(SystemExit) as exc_info:
        main()
    assert exc_info.value.code == 1
    mock_os_open.assert_called_once_with(os.devnull, os.O_WRONLY)
    mock_dup2.assert_called_once()
    mock_os_close.assert_called_once_with(99)


# --- Edge case tests for --json output ---


@mock.patch("wayback_machine_archiver.archiver.process_sitemaps", return_value=set())
def test_json_with_no_urls_produces_no_output(mock_sitemaps, cli_args, mock_credentials, capsys):
    """With --json but no valid URLs, nothing is written to stdout."""
    cli_args(["archiver", "--json"])
    main()

    captured = capsys.readouterr()
    assert captured.out == ""


@mock.patch("wayback_machine_archiver.workflow.time.sleep")
@mock.patch("wayback_machine_archiver.clients.time.sleep")
def test_json_filtered_urls_not_in_output(
    _mock_client_sleep, _mock_workflow_sleep, cli_args, mock_credentials, requests_mock, capsys
):
    """URLs filtered as invalid (e.g., ftp://) produce no JSONL record."""
    requests_mock.post(
        SPN2Client.SAVE_URL,
        json={"job_id": TEST_JOB_ID},
        status_code=200,
    )
    requests_mock.post(
        SPN2Client.STATUS_URL,
        json=[
            {"status": "success", "job_id": TEST_JOB_ID, "timestamp": TEST_TIMESTAMP}
        ],
        status_code=200,
    )

    cli_args(["archiver", "--json", "ftp://invalid.com", "http://valid.com"])
    main()

    captured = capsys.readouterr()
    lines = [line for line in captured.out.strip().split("\n") if line]
    assert len(lines) == 1
    record = json.loads(lines[0])
    assert record["url"] == "http://valid.com"


@mock.patch("wayback_machine_archiver.workflow.time.sleep")
@mock.patch("wayback_machine_archiver.clients.time.sleep")
def test_json_with_log_to_file(
    _mock_client_sleep, _mock_workflow_sleep, cli_args, mock_credentials, requests_mock, capsys, tmp_path
):
    """With --json and --log-to-file, JSONL goes to stdout and logs go to the file."""
    url_to_archive = "http://log-file-test.com"
    log_file = tmp_path / "test.log"

    requests_mock.post(
        SPN2Client.SAVE_URL,
        json={"job_id": TEST_JOB_ID},
        status_code=200,
    )
    requests_mock.post(
        SPN2Client.STATUS_URL,
        json=[
            {"status": "success", "job_id": TEST_JOB_ID, "timestamp": TEST_TIMESTAMP}
        ],
        status_code=200,
    )

    # Reset root logger so basicConfig can reconfigure with a file handler.
    root_logger = logging.getLogger()
    original_handlers = root_logger.handlers[:]
    root_logger.handlers.clear()

    cli_args(["archiver", "--json", "--log", "INFO", "--log-to-file", str(log_file), url_to_archive])
    try:
        main()
    finally:
        root_logger.handlers = original_handlers

    captured = capsys.readouterr()
    lines = [line for line in captured.out.strip().split("\n") if line]
    assert len(lines) == 1
    record = json.loads(lines[0])
    assert record["url"] == url_to_archive
    assert record["status"] == "success"

    log_contents = log_file.read_text()
    assert url_to_archive in log_contents
