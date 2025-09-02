import sys
from unittest import mock
import pytest
import logging
from wayback_machine_archiver.archiver import main


# We mock the clients to prevent any actual archiving logic from running.
# This keeps the tests focused purely on the CLI parsing and its direct effects.


@mock.patch("wayback_machine_archiver.archiver.os.getenv", return_value=None)
@mock.patch("wayback_machine_archiver.archiver.LegacyClient")
@mock.patch("wayback_machine_archiver.archiver.logging.basicConfig")
@pytest.mark.parametrize(
    "input_level, expected_level",
    [
        ("info", "INFO"),
        ("DEBUG", "DEBUG"),
        ("warning", "WARNING"),
        ("ErRoR", "ERROR"),
    ],
)
def test_log_level_is_case_insensitive(
    mock_basic_config,
    mock_legacy_client,
    mock_getenv,
    input_level,
    expected_level,
):
    """
    Verify that the --log argument is case-insensitive.
    """
    # Arrange
    sys.argv = ["archiver", "--log", input_level]

    # Act
    main()

    # Assert
    mock_basic_config.assert_called_once_with(level=expected_level, filename=None)


def test_version_action_exits():
    """
    Verify that the --version argument exits the program.
    """
    # Arrange
    sys.argv = ["archiver", "--version"]

    # Act & Assert: argparse's version action calls sys.exit, which raises SystemExit
    with pytest.raises(SystemExit):
        main()


@mock.patch("wayback_machine_archiver.archiver.os.getenv", return_value=None)
@mock.patch("wayback_machine_archiver.archiver.LegacyClient")
@mock.patch("wayback_machine_archiver.archiver.logging.basicConfig")
def test_log_to_file_sets_filename(mock_basic_config, mock_legacy_client, mock_getenv):
    """
    Verify that --log-to-file passes the filename to the logging config.
    """
    # Arrange
    log_file = "archive.log"
    sys.argv = ["archiver", "--log-to-file", log_file]

    # Act
    main()

    # Assert
    mock_basic_config.assert_called_once_with(level=logging.WARNING, filename=log_file)


@pytest.mark.parametrize(
    "creds_exist, user_input, expected_wait",
    [
        (True, 2, 5),
        (True, 10, 10),
        (False, 10, 15),
        (False, 20, 20),
    ],
)
@mock.patch("wayback_machine_archiver.archiver.SPN2Client")
@mock.patch("wayback_machine_archiver.archiver.LegacyClient")
def test_rate_limit_override(
    mock_legacy_client, mock_spn2_client, creds_exist, user_input, expected_wait
):
    """
    Verify that the script enforces the minimum rate-limit wait time.
    """
    # Arrange: Mock getenv to simulate credentials being present or not
    with mock.patch(
        "wayback_machine_archiver.archiver.os.getenv",
        return_value="dummy_key" if creds_exist else None,
    ):
        # Configure the SPN2 client's submit_capture to return None.
        # This prevents the test from entering the infinite polling loop.
        mock_spn2_client.return_value.submit_capture.return_value = None

        sys.argv = ["archiver", "http://test.com", "--rate-limit-wait", str(user_input)]

        # Act
        main()

        # Assert
        if creds_exist:
            mock_spn2_client.return_value.submit_capture.assert_called_once_with(
                "http://test.com", rate_limit_wait=expected_wait
            )
            mock_legacy_client.assert_not_called()
        else:
            # Note: The legacy client gets a pre-formatted URL
            formatted_url = "https://web.archive.org/save/http://test.com"
            mock_legacy_client.return_value.archive.assert_called_once_with(
                formatted_url, rate_limit_wait=expected_wait
            )
            mock_spn2_client.assert_not_called()
