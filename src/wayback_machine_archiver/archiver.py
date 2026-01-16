from __future__ import annotations

import logging
import os
import random
import sys
from urllib.parse import urlparse

import requests
from dotenv import load_dotenv
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from .cli import create_parser
from .clients import SPN2Client
from .sitemaps import process_sitemaps
from .workflow import run_archive_workflow

_DEFAULT_RETRY_COUNT = 5


def _create_session_with_retries(
    backoff_factor: float = 1,
    total_retries: int = _DEFAULT_RETRY_COUNT,
) -> requests.Session:
    """Create a requests session with retry logic for transient errors."""
    session = requests.Session()
    retries = Retry(
        total=total_retries,
        backoff_factor=backoff_factor,
        status_forcelist=[500, 502, 503, 504, 520],
        allowed_methods=["HEAD", "GET", "POST", "PUT", "DELETE", "OPTIONS", "TRACE"],
    )
    # Mount to both protocols to ensure retry logic applies regardless of target scheme
    session.mount("https://", HTTPAdapter(max_retries=retries))
    session.mount("http://", HTTPAdapter(max_retries=retries))
    return session


def _is_valid_url(url: str) -> bool:
    """Check if a URL has a valid structure for archiving."""
    try:
        parsed = urlparse(url)
        # Must have http or https scheme and a network location (domain)
        return parsed.scheme in ("http", "https") and bool(parsed.netloc)
    except ValueError:
        return False


def main() -> None:
    """Main entry point for the archiver script."""
    parser = create_parser()
    args = parser.parse_args()

    logging.basicConfig(level=args.log_level, filename=args.log_file)
    load_dotenv()

    # --- Load and REQUIRE credentials ---
    access_key = os.getenv("INTERNET_ARCHIVE_ACCESS_KEY")
    secret_key = os.getenv("INTERNET_ARCHIVE_SECRET_KEY")

    if not (access_key and secret_key):
        logging.error(
            "Authentication required. Please provide your Internet Archive S3-style keys."
        )
        logging.error("You can get your keys from: https://archive.org/account/s3.php")
        logging.error("Then, create a .env file or set the environment variables:")
        logging.error("INTERNET_ARCHIVE_ACCESS_KEY and INTERNET_ARCHIVE_SECRET_KEY")
        sys.exit(1)

    # --- Enforce API rate-limiting minimums for authenticated users ---
    MIN_WAIT_SEC = 5
    if args.rate_limit_in_sec < MIN_WAIT_SEC:
        logging.warning(
            "Provided rate limit of %d seconds is below the API minimum of %d for authenticated users. Overriding to %d seconds.",
            args.rate_limit_in_sec,
            MIN_WAIT_SEC,
            MIN_WAIT_SEC,
        )
        args.rate_limit_in_sec = MIN_WAIT_SEC

    # --- Build API parameters dictionary from CLI args ---
    api_params: dict[str, str | int] = {}
    if args.capture_all:
        api_params["capture_all"] = "1"
    if args.capture_outlinks:
        api_params["capture_outlinks"] = "1"
    if args.capture_screenshot:
        api_params["capture_screenshot"] = "1"
    if args.delay_wb_availability:
        api_params["delay_wb_availability"] = "1"
    if args.force_get:
        api_params["force_get"] = "1"
    if args.skip_first_archive:
        api_params["skip_first_archive"] = "1"
    if args.email_result:
        api_params["email_result"] = "1"
    if args.if_not_archived_within:
        api_params["if_not_archived_within"] = args.if_not_archived_within
    if args.js_behavior_timeout is not None:
        api_params["js_behavior_timeout"] = args.js_behavior_timeout
    if args.capture_cookie:
        api_params["capture_cookie"] = args.capture_cookie
    if args.use_user_agent:
        api_params["use_user_agent"] = args.use_user_agent

    if api_params:
        logging.info(f"Using the following API parameters: {api_params}")

    # --- Gather all URLs to archive ---
    urls_to_archive: set[str] = set()
    logging.info("Gathering URLs to archive...")
    if args.urls:
        logging.info(f"Found {len(args.urls)} URLs from command-line arguments.")
        urls_to_archive.update(args.urls)
    if args.sitemaps:
        session = _create_session_with_retries()
        logging.info(f"Processing {len(args.sitemaps)} sitemap(s)...")
        sitemap_urls = process_sitemaps(args.sitemaps, session)
        logging.info(f"Found {len(sitemap_urls)} URLs from sitemaps.")
        urls_to_archive.update(sitemap_urls)
        if args.archive_sitemap:
            remote_sitemaps = {s for s in args.sitemaps if not s.startswith("file://")}
            urls_to_archive.update(remote_sitemaps)
    if args.file:
        with open(args.file) as f:
            urls_from_file = {line.strip() for line in f if line.strip()}
            logging.info(f"Found {len(urls_from_file)} URLs from file: {args.file}")
            urls_to_archive.update(urls_from_file)

    # --- Validate URLs ---
    invalid_urls = {url for url in urls_to_archive if not _is_valid_url(url)}
    if invalid_urls:
        for url in invalid_urls:
            logging.warning(
                "Skipping invalid URL '%s': must have http:// or https:// scheme.",
                url,
            )
        urls_to_archive -= invalid_urls

    urls_to_process: list[str] = list(urls_to_archive)
    if not urls_to_process:
        logging.warning("No unique URLs found to archive. Exiting.")
        return
    logging.info(f"Found a total of {len(urls_to_process)} unique URLs to archive.")
    if args.random_order:
        logging.info("Randomizing the order of URLs.")
        random.shuffle(urls_to_process)

    # --- Run the archiving workflow ---
    logging.info("SPN2 credentials found. Using authenticated API workflow.")
    client_session = _create_session_with_retries(backoff_factor=args.rate_limit_in_sec)

    client = SPN2Client(
        session=client_session, access_key=access_key, secret_key=secret_key
    )
    run_archive_workflow(client, urls_to_process, args.rate_limit_in_sec, api_params)


if __name__ == "__main__":
    main()
