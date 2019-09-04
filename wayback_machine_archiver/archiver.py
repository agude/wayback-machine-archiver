from functools import partial
import argparse
import logging
import multiprocessing as mp
import re
import requests
import time
import xml.etree.ElementTree as ET


# Library version
__version__ = "1.3.1"


def format_archive_url(url):
    """Given a URL, constructs an Archive URL to submit the archive request."""
    logging.debug("Creating archive URL for %s", url)
    SAVE_URL = "https://web.archive.org/save/"
    request_url = SAVE_URL + url

    return request_url


def call_archiver(request_url, rate_limit_wait):
    """Submit a url to the Internet Archive to archive."""
    if rate_limit_wait > 0:
        logging.debug("Sleeping for %s", rate_limit_wait)
        time.sleep(rate_limit_wait)
    logging.info("Calling archive url %s", request_url)
    r = requests.head(request_url)

    # Raise `requests.exceptions.HTTPError` if 4XX or 5XX status
    r.raise_for_status()


def get_namespace(element):
    """Extract the namespace using a regular expression."""
    match = re.match(r"\{.*\}", element.tag)
    return match.group(0) if match else ""


def download_sitemap(site_map_url):
    """Download the sitemap of the target website."""
    logging.debug("Downloading: %s", site_map_url)
    r = requests.get(site_map_url)

    return r.text.encode("utf-8")


def extract_pages_from_sitemap(site_map_text):
    """Extract the various pages from the sitemap text. """
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
        prog="Github Pages Archiver",
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
        "--sitemaps",
        nargs="+",
        default=[],
        help="one or more URLs to sitemaps listing pages to archive",
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
        "--archive-sitemap-also",
        help="also submit the URL of the sitemap to be archived",
        dest="archive_sitemap",
        default=False,
        action="store_true",
    )
    parser.add_argument(
        "--jobs",
        "-j",
        help="run this many concurrent URL submissions, defaults to 1",
        default=1,
        type=int,
    )
    parser.add_argument(
        "--rate-limit-wait",
        help="number of seconds to wait between page requests to avoid flooding the archive site, defaults to 3",
        dest="rate_limit_in_sec",
        default=3,
        type=int,
    )

    args = parser.parse_args()

    # Set the logging level based on the arguments
    logging.basicConfig(level=args.log_level)

    logging.debug("Arguments: %s", args)

    archive_urls = []
    # Add the regular pages
    if args.urls:
        logging.info("Adding page URLs to archive")
        logging.debug("Page URLs to archive: %s", args.urls)
        archive_urls += map(format_archive_url, args.urls)

    # Download and process the sitemaps
    for sitemap_url in args.sitemaps:
        logging.info("Parsing sitemaps")
        sitemap_xml = download_sitemap(sitemap_url)
        for url in extract_pages_from_sitemap(sitemap_xml):
            archive_urls.append(format_archive_url(url))

    # Archive the sitemap as well, if requested
    if args.archive_sitemap:
        logging.info("Archiving sitemaps")
        archive_urls += map(format_archive_url, args.sitemaps)

    # Archive the URLs
    logging.debug("Archive URLs: %s", archive_urls)
    pool = mp.Pool(processes=args.jobs)
    partial_call = partial(call_archiver, rate_limit_in_sec=args.rate_limit_in_sec)
    pool.map(partial_call, archive_urls)
    pool.close()
    pool.join()


if __name__ == "__main__":
    main()
