import logging
import os
import random
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

    # Set up logging
    logging.basicConfig(level=args.log_level, filename=args.log_file)

    # Load environment variables for credentials
    load_dotenv()
    access_key = os.getenv("INTERNET_ARCHIVE_ACCESS_KEY")
    secret_key = os.getenv("INTERNET_ARCHIVE_SECRET_KEY")
    is_authenticated = access_key and secret_key

    # Enforce API rate-limiting minimums
    if is_authenticated:
        MIN_WAIT_SEC = 5
        if args.rate_limit_in_sec < MIN_WAIT_SEC:
            logging.warning(
                "Provided rate limit of %d seconds is below the API minimum of %d for authenticated users. Overriding to %d seconds.",
                args.rate_limit_in_sec,
                MIN_WAIT_SEC,
                MIN_WAIT_SEC,
            )
            args.rate_limit_in_sec = MIN_WAIT_SEC
    else:
        logging.warning(
            "No Internet Archive credentials found. Proceeding in unauthenticated mode with a lower rate limit."
        )
        MIN_WAIT_SEC = 15
        if args.rate_limit_in_sec < MIN_WAIT_SEC:
            logging.warning(
                "Provided rate limit of %d seconds is below the API minimum of %d for unauthenticated users. Overriding to %d seconds.",
                args.rate_limit_in_sec,
                MIN_WAIT_SEC,
                MIN_WAIT_SEC,
            )
            args.rate_limit_in_sec = MIN_WAIT_SEC

    # --- Gather all URLs to archive ---
    urls_to_archive = set()
    logging.info("Gathering URLs to archive...")

    # 1. From command-line arguments
    if args.urls:
        logging.info(f"Found {len(args.urls)} URLs from command-line arguments.")
        urls_to_archive.update(args.urls)

    # 2. From sitemaps
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

    # 3. From a file
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

    # Randomize order if requested
    if args.random_order:
        logging.info("Randomizing the order of URLs.")
        random.shuffle(urls_to_process)

    # --- Run the archiving workflow ---
    if is_authenticated:
        logging.info("SPN2 credentials found. Using authenticated API.")
    else:
        logging.warning("No SPN2 credentials found. Using public, unauthenticated API.")

    # Set up the session for the client
    client_session = requests.Session()
    retries = Retry(
        total=5,
        backoff_factor=args.rate_limit_in_sec,
        status_forcelist=[500, 502, 503, 504, 520],
    )
    client_session.mount("https://", HTTPAdapter(max_retries=retries))
    client_session.mount("http://", HTTPAdapter(max_retries=retries))

    client = SPN2Client(
        session=client_session, access_key=access_key, secret_key=secret_key
    )

    run_archive_workflow(client, urls_to_process, args.rate_limit_in_sec)


if __name__ == "__main__":
    main()
