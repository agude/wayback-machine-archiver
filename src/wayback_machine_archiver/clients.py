import logging
import time
import requests


class LegacyClient:
    """Handles archiving using the public, unauthenticated API."""

    def __init__(self, session):
        self.session = session

    def archive(self, request_url, rate_limit_wait):
        """Submit a url to the Internet Archive to archive."""
        if rate_limit_wait > 0:
            logging.debug("Sleeping for %s", rate_limit_wait)
            time.sleep(rate_limit_wait)
        logging.info("Calling archive url %s", request_url)
        r = self.session.head(request_url, allow_redirects=True)
        try:
            # Raise `requests.exceptions.HTTPError` if 4XX or 5XX status
            r.raise_for_status()
        except requests.exceptions.HTTPError as e:
            logging.exception(e)
            raise


class SPN2Client:
    """Handles archiving using the authenticated SPN2 API."""

    SAVE_URL = "https://web.archive.org/save"

    def __init__(self, session, access_key, secret_key):
        self.session = session
        auth_header = f"LOW {access_key}:{secret_key}"
        self.session.headers.update(
            {
                "Authorization": auth_header,
                "Accept": "application/json",
            }
        )

    def submit_capture(self, url_to_archive):
        """
        Submits a capture request to the SPN2 API.
        Returns the job_id for the capture request.
        """
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
