import sys
from unittest import mock
import pytest
import logging
from wayback_machine_archiver.archiver import main

# This test file now mocks the main workflow and any I/O functions
# to keep the tests focused purely on the CLI argument parsing logic.


@mock.patch("wayback_machine_archiver.archiver.process_sitemaps", return_value=set())
@mock.patch("wayback_machine_archiver.archiver.run_archive_workflow")
@mock.patch("wayback_machine_archiver.archiver.logging.basicConfig")
@pytest.mark.parametrize(
    "input_level, expected_level",
    [("info", "INFO"), ("DEBUG", "DEBUG")],
)
def test_log_level(
    mock_basic_config, mock_workflow, mock_sitemaps, input_level, expected_level
):
    """Verify that the --log argument is case-insensitive."""
    with mock.patch(
        "wayback_machine_archiver.archiver.os.getenv", return_value="dummy_key"
    ):
        sys.argv = ["archiver", "http://test.com", "--log", input_level]
        main()
        mock_basic_config.assert_called_once_with(level=expected_level, filename=None)


def test_version_action_exits():
    """Verify that the --version argument exits the program."""
    sys.argv = ["archiver", "--version"]
    with pytest.raises(SystemExit):
        main()


@mock.patch("wayback_machine_archiver.archiver.process_sitemaps", return_value=set())
@mock.patch("wayback_machine_archiver.archiver.run_archive_workflow")
@mock.patch("wayback_machine_archiver.archiver.logging.basicConfig")
def test_log_to_file(mock_basic_config, mock_workflow, mock_sitemaps):
    """Verify that --log-to-file passes the filename to the logging config."""
    with mock.patch(
        "wayback_machine_archiver.archiver.os.getenv", return_value="dummy_key"
    ):
        log_file = "archive.log"
        sys.argv = ["archiver", "http://test.com", "--log-to-file", log_file]
        main()
        mock_basic_config.assert_called_once_with(
            level=logging.WARNING, filename=log_file
        )


@pytest.mark.parametrize(
    "user_input, expected_wait",
    [(2, 5), (10, 10)],
)
@mock.patch("wayback_machine_archiver.archiver.process_sitemaps", return_value=set())
@mock.patch("wayback_machine_archiver.archiver.run_archive_workflow")
def test_rate_limit_override(mock_workflow, mock_sitemaps, user_input, expected_wait):
    """Verify the script enforces the minimum rate-limit for authenticated users."""
    with mock.patch(
        "wayback_machine_archiver.archiver.os.getenv", return_value="dummy_key"
    ):
        sys.argv = ["archiver", "http://test.com", "--rate-limit-wait", str(user_input)]
        main()
        # The third argument to the mock_workflow call is the rate limit.
        final_rate_limit = mock_workflow.call_args[0][2]
        assert final_rate_limit == expected_wait


@mock.patch("wayback_machine_archiver.archiver.logging.error")
def test_main_exits_if_no_credentials(mock_logging_error):
    """Verify the script raises SystemExit if getenv returns None for credentials."""
    with mock.patch("wayback_machine_archiver.archiver.os.getenv", return_value=None):
        sys.argv = ["archiver", "http://test.com"]
        with pytest.raises(SystemExit) as e:
            main()

        # Check that the exit code is 1 (error)
        assert e.value.code == 1
        # Check that we logged an error message to the user
        assert mock_logging_error.call_count > 0
