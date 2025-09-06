import sys
from unittest import mock
from wayback_machine_archiver.archiver import main

# This test file now mocks the main workflow and assumes credentials are present
# to test the URL gathering and shuffling logic.


@mock.patch("wayback_machine_archiver.archiver.process_sitemaps", return_value=set())
@mock.patch("wayback_machine_archiver.archiver.run_archive_workflow")
@mock.patch("wayback_machine_archiver.archiver.os.getenv", return_value="dummy_key")
@mock.patch("wayback_machine_archiver.archiver.random.shuffle")
def test_random_order_flag_shuffles_urls(
    mock_shuffle, mock_getenv, mock_workflow, mock_sitemaps
):
    """Verify that when --random-order is passed, random.shuffle is called."""
    urls_to_archive = ["http://test.com/a", "http://test.com/b"]
    sys.argv = ["archiver", "--random-order"] + urls_to_archive
    main()
    mock_shuffle.assert_called_once()
    # Check that the workflow was called with the list of URLs
    # The second argument to the mock_workflow call is the list of URLs.
    assert mock_workflow.call_args[0][1] == urls_to_archive


@mock.patch("wayback_machine_archiver.archiver.process_sitemaps", return_value=set())
@mock.patch("wayback_machine_archiver.archiver.run_archive_workflow")
@mock.patch("wayback_machine_archiver.archiver.os.getenv", return_value="dummy_key")
@mock.patch("wayback_machine_archiver.archiver.random.shuffle")
def test_default_order_does_not_shuffle(
    mock_shuffle, mock_getenv, mock_workflow, mock_sitemaps
):
    """Verify that without --random-order, shuffle is not called."""
    urls_to_archive = ["http://test.com/a", "http://test.com/b"]
    sys.argv = ["archiver"] + urls_to_archive
    main()
    mock_shuffle.assert_not_called()
    assert mock_workflow.call_args[0][1] == urls_to_archive
