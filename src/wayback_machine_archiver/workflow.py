import logging
import time

# A set of transient errors that suggest a retry might be successful.
REQUEUE_ERRORS = {
    "error:bad-gateway",
    "error:bandwidth-limit-exceeded",
    "error:browsing-timeout",
    "error:cannot-fetch",
    "error:capture-location-error",
    "error:celery",
    "error:gateway-timeout",
    "error:internal-server-error",
    "error:invalid-server-response",
    "error:job-failed",
    "error:no-browsers-available",
    "error:protocol-error",
    "error:proxy-error",
    "error:read-timeout",
    "error:service-unavailable",
    "error:soft-time-limit-exceeded",
    "error:too-many-requests",
    "error:user-session-limit",
}

# A map of transient error codes to user-friendly, explanatory messages.
TRANSIENT_ERROR_MESSAGES = {
    "error:bad-gateway": "The server reported a temporary upstream issue (Bad Gateway).",
    "error:bandwidth-limit-exceeded": "The target server has exceeded its bandwidth limit.",
    "error:browsing-timeout": "The headless browser timed out, possibly due to high server load.",
    "error:cannot-fetch": "The Internet Archive's systems are temporarily overloaded.",
    "error:capture-location-error": "An internal Internet Archive system error occurred.",
    "error:celery": "An error occurred in the Internet Archive's internal job queue.",
    "error:gateway-timeout": "The server reported a temporary upstream timeout (Gateway Timeout).",
    "error:internal-server-error": "The Internet Archive's server reported a temporary internal error.",
    "error:invalid-server-response": "The target server sent a malformed response, possibly due to a network glitch.",
    "error:job-failed": "The capture failed due to a generic Internet Archive system error.",
    "error:no-browsers-available": "The Internet Archive's capture browsers are temporarily at capacity.",
    "error:protocol-error": "The HTTP connection was broken, likely due to a network issue.",
    "error:proxy-error": "An internal Internet Archive proxy error occurred.",
    "error:read-timeout": "The connection timed out while reading data from the server.",
    "error:service-unavailable": "The Internet Archive's service is temporarily unavailable.",
    "error:soft-time-limit-exceeded": "The capture took too long and was terminated; a retry may succeed.",
    "error:too-many-requests": "The target server is rate-limiting requests.",
    "error:user-session-limit": "Your Internet Archive account has reached its concurrent job limit.",
}

# A map of permanent error codes to user-friendly, explanatory messages.
PERMANENT_ERROR_MESSAGES = {
    "error:bad-request": "The API reported a bad request. This may be a bug in the archiver script.",
    "error:blocked": "The target site is actively blocking the Internet Archive's requests. To save the block page, use the --capture-all flag.",
    "error:blocked-client-ip": "Your IP address is on a blocklist (e.g., Spamhaus), and the Internet Archive is refusing the request.",
    "error:blocked-url": "This URL is on a blocklist (e.g., a tracking domain) and cannot be archived.",
    "error:filesize-limit": "The file at this URL is larger than the 2GB limit and cannot be archived.",
    "error:ftp-access-denied": "Access to the FTP resource was denied due to a permissions issue.",
    "error:http-version-not-supported": "The target server uses an unsupported HTTP version.",
    "error:invalid-host-resolution": "The domain name could not be found. Check for typos in the URL.",
    "error:invalid-url-syntax": "The URL is malformed. Please check its structure.",
    "error:method-not-allowed": "The server forbids the HTTP method used for archiving. To save this error page, use the --capture-all flag.",
    "error:network-authentication-required": "A captive portal or proxy is requiring authentication. To save the login page, use the --capture-all flag.",
    "error:no-access": "The page is forbidden (403 Forbidden). To save this error page, use the --capture-all flag.",
    "error:not-found": "The page could not be found (404 Not Found). To save this error page, use the --capture-all flag.",
    "error:not-implemented": "The server does not support the functionality required to archive the page.",
    "error:too-many-daily-captures": "This URL has already been captured the maximum number of times today.",
    "error:too-many-redirects": "The URL has too many redirects, likely indicating a redirect loop.",
    "error:unauthorized": "The page requires a login (401 Unauthorized). To save the login/error page, use the --capture-all flag.",
}


def _submit_next_url(
    urls_to_process,
    client,
    pending_jobs,
    rate_limit_in_sec,
    submission_attempts,
    api_params,
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
        job_id = client.submit_capture(
            url, rate_limit_wait=rate_limit_in_sec, api_params=api_params
        )

        if not job_id:
            # The API accepted the request but didn't provide a job_id.
            # This is treated as a transient error to trigger a retry.
            raise ValueError(
                "API did not return a job_id, likely due to rate limiting."
            )

        # --- Store a dictionary with URL and timestamp ---
        pending_jobs[job_id] = {"url": url, "submitted_at": time.time()}
        if url in submission_attempts:
            del submission_attempts[url]

    except ValueError as _:
        # This block specifically catches the "no job_id" case.
        logging.warning(
            "Submission for %s was accepted but no job_id was returned. This can happen under high load or due to rate limits. Re-queuing for another attempt.",
            url,
        )
        urls_to_process.append(url)

    except Exception as e:
        # This block now catches all OTHER submission errors (e.g., network).
        logging.warning(
            "Failed to submit URL %s due to a connection or API error: %s. Re-queuing for another attempt.",
            url,
            e,
        )
        urls_to_process.append(url)

    return None


def _poll_pending_jobs(
    client,
    pending_jobs,
    transient_error_retries,
    max_transient_retries,
    job_timeout_sec,
    poll_interval_sec=0.2,
):
    """
    Checks the status of all pending jobs using a single batch request.
    Returns a tuple of (successful_urls, failed_urls, requeued_urls) for completed jobs.
    """
    successful_urls = []
    failed_urls = []
    requeued_urls = []

    # Get all job IDs that need to be checked.
    job_ids_to_check = list(pending_jobs.keys())
    if not job_ids_to_check:
        return [], [], []

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

            # --- URL is now inside a dictionary ---
            original_url = pending_jobs[job_id]["url"]
            status = status_data.get("status")

            if status == "success":
                timestamp = status_data.get("timestamp")
                archive_url = f"https://web.archive.org/web/{timestamp}/{original_url}"
                logging.info("Success for job %s: %s", job_id, archive_url)
                del pending_jobs[job_id]
                successful_urls.append(original_url)
            elif status == "error":
                status_ext = status_data.get("status_ext")
                api_message = status_data.get("message", "Unknown error")

                if status_ext in REQUEUE_ERRORS:
                    # --- Check if this URL has exceeded its transient retry limit ---
                    retry_count = transient_error_retries.get(original_url, 0) + 1
                    transient_error_retries[original_url] = retry_count

                    if retry_count > max_transient_retries:
                        logging.error(
                            "URL %s failed with a transient error %d times. Marking as a permanent failure. (API code: %s)",
                            original_url,
                            max_transient_retries,
                            status_ext,
                        )
                        del pending_jobs[job_id]
                        failed_urls.append(original_url)
                    else:
                        # --- This is the original re-queue logic ---
                        helpful_message = TRANSIENT_ERROR_MESSAGES.get(
                            status_ext, "A transient error occurred."
                        )
                        logging.warning(
                            "Transient error for %s: %s Re-queuing for another attempt (%d/%d). (API code: %s)",
                            original_url,
                            helpful_message,
                            retry_count,
                            max_transient_retries,
                            status_ext,
                        )
                        del pending_jobs[job_id]
                        requeued_urls.append(original_url)
                else:
                    # Look up the helpful message, with a fallback for unknown permanent errors.
                    helpful_message = PERMANENT_ERROR_MESSAGES.get(
                        status_ext, "An unrecoverable error occurred."
                    )
                    logging.error(
                        "Permanent error for %s: %s (API message: %s)",
                        original_url,
                        helpful_message,
                        api_message,
                    )
                    del pending_jobs[job_id]
                    failed_urls.append(original_url)
            else:
                # --- Check for job timeout if status is pending ---
                submitted_at = pending_jobs[job_id]["submitted_at"]
                job_age = time.time() - submitted_at
                if job_age > job_timeout_sec:
                    logging.error(
                        "Job for %s timed out after being pending for over %d seconds. Marking as failed.",
                        original_url,
                        job_timeout_sec,
                    )
                    del pending_jobs[job_id]
                    failed_urls.append(original_url)
                else:
                    logging.debug(
                        "Job %s (%s) is still pending...", job_id, original_url
                    )

    except Exception as e:
        logging.error(
            "An exception occurred during batch polling: %s. Clearing all pending jobs for this cycle to prevent loops.",
            e,
        )
        # --- Must extract URLs from the dictionary values ---
        failed_urls.extend([job["url"] for job in pending_jobs.values()])
        pending_jobs.clear()

    # A short sleep after each batch poll to be nice to the API.
    time.sleep(poll_interval_sec)

    return successful_urls, failed_urls, requeued_urls


def run_archive_workflow(client, urls_to_process, rate_limit_in_sec, api_params):
    """Manages the main loop for submitting and polling URLs."""
    pending_jobs = {}
    submission_attempts = {}
    # --- Dictionary to track retries for transient polling errors ---
    transient_error_retries = {}
    MAX_TRANSIENT_RETRIES = 3
    # --- Timeout for jobs stuck in pending state ---
    JOB_TIMEOUT_SEC = 7200  # 2 hours

    total_urls = len(urls_to_process)
    success_count = 0
    failure_count = 0

    # --- Variables for dynamic polling ---
    INITIAL_POLLING_WAIT = 5
    MAX_POLLING_WAIT = 60
    POLLING_BACKOFF_FACTOR = 1.5
    polling_wait_time = INITIAL_POLLING_WAIT

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
                api_params,
            )
            if status == "failed":
                failure_count += 1
            # Reset polling wait time after a new submission
            polling_wait_time = INITIAL_POLLING_WAIT

        if pending_jobs:
            # --- Pass job timeout to the polling function ---
            successful, failed, requeued = _poll_pending_jobs(
                client,
                pending_jobs,
                transient_error_retries,
                MAX_TRANSIENT_RETRIES,
                JOB_TIMEOUT_SEC,
            )
            success_count += len(successful)
            failure_count += len(failed)
            if requeued:
                urls_to_process.extend(requeued)
                logging.info(
                    "Re-queued %d URLs due to transient API errors.", len(requeued)
                )

        if not urls_to_process and pending_jobs:
            logging.info(
                "%d captures remaining, starting next polling cycle in %d seconds...",
                len(pending_jobs),
                polling_wait_time,
            )
            time.sleep(polling_wait_time)
            # Increase wait time for the next cycle
            polling_wait_time = min(
                int(polling_wait_time * POLLING_BACKOFF_FACTOR), MAX_POLLING_WAIT
            )

    logging.info("--------------------------------------------------")
    logging.info("Archive workflow complete.")
    logging.info(f"Total URLs processed: {total_urls}")
    logging.info(f"Successful captures: {success_count}")
    logging.info(f"Failed captures: {failure_count}")
    logging.info("--------------------------------------------------")
