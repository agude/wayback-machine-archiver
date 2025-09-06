import logging
import time


def _submit_next_url(
    urls_to_process,
    client,
    pending_jobs,
    rate_limit_in_sec,
    submission_attempts,
    max_retries=3,
):
    """
    Pops the next URL, submits it, and adds its job_id to pending_jobs.
    Returns 'failed' on a definitive failure, otherwise None.
    """
    url = urls_to_process.pop(0)
    attempt_num = submission_attempts.get(url, 0) + 1
    submission_attempts[url] = attempt_num

    if attempt_num > max_retries:
        logging.error("URL %s failed submission %d times, giving up.", url, max_retries)
        return "failed"

    try:
        logging.info("Submitting %s (attempt %d/%d)...", url, attempt_num, max_retries)
        job_id = client.submit_capture(url, rate_limit_wait=rate_limit_in_sec)

        if job_id:
            pending_jobs[job_id] = url
            if url in submission_attempts:
                del submission_attempts[url]
        else:
            # This is the critical fix: Handle cases where the API accepts the
            # request but does not return a job_id, indicating a rejection.
            logging.error(
                "Failed to get a job_id for %s. The API may have rejected it (e.g., rate limit). This will be counted as a failure.",
                url,
            )
            return "failed"

    except Exception as e:
        logging.warning(
            "Failed to submit URL %s: %s. Re-queuing for another attempt.", url, e
        )
        urls_to_process.append(url)

    return None


def _poll_pending_jobs(client, pending_jobs, poll_interval_sec=0.2):
    """
    Checks the status of all pending jobs using a single batch request.
    Returns a tuple of (successful_urls, failed_urls) for completed jobs.
    """
    successful_urls = []
    failed_urls = []

    # Get all job IDs that need to be checked.
    job_ids_to_check = list(pending_jobs.keys())
    if not job_ids_to_check:
        return [], []

    try:
        # Make a single batch request for all pending jobs.
        # The API is expected to return a list of status objects.
        batch_statuses = client.check_status_batch(job_ids_to_check)

        # It's possible the API returns a single object if only one job was queried.
        if not isinstance(batch_statuses, list):
            batch_statuses = [batch_statuses]

        for status_data in batch_statuses:
            job_id = status_data.get("job_id")
            if not job_id or job_id not in pending_jobs:
                continue

            original_url = pending_jobs[job_id]
            status = status_data.get("status")

            if status == "success":
                timestamp = status_data.get("timestamp")
                archive_url = f"https://web.archive.org/web/{timestamp}/{original_url}"
                logging.info("Success for job %s: %s", job_id, archive_url)
                del pending_jobs[job_id]
                successful_urls.append(original_url)
            elif status == "error":
                message = status_data.get("message", "Unknown error")
                logging.error(
                    "Error for job %s (%s): %s", job_id, original_url, message
                )
                del pending_jobs[job_id]
                failed_urls.append(original_url)
            else:
                logging.debug("Job %s (%s) is still pending...", job_id, original_url)

    except Exception as e:
        logging.error(
            "An exception occurred during batch polling: %s. Clearing all pending jobs for this cycle to prevent loops.",
            e,
        )
        # In case of a total failure, we clear the pending jobs to avoid getting stuck.
        failed_urls.extend(pending_jobs.values())
        pending_jobs.clear()

    # A short sleep after each batch poll to be nice to the API.
    time.sleep(poll_interval_sec)

    return successful_urls, failed_urls


def run_archive_workflow(client, urls_to_process, rate_limit_in_sec):
    """Manages the main loop for submitting and polling URLs."""
    pending_jobs = {}
    submission_attempts = {}

    total_urls = len(urls_to_process)
    success_count = 0
    failure_count = 0

    logging.info(
        "Beginning interleaved submission and polling of %d URLs...",
        total_urls,
    )

    while urls_to_process or pending_jobs:
        if urls_to_process:
            status = _submit_next_url(
                urls_to_process,
                client,
                pending_jobs,
                rate_limit_in_sec,
                submission_attempts,
            )
            if status == "failed":
                failure_count += 1

        if pending_jobs:
            successful, failed = _poll_pending_jobs(client, pending_jobs)
            success_count += len(successful)
            failure_count += len(failed)

        if not urls_to_process and pending_jobs:
            wait_time = 5
            logging.info(
                "%d captures remaining, starting next polling cycle in %d seconds...",
                len(pending_jobs),
                wait_time,
            )
            time.sleep(wait_time)

    logging.info("--------------------------------------------------")
    logging.info("Archive workflow complete.")
    logging.info(f"Total URLs processed: {total_urls}")
    logging.info(f"Successful captures: {success_count}")
    logging.info(f"Failed captures: {failure_count}")
    logging.info("--------------------------------------------------")
