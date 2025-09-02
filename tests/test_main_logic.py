import sys
from unittest import mock

from wayback_machine_archiver.archiver import main, format_archive_url


@mock.patch("wayback_machine_archiver.archiver.LegacyClient")
@mock.patch("wayback_machine_archiver.archiver.os.getenv", return_value=None)
@mock.patch("wayback_machine_archiver.archiver.random.shuffle")
def test_random_order_flag_shuffles_urls(mock_shuffle, mock_getenv, mock_legacy_client):
    """
    Verify that when --random-order is passed, random.shuffle is called
    and the client's archive method is called for each URL.
    """
    # Arrange: Simulate command-line arguments
    urls_to_archive = ["http://test.com/a", "http://test.com/b"]
    sys.argv = ["archiver", "--random-order"] + urls_to_archive

    # Get a reference to the mock client instance that main() will create
    mock_client_instance = mock_legacy_client.return_value

    # Act: Run the main function
    main()

    # Assert: Check that our mocks were called as expected
    mock_shuffle.assert_called_once()
    assert mock_client_instance.archive.call_count == len(urls_to_archive)

    # Verify the content of the calls is correct
    called_urls = {call.args[0] for call in mock_client_instance.archive.call_args_list}
    expected_urls = {format_archive_url(u) for u in urls_to_archive}
    assert called_urls == expected_urls


@mock.patch("wayback_machine_archiver.archiver.LegacyClient")
@mock.patch("wayback_machine_archiver.archiver.os.getenv", return_value=None)
@mock.patch("wayback_machine_archiver.archiver.random.shuffle")
def test_default_order_does_not_shuffle(mock_shuffle, mock_getenv, mock_legacy_client):
    """
    Verify that without --random-order, shuffle is not called,
    but the client's archive method is still called for each URL.
    """
    # Arrange: Simulate command-line arguments
    urls_to_archive = ["http://test.com/a", "http://test.com/b"]
    sys.argv = ["archiver"] + urls_to_archive

    mock_client_instance = mock_legacy_client.return_value

    # Act: Run the main function
    main()

    # Assert: Check that shuffle was NOT called, but the client was.
    mock_shuffle.assert_not_called()
    assert mock_client_instance.archive.call_count == len(urls_to_archive)

    # Verify the content of the calls is correct
    called_urls = {call.args[0] for call in mock_client_instance.archive.call_args_list}
    expected_urls = {format_archive_url(u) for u in urls_to_archive}
    assert called_urls == expected_urls
