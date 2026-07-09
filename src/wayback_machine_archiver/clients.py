from __future__ import annotations

import logging
import time
from typing import Any

import requests


from . import REQUEST_TIMEOUT

BATCH_STATUS_CHUNK_SIZE = 50


class SPN2Client:
    """
    Handles archiving using the authenticated SPN2 API.
    """

    SAVE_URL = "https://web.archive.org/save"
    STATUS_URL = "https://web.archive.org/save/status"
    STATUS_URL_TEMPLATE = "https://web.archive.org/save/status/{job_id}"

    def __init__(
        self,
        session: requests.Session,
        access_key: str,
        secret_key: str,
    ) -> None:
        self.session = session

        self.session.headers.update({"Accept": "application/json"})
        auth_header = f"LOW {access_key}:{secret_key}"
        self.session.headers.update({"Authorization": auth_header})

    def submit_capture(
        self,
        url_to_archive: str,
        rate_limit_wait: float,
        api_params: dict[str, str | int] | None = None,
    ) -> str | None:
        """Submits a capture request to the SPN2 API."""
        if rate_limit_wait > 0:
            logging.debug("Sleeping for %s seconds", rate_limit_wait)
            time.sleep(rate_limit_wait)
        logging.info("Submitting %s to SPN2", url_to_archive)
        data: dict[str, str | int] = {"url": url_to_archive}
        if api_params:
            data.update(api_params)

        r = self.session.post(self.SAVE_URL, data=data, timeout=REQUEST_TIMEOUT)
        r.raise_for_status()
        response_json = r.json()
        job_id: str | None = response_json.get("job_id")
        logging.info("Successfully submitted %s, job_id: %s", url_to_archive, job_id)

        if job_id:
            status_check_url = self.STATUS_URL_TEMPLATE.format(job_id=job_id)
            logging.debug(
                "Manual status check URL for %s: %s", url_to_archive, status_check_url
            )

        return job_id

    def check_status_batch(self, job_ids: list[str]) -> list[dict[str, Any]]:
        """Checks the status of multiple capture jobs, chunking large batches."""
        logging.debug("Checking status for %d jobs.", len(job_ids))
        all_results: list[dict[str, Any]] = []
        for i in range(0, len(job_ids), BATCH_STATUS_CHUNK_SIZE):
            chunk = job_ids[i : i + BATCH_STATUS_CHUNK_SIZE]
            data = {"job_ids": ",".join(chunk)}
            r = self.session.post(self.STATUS_URL, data=data, timeout=REQUEST_TIMEOUT)
            r.raise_for_status()
            result = r.json()
            if isinstance(result, list):
                all_results.extend(result)
            else:
                all_results.append(result)
        logging.debug("Status API response: %s", all_results)
        return all_results
