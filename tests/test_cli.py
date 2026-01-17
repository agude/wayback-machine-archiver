"""Tests for CLI argument parsing logic."""

import logging
import sys
from unittest import mock

import pytest

from wayback_machine_archiver.archiver import _is_valid_url, main
from wayback_machine_archiver.cli import create_parser

# Test constants
DUMMY_CREDENTIALS = "dummy_key"
CREDENTIAL_ENV_VARS = ("INTERNET_ARCHIVE_ACCESS_KEY", "INTERNET_ARCHIVE_SECRET_KEY")


@pytest.fixture
def cli_args(monkeypatch):
    """Fixture to safely set sys.argv for CLI tests."""

    def _set(args):
        monkeypatch.setattr(sys, "argv", args)

    return _set


@pytest.fixture
def mock_credentials(monkeypatch):
    """Mock environment credentials for Internet Archive API."""
    monkeypatch.setattr(
        "wayback_machine_archiver.archiver.os.getenv",
        lambda key, default=None: DUMMY_CREDENTIALS
        if key in CREDENTIAL_ENV_VARS
        else default,
    )


@pytest.fixture
def mock_no_credentials(monkeypatch):
    """Mock missing environment credentials."""
    monkeypatch.setattr(
        "wayback_machine_archiver.archiver.os.getenv",
        lambda key, default=None: default,
    )


# --- Tests for logging configuration ---


@pytest.mark.parametrize(
    "input_level, expected_level",
    [("info", "INFO"), ("DEBUG", "DEBUG")],
)
@mock.patch("wayback_machine_archiver.archiver.process_sitemaps", return_value=set())
@mock.patch("wayback_machine_archiver.archiver.run_archive_workflow")
@mock.patch("wayback_machine_archiver.archiver.logging.basicConfig")
def test_log_level(
    mock_basic_config,
    mock_workflow,
    mock_sitemaps,
    input_level,
    expected_level,
    cli_args,
    mock_credentials,
):
    """Verify that the --log argument is case-insensitive."""
    cli_args(["archiver", "http://test.com", "--log", input_level])
    main()
    mock_basic_config.assert_called_once_with(level=expected_level, filename=None)


@mock.patch("wayback_machine_archiver.archiver.process_sitemaps", return_value=set())
@mock.patch("wayback_machine_archiver.archiver.run_archive_workflow")
@mock.patch("wayback_machine_archiver.archiver.logging.basicConfig")
def test_log_to_file(
    mock_basic_config, mock_workflow, mock_sitemaps, cli_args, mock_credentials
):
    """Verify that --log-to-file passes the filename to the logging config."""
    log_file = "archive.log"
    cli_args(["archiver", "http://test.com", "--log-to-file", log_file])
    main()
    mock_basic_config.assert_called_once_with(level=logging.WARNING, filename=log_file)


# --- Tests for rate limiting ---


@pytest.mark.parametrize(
    "user_input, expected_wait",
    [(2, 5), (10, 10)],
)
@mock.patch("wayback_machine_archiver.archiver.process_sitemaps", return_value=set())
@mock.patch("wayback_machine_archiver.archiver.run_archive_workflow")
def test_rate_limit_override(
    mock_workflow, mock_sitemaps, user_input, expected_wait, cli_args, mock_credentials
):
    """Verify the script enforces the minimum rate-limit for authenticated users."""
    cli_args(["archiver", "http://test.com", "--rate-limit-wait", str(user_input)])
    main()
    # The third argument to run_archive_workflow is the rate limit
    final_rate_limit = mock_workflow.call_args[0][2]
    assert final_rate_limit == expected_wait


# --- Tests for credential handling ---


def test_version_action_exits(cli_args):
    """Verify that the --version argument exits the program."""
    cli_args(["archiver", "--version"])
    with pytest.raises(SystemExit):
        main()


@mock.patch("wayback_machine_archiver.archiver.logging.error")
def test_main_exits_if_no_credentials(
    mock_logging_error, cli_args, mock_no_credentials
):
    """Verify the script raises SystemExit if credentials are missing."""
    cli_args(["archiver", "http://test.com"])
    with pytest.raises(SystemExit) as e:
        main()

    assert e.value.code == 1
    assert mock_logging_error.call_count > 0


# --- Tests for API option parsing ---


def test_api_option_flags_are_parsed_correctly():
    """
    Directly tests the parser to ensure all API flags are correctly defined
    and their default values are as expected.
    """
    parser = create_parser()

    # Test default values (when no flags are passed)
    args = parser.parse_args([])
    assert args.capture_all is False
    assert args.capture_outlinks is False
    assert args.capture_screenshot is False
    assert args.delay_wb_availability is False
    assert args.force_get is False
    assert args.skip_first_archive is False
    assert args.email_result is False
    assert args.if_not_archived_within is None
    assert args.js_behavior_timeout is None
    assert args.capture_cookie is None
    assert args.use_user_agent is None

    # Test boolean flags are set to True
    args = parser.parse_args(
        [
            "--capture-all",
            "--capture-outlinks",
            "--capture-screenshot",
            "--delay-wb-availability",
            "--force-get",
            "--skip-first-archive",
            "--email-result",
        ]
    )
    assert args.capture_all is True
    assert args.capture_outlinks is True
    assert args.capture_screenshot is True
    assert args.delay_wb_availability is True
    assert args.force_get is True
    assert args.skip_first_archive is True
    assert args.email_result is True

    # Test value-based flags
    args = parser.parse_args(
        [
            "--if-not-archived-within",
            "10d 5h",
            "--js-behavior-timeout",
            "25",
            "--capture-cookie",
            "name=value",
            "--user-agent",
            "MyTestAgent/1.0",
        ]
    )
    assert args.if_not_archived_within == "10d 5h"
    assert args.js_behavior_timeout == 25
    assert args.capture_cookie == "name=value"
    assert args.use_user_agent == "MyTestAgent/1.0"


# --- Tests for URL validation ---


@pytest.mark.parametrize(
    "url,expected",
    [
        ("https://example.com", True),
        ("http://example.com/page", True),
        ("https://example.com/path?query=1", True),
        ("http://localhost:8080", True),
        ("ftp://example.com", False),  # Wrong scheme
        ("example.com", False),  # No scheme
        ("not a url", False),  # Invalid
        ("", False),  # Empty
        ("://missing-scheme.com", False),  # Missing scheme
        ("https://", False),  # No netloc
    ],
    ids=[
        "https_valid",
        "http_with_path",
        "https_with_query",
        "localhost_with_port",
        "ftp_invalid_scheme",
        "no_scheme",
        "not_a_url",
        "empty_string",
        "missing_scheme",
        "no_netloc",
    ],
)
def test_is_valid_url(url, expected):
    """Verify URL validation accepts http/https and rejects invalid URLs."""
    assert _is_valid_url(url) == expected


@mock.patch("wayback_machine_archiver.archiver.process_sitemaps", return_value=set())
@mock.patch("wayback_machine_archiver.archiver.run_archive_workflow")
def test_invalid_urls_are_filtered_with_warning(
    mock_workflow, mock_sitemaps, cli_args, mock_credentials, caplog
):
    """Verify that invalid URLs are filtered out and logged as warnings."""
    cli_args(["archiver", "https://valid.com", "not-a-url", "ftp://wrong.com"])

    with caplog.at_level(logging.WARNING):
        main()

    # Only the valid URL should be passed to the workflow
    passed_urls = mock_workflow.call_args[0][1]
    assert set(passed_urls) == {"https://valid.com"}

    # Invalid URLs should be logged as warnings
    assert "not-a-url" in caplog.text
    assert "ftp://wrong.com" in caplog.text
