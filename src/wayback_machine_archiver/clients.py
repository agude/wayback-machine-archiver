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

    def __init__(self, session):
        self.session = session

    def archive(self, request_url, rate_limit_wait):
        """
        Placeholder archive method.
        Currently mimics the LegacyClient for structural purposes.
        """
        if rate_limit_wait > 0:
            logging.debug("Sleeping for %s", rate_limit_wait)
            time.sleep(rate_limit_wait)
        logging.info("Calling archive url %s (SPN2 placeholder)", request_url)
        r = self.session.head(request_url, allow_redirects=True)
        try:
            r.raise_for_status()
        except requests.exceptions.HTTPError as e:
            logging.exception(e)
            raise
