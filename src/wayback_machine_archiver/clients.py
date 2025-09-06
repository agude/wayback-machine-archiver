import logging
import time
import requests


class SPN2Client:
    """
    Handles archiving using the SPN2 API for both authenticated and
    unauthenticated users.
    """

    SAVE_URL = "https://web.archive.org/save"
    STATUS_URL_TEMPLATE = "https://web.archive.org/save/status/{job_id}"

    def __init__(self, session, access_key=None, secret_key=None):
        """
        Initializes the client. If access_key and secret_key are provided,
        it will make authenticated requests. Otherwise, it will make
        unauthenticated requests.
        """
        self.session = session
        # Always set the Accept header for JSON responses
        self.session.headers.update({"Accept": "application/json"})

        # Add Authorization header only if credentials are provided
        if access_key and secret_key:
            auth_header = f"LOW {access_key}:{secret_key}"
            self.session.headers.update({"Authorization": auth_header})

    def submit_capture(self, url_to_archive, rate_limit_wait):
        """
        Submits a capture request to the SPN2 API.
        Returns the job_id for the capture request.
        """
        if rate_limit_wait > 0:
            logging.debug("Sleeping for %s seconds", rate_limit_wait)
            time.sleep(rate_limit_wait)
        logging.info("Submitting %s to SPN2", url_to_archive)
        data = {"url": url_to_archive}
        try:
            r = self.session.post(self.SAVE_URL, data=data)
            r.raise_for_status()
            response_json = r.json()
            job_id = response_json.get("job_id")
            logging.info(
                "Successfully submitted %s, job_id: %s", url_to_archive, job_id
            )
            return job_id
        except requests.exceptions.HTTPError as e:
            logging.error("HTTP Error submitting URL %s: %s", url_to_archive, e)
            logging.error("Response content: %s", e.response.text)
            raise
        except Exception as e:
            logging.exception(e)
            raise

    def check_status(self, job_id):
        """
        Checks the status of a capture job.
        Returns the JSON response from the status API.
        """
        status_url = self.STATUS_URL_TEMPLATE.format(job_id=job_id)
        logging.debug("Checking status for job_id: %s", job_id)
        try:
            r = self.session.get(status_url)
            r.raise_for_status()
            return r.json()
        except requests.exceptions.HTTPError as e:
            logging.error("HTTP Error checking status for job %s: %s", job_id, e)
            logging.error("Response content: %s", e.response.text)
            raise
        except Exception as e:
            logging.exception(e)
            raise
