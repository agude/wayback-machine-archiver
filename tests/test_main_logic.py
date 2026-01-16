"""Tests for main() logic in archiver.py."""

import sys
from unittest import mock

import pytest

from wayback_machine_archiver.archiver import main
from wayback_machine_archiver.clients import SPN2Client

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
        lambda key, default=None: DUMMY_CREDENTIALS if key in CREDENTIAL_ENV_VARS else default,
    )


# --- Tests for URL gathering and shuffling ---


@mock.patch("wayback_machine_archiver.archiver.process_sitemaps", return_value=set())
@mock.patch("wayback_machine_archiver.archiver.run_archive_workflow")
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
@mock.patch("wayback_machine_archiver.archiver.run_archive_workflow")
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
@mock.patch("wayback_machine_archiver.archiver.run_archive_workflow")
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
    assert f"LOW {DUMMY_CREDENTIALS}:{DUMMY_CREDENTIALS}" in submit_request.headers[
        "Authorization"
    ]

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
@mock.patch("wayback_machine_archiver.archiver.run_archive_workflow")
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
