import logging
import time
import requests


class SPN2Client:
    """
    Handles archiving using the authenticated SPN2 API.
    """

    SAVE_URL = "https://web.archive.org/save"
    STATUS_URL = "https://web.archive.org/save/status"
    STATUS_URL_TEMPLATE = "https://web.archive.org/save/status/{job_id}"

    def __init__(self, session, access_key, secret_key):
        self.session = session
        self.is_authenticated = True  # Always true now

        self.session.headers.update({"Accept": "application/json"})
        auth_header = f"LOW {access_key}:{secret_key}"
        self.session.headers.update({"Authorization": auth_header})

    def submit_capture(self, url_to_archive, rate_limit_wait, api_params=None):
        """Submits a capture request to the SPN2 API."""
        if rate_limit_wait > 0:
            logging.debug("Sleeping for %s seconds", rate_limit_wait)
            time.sleep(rate_limit_wait)
        logging.info("Submitting %s to SPN2", url_to_archive)
        data = {"url": url_to_archive}
        if api_params:
            data.update(api_params)

        r = self.session.post(self.SAVE_URL, data=data)
        r.raise_for_status()
        response_json = r.json()
        job_id = response_json.get("job_id")
        logging.info("Successfully submitted %s, job_id: %s", url_to_archive, job_id)

        if job_id:
            status_check_url = self.STATUS_URL_TEMPLATE.format(job_id=job_id)
            logging.debug(
                "Manual status check URL for %s: %s", url_to_archive, status_check_url
            )

        return job_id

    def check_status(self, job_id):
        """Checks the status of a single capture job."""
        status_url = self.STATUS_URL_TEMPLATE.format(job_id=job_id)
        logging.debug("Checking status for single job_id: %s", job_id)
        r = self.session.get(status_url)
        r.raise_for_status()
        return r.json()

    def check_status_batch(self, job_ids):
        """Checks the status of multiple capture jobs in a single request."""
        logging.debug("Checking status for %d jobs in a batch.", len(job_ids))
        data = {"job_ids": ",".join(job_ids)}
        r = self.session.post(self.STATUS_URL, data=data)
        r.raise_for_status()
        return r.json()
