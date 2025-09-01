import sys
from unittest import mock

from wayback_machine_archiver.archiver import main, format_archive_url


# We patch the Pool and shuffle functions to isolate our test
# to the logic inside main(), without creating real processes or shuffling.
@mock.patch("wayback_machine_archiver.archiver.mp.Pool")
@mock.patch("wayback_machine_archiver.archiver.random.shuffle")
def test_random_order_flag_shuffles_urls(mock_shuffle, mock_pool):
    """
    Verify that when --random-order is passed, random.shuffle is called.
    """
    # Arrange: Simulate command-line arguments
    urls_to_archive = ["http://test.com/a", "http://test.com/b"]
    sys.argv = ["archiver", "--random-order"] + urls_to_archive

    # We need to get a reference to the mock Pool instance to check its methods
    mock_pool_instance = mock_pool.return_value

    # Act: Run the main function
    main()

    # Assert: Check that our mocks were called as expected
    mock_shuffle.assert_called_once()
    mock_pool_instance.map.assert_called_once()

    # Get the list of URLs that was passed to the pool
    # call_args[0] is the tuple of positional args, and the list is the second one
    url_list_passed_to_pool = mock_pool_instance.map.call_args[0][1]

    # Verify the content of the list is correct
    expected_urls = {format_archive_url(u) for u in urls_to_archive}
    assert set(url_list_passed_to_pool) == expected_urls


@mock.patch("wayback_machine_archiver.archiver.mp.Pool")
@mock.patch("wayback_machine_archiver.archiver.random.shuffle")
def test_default_order_does_not_shuffle(mock_shuffle, mock_pool):
    """
    Verify that without the --random-order flag, random.shuffle is NOT called.
    """
    # Arrange: Simulate command-line arguments without the flag
    urls_to_archive = ["http://test.com/a", "http://test.com/b"]
    sys.argv = ["archiver"] + urls_to_archive

    mock_pool_instance = mock_pool.return_value

    # Act: Run the main function
    main()

    # Assert: Check that shuffle was NOT called, but the pool still was.
    mock_shuffle.assert_not_called()
    mock_pool_instance.map.assert_called_once()

    # Get the list of URLs that was passed to the pool
    url_list_passed_to_pool = mock_pool_instance.map.call_args[0][1]

    # Verify the content of the list is correct
    expected_urls = {format_archive_url(u) for u in urls_to_archive}
    assert set(url_list_passed_to_pool) == expected_urls
