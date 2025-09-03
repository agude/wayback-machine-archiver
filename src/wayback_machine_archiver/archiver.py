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
__version__ = "2.2.0"


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


def _submit_next_url(
    urls_to_process,
    client,
    pending_jobs,
    rate_limit_in_sec,
    submission_attempts,
    max_retries=3,
):
    """
    Pops the next URL, submits it, and adds its job_id to pending_jobs.
    If submission fails, it re-queues the URL up to max_retries.
    """
    url = urls_to_process.pop(0)
    attempt_num = submission_attempts.get(url, 0) + 1
    submission_attempts[url] = attempt_num

    if attempt_num > max_retries:
        logging.error("URL %s failed submission %d times, giving up.", url, max_retries)
        return

    try:
        logging.info("Submitting %s (attempt %d/%d)...", url, attempt_num, max_retries)
        job_id = client.submit_capture(url, rate_limit_wait=rate_limit_in_sec)
        if job_id:
            pending_jobs[job_id] = url
            # On success, we can remove it from the attempts tracker
            if url in submission_attempts:
                del submission_attempts[url]
    except Exception as e:
        logging.warning(
            "Failed to submit URL %s: %s. Re-queuing for another attempt.", url, e
        )
        urls_to_process.append(url)


def _poll_pending_jobs(client, pending_jobs, poll_interval_sec=0.2):
    """
    Checks the status of pending jobs, removing completed ones.
    Waits a short interval between each check to avoid slamming the API.
    """
    for job_id in list(pending_jobs.keys()):
        original_url = pending_jobs[job_id]
        try:
            status_data = client.check_status(job_id)
            status = status_data.get("status")

            if status == "success":
                timestamp = status_data.get("timestamp")
                archive_url = f"https://web.archive.org/web/{timestamp}/{original_url}"
                logging.info("Success for job %s: %s", job_id, archive_url)
                del pending_jobs[job_id]
            elif status == "error":
                message = status_data.get("message", "Unknown error")
                logging.error(
                    "Error for job %s (%s): %s", job_id, original_url, message
                )
                del pending_jobs[job_id]
            else:
                logging.debug("Job %s (%s) is pending...", job_id, original_url)

        except Exception as e:
            logging.error(
                "An exception occurred while checking job %s (%s): %s",
                job_id,
                original_url,
                e,
            )
            del pending_jobs[job_id]

        # Be nice to the polling API
        time.sleep(poll_interval_sec)


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
        help="set the logging level, defaults to WARNING (case-insensitive)",
        dest="log_level",
        default=logging.WARNING,
        type=str.upper,
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
        help="number of seconds to wait between page requests to avoid flooding the archive site, defaults to 15",
        dest="rate_limit_in_sec",
        default=15,
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

    # Enforce API minimums for both modes
    if use_spn2:
        MIN_SPN2_WAIT_SEC = 5
        if args.rate_limit_in_sec < MIN_SPN2_WAIT_SEC:
            logging.warning(
                "Provided rate limit of %d seconds is below the API minimum of %d for authenticated users. Overriding to %d seconds to avoid rate-limiting.",
                args.rate_limit_in_sec,
                MIN_SPN2_WAIT_SEC,
                MIN_SPN2_WAIT_SEC,
            )
            args.rate_limit_in_sec = MIN_SPN2_WAIT_SEC
    else:
        MIN_LEGACY_WAIT_SEC = 15
        if args.rate_limit_in_sec < MIN_LEGACY_WAIT_SEC:
            logging.warning(
                "Provided rate limit of %d seconds is below the API minimum of %d for unauthenticated users. Overriding to %d seconds to avoid rate-limiting.",
                args.rate_limit_in_sec,
                MIN_LEGACY_WAIT_SEC,
                MIN_LEGACY_WAIT_SEC,
            )
            args.rate_limit_in_sec = MIN_LEGACY_WAIT_SEC

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

        urls_to_process = list(urls_to_archive_list)
        pending_jobs = {}
        submission_attempts = {}  # Tracks failed submission retries

        logging.info(
            "Beginning interleaved submission and polling of %d URLs...",
            len(urls_to_process),
        )

        while urls_to_process or pending_jobs:
            if urls_to_process:
                _submit_next_url(
                    urls_to_process,
                    client,
                    pending_jobs,
                    args.rate_limit_in_sec,
                    submission_attempts,
                )

            if pending_jobs:
                _poll_pending_jobs(client, pending_jobs)

            if not urls_to_process and pending_jobs:
                wait_time = 5
                logging.info(
                    "%d captures remaining, starting next polling cycle in %d seconds...",
                    len(pending_jobs),
                    wait_time,
                )
                time.sleep(wait_time)

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
