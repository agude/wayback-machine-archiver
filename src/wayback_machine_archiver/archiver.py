import logging
import os
import random
import sys
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from dotenv import load_dotenv

from .clients import SPN2Client
from .cli import create_parser
from .sitemaps import process_sitemaps
from .workflow import run_archive_workflow


def main():
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
    api_params = {}
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
    urls_to_archive = set()
    logging.info("Gathering URLs to archive...")
    if args.urls:
        logging.info(f"Found {len(args.urls)} URLs from command-line arguments.")
        urls_to_archive.update(args.urls)
    if args.sitemaps:
        session = requests.Session()
        retries = Retry(
            total=5, backoff_factor=1, status_forcelist=[500, 502, 503, 504]
        )
        session.mount("https://", HTTPAdapter(max_retries=retries))
        session.mount("http://", HTTPAdapter(max_retries=retries))
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

    urls_to_process = list(urls_to_archive)
    if not urls_to_process:
        logging.warning("No unique URLs found to archive. Exiting.")
        return
    logging.info(f"Found a total of {len(urls_to_process)} unique URLs to archive.")
    if args.random_order:
        logging.info("Randomizing the order of URLs.")
        random.shuffle(urls_to_process)

    # --- Run the archiving workflow ---
    logging.info("SPN2 credentials found. Using authenticated API workflow.")
    client_session = requests.Session()
    retries = Retry(
        total=5,
        backoff_factor=args.rate_limit_in_sec,
        status_forcelist=[500, 502, 503, 504, 520],
        allowed_methods=["HEAD", "GET", "POST", "PUT", "DELETE", "OPTIONS", "TRACE"],
    )
    client_session.mount("https://", HTTPAdapter(max_retries=retries))
    client_session.mount("http://", HTTPAdapter(max_retries=retries))

    client = SPN2Client(
        session=client_session, access_key=access_key, secret_key=secret_key
    )
    run_archive_workflow(client, urls_to_process, args.rate_limit_in_sec, api_params)


if __name__ == "__main__":
    main()
