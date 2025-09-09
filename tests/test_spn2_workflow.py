import logging
from unittest import mock
import pytest
import time
from wayback_machine_archiver.workflow import (
    _submit_next_url,
    _poll_pending_jobs,
    run_archive_workflow,
    PERMANENT_ERROR_MESSAGES,
    TRANSIENT_ERROR_MESSAGES,
)

# --- Tests for _submit_next_url ---


def test_submit_next_url_success():
    """
    Verify that a successful submission adds the job_id to the pending_jobs
    dictionary, consumes the URL, and clears the attempts tracker for that URL.
    """
    mock_client = mock.Mock()
    mock_client.submit_capture.return_value = "job-123"

    urls_to_process = ["http://example.com"]
    pending_jobs = {}
    # Simulate a previous failure to ensure the tracker is cleared on success
    submission_attempts = {"http://example.com": 1}

    _submit_next_url(
        urls_to_process,
        mock_client,
        pending_jobs,
        5,
        submission_attempts,
        api_params={},
    )

    # Assertions
    mock_client.submit_capture.assert_called_once_with(
        "http://example.com", rate_limit_wait=5, api_params={}
    )
    # --- Check the new data structure ---
    assert "job-123" in pending_jobs
    assert pending_jobs["job-123"]["url"] == "http://example.com"
    assert "submitted_at" in pending_jobs["job-123"]
    assert not urls_to_process, "URL should have been consumed from the list"
    assert "http://example.com" not in submission_attempts, (
        "Attempts tracker should be cleared on success"
    )


def test_submit_next_url_failure_requeues_and_tracks_attempt():
    """
    Verify that a failed submission re-queues the URL at the end of the list
    and increments its attempt count.
    """
    mock_client = mock.Mock()
    mock_client.submit_capture.side_effect = Exception("API Error")

    urls_to_process = ["http://a.com", "http://b.com"]
    pending_jobs = {}
    submission_attempts = {}

    _submit_next_url(
        urls_to_process,
        mock_client,
        pending_jobs,
        5,
        submission_attempts,
        api_params={},
    )

    # Assertions
    assert not pending_jobs, "No job should have been added on failure"
    assert urls_to_process == ["http://b.com", "http://a.com"], (
        "Failed URL should be at the end of the list"
    )
    assert submission_attempts == {"http://a.com": 1}, (
        "Attempt count should be incremented"
    )


def test_submit_next_url_gives_up_after_max_retries():
    """
    Verify that if a URL has reached its max retry count, it is not
    re-queued and the submission is not attempted.
    """
    mock_client = mock.Mock()

    urls_to_process = ["http://will-fail.com"]
    pending_jobs = {}
    # Simulate that the URL has already failed 3 times
    submission_attempts = {"http://will-fail.com": 3}

    _submit_next_url(
        urls_to_process,
        mock_client,
        pending_jobs,
        5,
        submission_attempts,
        api_params={},
        max_retries=3,
    )

    # Assertions
    mock_client.submit_capture.assert_not_called()
    assert not pending_jobs
    assert not urls_to_process, "URL should be consumed but not re-queued"
    assert submission_attempts == {"http://will-fail.com": 4}, (
        "Attempt count is still updated"
    )


def test_submit_next_url_passes_api_params_to_client():
    """
    Verify that the api_params dictionary is correctly passed to the client's
    submit_capture method.
    """
    mock_client = mock.Mock()
    mock_client.submit_capture.return_value = "job-123"
    urls_to_process = ["http://example.com"]
    pending_jobs = {}
    submission_attempts = {}
    api_params = {"capture_screenshot": "1", "force_get": "1"}

    _submit_next_url(
        urls_to_process,
        mock_client,
        pending_jobs,
        0,
        submission_attempts,
        api_params,
    )

    mock_client.submit_capture.assert_called_once_with(
        "http://example.com", rate_limit_wait=0, api_params=api_params
    )


# --- Tests for _poll_pending_jobs ---


@mock.patch("wayback_machine_archiver.workflow.time.sleep")
def test_poll_uses_batch_and_removes_completed_jobs(mock_sleep):
    """
    Verify that jobs with 'success' or 'error' status are removed from the
    pending list via the batch endpoint, while 'pending' jobs remain.
    """
    mock_client = mock.Mock()
    # Define the return value for the single batch request
    mock_client.check_status_batch.return_value = [
        {"status": "success", "job_id": "job-success", "timestamp": "20250101"},
        {"status": "error", "job_id": "job-error", "message": "Too many redirects."},
        {"status": "pending", "job_id": "job-pending"},
    ]

    # --- Use the new data structure for pending_jobs ---
    now = time.time()
    pending_jobs = {
        "job-success": {"url": "http://a.com", "submitted_at": now},
        "job-error": {"url": "http://b.com", "submitted_at": now},
        "job-pending": {"url": "http://c.com", "submitted_at": now},
    }

    # --- Provide the new required arguments ---
    successful, failed, requeued = _poll_pending_jobs(
        mock_client,
        pending_jobs,
        transient_error_retries={},
        max_transient_retries=3,
        job_timeout_sec=7200,
    )

    # Assertions
    mock_client.check_status_batch.assert_called_once_with(
        ["job-success", "job-error", "job-pending"]
    )
    # --- Check the new data structure in the assertion ---
    assert list(pending_jobs.keys()) == ["job-pending"]
    assert pending_jobs["job-pending"]["url"] == "http://c.com"
    assert successful == ["http://a.com"]
    assert failed == ["http://b.com"]
    assert requeued == []
    mock_sleep.assert_called_once()


@pytest.mark.parametrize(
    "status_ext, expected_outcome, expected_log_level, expected_log_snippet",
    [
        (
            "error:service-unavailable",
            "requeue",
            logging.WARNING,
            TRANSIENT_ERROR_MESSAGES["error:service-unavailable"],
        ),
        (
            "error:not-found",
            "fail",
            logging.ERROR,
            PERMANENT_ERROR_MESSAGES["error:not-found"],
        ),
        (
            "error:some-new-unseen-error",
            "fail",
            logging.ERROR,
            "An unrecoverable error occurred.",
        ),
    ],
)
@mock.patch("wayback_machine_archiver.workflow.time.sleep")
def test_poll_pending_jobs_handles_errors_intelligently(
    mock_sleep,
    caplog,
    status_ext,
    expected_outcome,
    expected_log_level,
    expected_log_snippet,
):
    """
    Verify that _poll_pending_jobs correctly categorizes errors as either
    transient (re-queue) or permanent (fail) and logs helpful messages.
    """
    mock_client = mock.Mock()
    mock_client.check_status_batch.return_value = [
        {
            "status": "error",
            "job_id": "job-1",
            "status_ext": status_ext,
            "message": "API message",
        }
    ]
    # --- Use the new data structure for pending_jobs ---
    pending_jobs = {"job-1": {"url": "http://example.com", "submitted_at": time.time()}}

    with caplog.at_level(logging.WARNING):
        # --- Provide the new required arguments ---
        successful, failed, requeued = _poll_pending_jobs(
            mock_client,
            pending_jobs,
            transient_error_retries={},
            max_transient_retries=3,
            job_timeout_sec=7200,
        )

    assert not successful
    if expected_outcome == "requeue":
        assert requeued == ["http://example.com"]
        assert not failed
    else:  # fail
        assert not requeued
        assert failed == ["http://example.com"]

    assert len(caplog.records) == 1
    log_record = caplog.records[0]
    assert log_record.levelno == expected_log_level
    assert expected_log_snippet in log_record.message


# --- Corrected test for run_archive_workflow dynamic polling ---


@mock.patch("wayback_machine_archiver.workflow.time.sleep")
@mock.patch("wayback_machine_archiver.workflow._poll_pending_jobs")
@mock.patch("wayback_machine_archiver.workflow._submit_next_url")
def test_run_archive_workflow_dynamic_polling_is_fast_and_correct(
    mock_submit, mock_poll, mock_sleep
):
    """
    Verify that the polling wait time increases exponentially when jobs are pending
    and the submission queue is empty, and that the test runs quickly.
    """
    mock_client = mock.Mock()
    initial_urls = ["http://a.com"]
    # Use a mutable list for the test to simulate its modification by _submit_next_url
    urls_to_process_list = list(initial_urls)
    rate_limit_in_sec = 0
    api_params = {}

    # Configure mock_submit to simulate a successful submission
    # It needs to modify the urls_to_process_list and pending_jobs_dict passed to it
    def submit_side_effect(urls_proc, client_arg, pending_jobs_dict, *args, **kwargs):
        url = urls_proc.pop(0)  # Remove the URL from the list
        job_id = f"job-{url}"
        # --- Use the new data structure ---
        pending_jobs_dict[job_id] = {"url": url, "submitted_at": time.time()}
        return job_id

    mock_submit.side_effect = submit_side_effect

    # Configure mock_poll to simulate jobs staying pending, then succeeding
    poll_calls = 0

    def poll_side_effect(client_arg, pending_jobs_dict, *args, **kwargs):
        nonlocal poll_calls
        poll_calls += 1
        if poll_calls <= 3:  # Simulate pending for 3 calls
            return [], [], []  # No success, no failure, no requeue
        else:  # Simulate success on the 4th call
            # --- Extract URLs from the new data structure ---
            successful_urls = [job["url"] for job in pending_jobs_dict.values()]
            pending_jobs_dict.clear()
            return successful_urls, [], []

    mock_poll.side_effect = poll_side_effect

    # Call the main workflow function
    run_archive_workflow(
        mock_client, urls_to_process_list, rate_limit_in_sec, api_params
    )

    # Assertions
    # Check the calls to time.sleep
    # We expect sleep to be called between polling cycles when the submission
    # queue is empty.
    # Cycle 1: Submits URL. Polls. Loop continues.
    # Cycle 2: No URLs to submit. Polls. Sleeps for 5s.
    # Cycle 3: No URLs to submit. Polls. Sleeps for 7s (5 * 1.5).
    # Cycle 4: No URLs to submit. Polls. Sleeps for 10s (7 * 1.5).
    # Cycle 5: No URLs to submit. Polls (job succeeds). Loop terminates.
    # We filter out the small 0.2s sleeps that happen inside _poll_pending_jobs.
    sleep_calls = [call[0][0] for call in mock_sleep.call_args_list if call[0][0] > 1]

    assert sleep_calls == [5, 7, 10]
    assert mock_submit.call_count == 1
    # The poll side effect now runs 4 times to get to the success case
    assert mock_poll.call_count == 4
    assert not urls_to_process_list  # Ensure the initial URL list is empty


def test_poll_gives_up_after_max_transient_retries(caplog):
    """
    Verify that if a URL fails with a transient error more times than allowed,
    it is marked as a permanent failure and not re-queued.
    """
    mock_client = mock.Mock()
    mock_client.check_status_batch.return_value = [
        {
            "status": "error",
            "job_id": "job-1",
            "status_ext": "error:service-unavailable",  # A transient error
            "message": "API message",
        }
    ]

    url = "http://example.com"
    max_retries = 3

    # Simulate that this URL has already failed 3 times with a transient error
    transient_error_retries = {url: 3}
    pending_jobs = {"job-1": {"url": url, "submitted_at": time.time()}}

    with caplog.at_level(logging.INFO):
        successful, failed, requeued = _poll_pending_jobs(
            mock_client,
            pending_jobs,
            transient_error_retries,
            max_transient_retries=max_retries,
            job_timeout_sec=7200,
        )

    # Assertions
    assert not successful
    assert not requeued, "URL should not have been re-queued"
    assert failed == [url], "URL should have been marked as failed"
    assert "Marking as a permanent failure" in caplog.text


def test_poll_fails_job_after_timeout(caplog):
    """
    Verify that a job that remains in a 'pending' state for longer than the
    timeout period is marked as a failure.
    """
    mock_client = mock.Mock()
    mock_client.check_status_batch.return_value = [
        {"status": "pending", "job_id": "job-stuck"}
    ]

    url = "http://stuck.com"
    timeout_sec = 3600  # 1 hour

    # Simulate a job that was submitted long ago, well before the timeout
    stale_timestamp = time.time() - (timeout_sec + 60)
    pending_jobs = {"job-stuck": {"url": url, "submitted_at": stale_timestamp}}

    with caplog.at_level(logging.INFO):
        successful, failed, requeued = _poll_pending_jobs(
            mock_client,
            pending_jobs,
            transient_error_retries={},
            max_transient_retries=3,
            job_timeout_sec=timeout_sec,
        )

    # Assertions
    assert not successful
    assert not requeued
    assert failed == [url], "Stuck job should have been marked as failed"
    assert "timed out after being pending" in caplog.text
