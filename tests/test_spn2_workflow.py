from unittest import mock
import pytest
from wayback_machine_archiver.archiver import _submit_next_url, _poll_pending_jobs

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

    _submit_next_url(urls_to_process, mock_client, pending_jobs, 5, submission_attempts)

    # Assertions
    mock_client.submit_capture.assert_called_once_with(
        "http://example.com", rate_limit_wait=5
    )
    assert pending_jobs == {"job-123": "http://example.com"}
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

    _submit_next_url(urls_to_process, mock_client, pending_jobs, 5, submission_attempts)

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
        max_retries=3,
    )

    # Assertions
    mock_client.submit_capture.assert_not_called()
    assert not pending_jobs
    assert not urls_to_process, "URL should be consumed but not re-queued"
    assert submission_attempts == {"http://will-fail.com": 4}, (
        "Attempt count is still updated"
    )


# --- Tests for _poll_pending_jobs ---


@mock.patch("wayback_machine_archiver.archiver.time.sleep")
def test_poll_removes_completed_jobs(mock_sleep):
    """
    Verify that jobs with 'success' or 'error' status are removed from the
    pending list, while 'pending' jobs remain.
    """
    mock_client = mock.Mock()
    # Define the return values for consecutive calls to check_status
    mock_client.check_status.side_effect = [
        {"status": "success", "original_url": "http://a.com", "timestamp": "20250101"},
        {"status": "error", "message": "Too many redirects."},
        {"status": "pending"},
    ]

    pending_jobs = {
        "job-success": "http://a.com",
        "job-error": "http://b.com",
        "job-pending": "http://c.com",
    }

    _poll_pending_jobs(mock_client, pending_jobs)

    # Assertions
    assert pending_jobs == {"job-pending": "http://c.com"}, (
        "Only the pending job should remain"
    )
    assert mock_client.check_status.call_count == 3
    assert mock_sleep.call_count == 3, "Should sleep after each poll attempt"


@mock.patch("wayback_machine_archiver.archiver.time.sleep")
def test_poll_handles_exception_during_status_check(mock_sleep):
    """
    Verify that if checking a job's status raises an exception, the job is
    removed from the pending list to prevent repeated errors.
    """
    mock_client = mock.Mock()
    mock_client.check_status.side_effect = Exception("Network Error")

    pending_jobs = {"job-will-fail": "http://example.com"}

    _poll_pending_jobs(mock_client, pending_jobs)

    # Assertions
    assert not pending_jobs, "Job that caused an exception should be removed"
    mock_client.check_status.assert_called_once_with("job-will-fail")
    mock_sleep.assert_called_once()
