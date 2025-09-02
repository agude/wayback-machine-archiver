from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import argparse
import logging
import os
import random
import re
import requests
import time
import xml.etree.ElementTree as ET
from dotenv import load_dotenv
from .clients import LegacyClient, SPN2Client

# Library version
__version__ = "2.0.0"


# String used to prefix local sitemaps
LOCAL_PREFIX = "file://"


def format_archive_url(url):
    """Given a URL, constructs an Archive URL to submit the archive request."""
    logging.debug("Creating archive URL for %s", url)
    SAVE_URL = "https://web.archive.org/save/"
    request_url = SAVE_URL + url

    return request_url


def get_namespace(element):
    """Extract the namespace using a regular expression."""
    match = re.match(r"\{.*\}", element.tag)
    return match.group(0) if match else ""


def download_remote_sitemap(sitemap_url, session):
    """Download the sitemap of the target website."""
    logging.debug("Downloading: %s", sitemap_url)
    r = session.get(sitemap_url)
    try:
        # Raise `requests.exceptions.HTTPError` if 4XX or 5XX status
        r.raise_for_status()
    except requests.exceptions.HTTPError as e:
        logging.exception(e)
        raise
    else:
        return r.text.encode("utf-8")


def load_local_sitemap(sitemap_filepath):
    """Load a local sitemap and return it as a string."""
    logging.debug("Loading local sitemap: %s", sitemap_filepath)

    if sitemap_filepath.startswith(LOCAL_PREFIX):
        sitemap_filepath = sitemap_filepath[len(LOCAL_PREFIX) :]

    # Try to open the file, error on failure
    try:
        logging.debug("Opening local file '%s'", sitemap_filepath)
        with open(sitemap_filepath, "r") as fp:
            contents = fp.read()
    except IOError as e:
        logging.exception(e)
        raise

    return contents


def sitemap_is_local(sitemap_url):
    """Returns True if we believe a URI to be local, False otherwise."""
    return sitemap_url.startswith(LOCAL_PREFIX) or sitemap_url.startswith("/")


def extract_pages_from_sitemap(site_map_text):
    """Extract the various pages from the sitemap text."""
    root = ET.fromstring(site_map_text)

    # Sitemaps use a namespace in the XML, which we need to read
    namespace = get_namespace(root)

    urls = []
    for loc_node in root.findall(".//{}loc".format(namespace)):
        urls.append(loc_node.text)

    return set(urls)


def main():
    # Command line parsing
    parser = argparse.ArgumentParser(
        prog="archiver",
        description="A script to backup a web pages with Internet Archive",
    )
    parser.add_argument(
        "--version",
        action="version",
        version="%(prog)s {version}".format(version=__version__),
    )
    parser.add_argument(
        "urls",
        nargs="*",
        default=[],
        help="the URLs of the pages to archive",
    )
    parser.add_argument(
        "--file",
        help="path to a file containing urls to save (one url per line)",
        required=False,
    )
    parser.add_argument(
        "--sitemaps",
        nargs="+",
        default=[],
        help="one or more URIs to sitemaps listing pages to archive; local paths must be prefixed with '{f}'".format(
            f=LOCAL_PREFIX
        ),
        required=False,
    )
    parser.add_argument(
        "--log",
        help="set the logging level, defaults to WARNING",
        dest="log_level",
        default=logging.WARNING,
        choices=[
            "DEBUG",
            "INFO",
            "WARNING",
            "ERROR",
            "CRITICAL",
        ],
    )
    parser.add_argument(
        "--log-to-file",
        help="redirect logs to a file",
        dest="log_file",
        default=None,
    )
    parser.add_argument(
        "--archive-sitemap-also",
        help="also submit the URL of the sitemap to be archived",
        dest="archive_sitemap",
        default=False,
        action="store_true",
    )
    parser.add_argument(
        "--rate-limit-wait",
        help="number of seconds to wait between page requests to avoid flooding the archive site, defaults to 5; also used as the backoff factor for retries",
        dest="rate_limit_in_sec",
        default=5,
        type=int,
    )
    parser.add_argument(
        "--random-order",
        help="randomize the order of pages before archiving",
        dest="random_order",
        default=False,
        action="store_true",
    )

    args = parser.parse_args()

    # Set the logging level based on the arguments
    logging.basicConfig(level=args.log_level, filename=args.log_file)

    # This will load variables from a .env file into the environment.
    # It will NOT overwrite any existing environment variables.
    load_dotenv()

    access_key = os.getenv("INTERNET_ARCHIVE_ACCESS_KEY")
    secret_key = os.getenv("INTERNET_ARCHIVE_SECRET_KEY")
    use_spn2 = access_key and secret_key

    logging.debug("Archiver Version: %s", __version__)
    logging.debug("Arguments: %s", args)

    urls_to_archive = []
    # Add the regular pages
    if args.urls:
        logging.info("Adding page URLs to archive")
        logging.debug("Page URLs to archive: %s", args.urls)
        urls_to_archive.extend(args.urls)

    # Set up retry and backoff
    session = requests.Session()
    session.max_redirects = 100

    retries = Retry(
        total=5,
        backoff_factor=args.rate_limit_in_sec,
        status_forcelist=[500, 502, 503, 504, 520],
    )

    session.mount("https://", HTTPAdapter(max_retries=retries))
    session.mount("http://", HTTPAdapter(max_retries=retries))

    # Download and process the sitemaps
    remote_sitemaps = set()
    logging.info("Parsing sitemaps")
    for sitemap_url in args.sitemaps:
        # Save the remote ones, incase the user wants us to backthem up
        if sitemap_is_local(sitemap_url):
            logging.debug("The sitemap '%s' is local.", sitemap_url)
            sitemap_xml = load_local_sitemap(sitemap_url)
        else:
            logging.debug("The sitemap '%s' is remote.", sitemap_url)
            if args.archive_sitemap:
                remote_sitemaps.add(sitemap_url)
            sitemap_xml = download_remote_sitemap(sitemap_url, session=session)

        urls_to_archive.extend(extract_pages_from_sitemap(sitemap_xml))

    # Archive the sitemap as well, if requested
    if args.archive_sitemap:
        logging.info("Archiving sitemaps")
        if remote_sitemaps:
            urls_to_archive.extend(remote_sitemaps)
        else:
            logging.debug("No remote sitemaps to backup.")

    # And URLs from file
    if args.file:
        logging.info("Reading urls from file: %s", args.file)
        with open(args.file) as file:
            urls_from_file = (u.strip() for u in file.readlines() if u.strip())
            urls_to_archive.extend(urls_from_file)

    # Deduplicate URLs and convert to a list
    urls_to_archive_list = list(set(urls_to_archive))

    # Randomize the order if requested
    if args.random_order:
        logging.info("Randomizing the order of URLs.")
        random.shuffle(urls_to_archive_list)

    # Archive the URLs
    logging.debug("Archive URLs: %s", urls_to_archive_list)

    if use_spn2:
        logging.info("SPN2 credentials found. Using authenticated API.")
        client = SPN2Client(
            session=session, access_key=access_key, secret_key=secret_key
        )

        # Phase 1: Submit all jobs sequentially
        logging.info("Submitting %d URLs to the SPN2 API...", len(urls_to_archive_list))
        job_ids = []
        for url in urls_to_archive_list:
            try:
                job_id = client.submit_capture(url)
                if job_id:
                    job_ids.append(job_id)
            except Exception as e:
                logging.error("Failed to submit URL %s: %s", url, e)

        # Filter out any submissions that failed
        pending_job_ids = job_ids
        logging.info("All URLs submitted. Now polling for capture status...")

        # Phase 2: Poll for status in a single thread
        while pending_job_ids:
            logging.info("%d captures remaining...", len(pending_job_ids))
            # Use a copy of the list to allow removing items during iteration
            for job_id in list(pending_job_ids):
                try:
                    status_data = client.check_status(job_id)
                    status = status_data.get("status")

                    if status == "success":
                        original_url = status_data.get("original_url")
                        timestamp = status_data.get("timestamp")
                        archive_url = (
                            f"https://web.archive.org/web/{timestamp}/{original_url}"
                        )
                        logging.info("Success for job %s: %s", job_id, archive_url)
                        pending_job_ids.remove(job_id)
                    elif status == "error":
                        message = status_data.get("message", "Unknown error")
                        logging.error("Error for job %s: %s", job_id, message)
                        pending_job_ids.remove(job_id)
                    else:  # status == "pending" or unknown
                        logging.debug("Job %s is pending...", job_id)

                except Exception as e:
                    logging.error(
                        "An exception occurred while checking job %s: %s", job_id, e
                    )
                    pending_job_ids.remove(job_id)  # Stop checking this job

            if pending_job_ids:
                time.sleep(5)  # Wait before the next polling cycle

        logging.info("All captures complete.")

    else:
        logging.warning("No SPN2 credentials found. Using public, unauthenticated API.")
        client = LegacyClient(session=session)
        # For legacy, we must format the URL first
        archive_urls_list = list(map(format_archive_url, urls_to_archive_list))

        logging.info("Archiving %d URLs sequentially...", len(archive_urls_list))
        for url in archive_urls_list:
            try:
                client.archive(url, rate_limit_wait=args.rate_limit_in_sec)
            except Exception as e:
                logging.error("Failed to archive URL %s: %s", url, e)


if __name__ == "__main__":
    main()
