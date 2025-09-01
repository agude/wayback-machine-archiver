import logging
import time
import requests


def call_archiver(request_url, rate_limit_wait, session):
    """Submit a url to the Internet Archive to archive."""
    if rate_limit_wait > 0:
        logging.debug("Sleeping for %s", rate_limit_wait)
        time.sleep(rate_limit_wait)
    logging.info("Calling archive url %s", request_url)
    r = session.head(request_url, allow_redirects=True)
    try:
        # Raise `requests.exceptions.HTTPError` if 4XX or 5XX status
        r.raise_for_status()
    except requests.exceptions.HTTPError as e:
        logging.exception(e)
        raise
