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

    # Check for membership, not order, by comparing sets.
    # The second argument to the mock_workflow call is the list of URLs.
    passed_urls = mock_workflow.call_args[0][1]
    assert set(passed_urls) == set(urls_to_archive)


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

    # Check for membership, not order, by comparing sets.
    passed_urls = mock_workflow.call_args[0][1]
    assert set(passed_urls) == set(urls_to_archive)


@mock.patch("wayback_machine_archiver.archiver.process_sitemaps", return_value=set())
@mock.patch("wayback_machine_archiver.archiver.run_archive_workflow")
@mock.patch("wayback_machine_archiver.archiver.os.getenv", return_value="dummy_key")
def test_main_builds_and_passes_api_params(mock_getenv, mock_workflow, mock_sitemaps):
    """
    Verify that main() correctly constructs the api_params dictionary from CLI
    flags and passes it to the workflow.
    """
    sys.argv = [
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
    main()

    # The fourth argument to the mock_workflow call is the api_params dict.
    passed_params = mock_workflow.call_args[0][3]
    expected_params = {
        "capture_screenshot": "1",
        "js_behavior_timeout": 10,
        "if_not_archived_within": "5d",
        "use_user_agent": "TestBot/1.0",
    }
    assert passed_params == expected_params
