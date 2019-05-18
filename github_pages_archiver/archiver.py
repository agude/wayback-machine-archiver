import argparse
import logging
import re
import requests
import xml.etree.ElementTree as ET


def archive_url(url):
    """Submit a url to the Internet Archive to archive."""
    logging.info("Archiving %s", url)
    SAVE_URL = "https://web.archive.org/save/"
    request_url = SAVE_URL + url
    logging.debug("Using archive url %s", request_url)
    r = requests.get(request_url)

    # Raise `requests.exceptions.HTTPError` if 4XX or 5XX status
    r.raise_for_status()


def get_namespace(element):
    """Extract the namespace using a regular expression."""
    match = re.match(r"\{.*\}", element.tag)
    return match.group(0) if match else ''


def download_sitemap(site_map_url):
    """Download the sitemap of the target website."""
    logging.info("Processing: %s", site_map_url)
    r = requests.get(site_map_url)
    root = ET.fromstring(r.text.encode("utf-8"))

    # Sitemaps use a namespace in the XML, which we need to read
    ns = get_namespace(root)

    urls = []
    for loc_node in root.findall(".//{}loc".format(ns)):
        urls.append(loc_node.text)

    return set(urls)


def main():
    # Command line parsing
    parser = argparse.ArgumentParser(
        prog="Github Pages Archiver",
        description="A script to backup a Github Pages site with Internet Archive",
    )
    parser.add_argument(
        "sitemaps",
        nargs="+",
        help="one or more sitemap urls to load",
    )
    parser.add_argument(
        "--log",
        help="set the logging level, defaults to WARNING",
        dest="log_level",
        default=logging.WARNING,
        choices=[
            'DEBUG',
            'INFO',
            'WARNING',
            'ERROR',
            'CRITICAL',
        ],
    )

    args = parser.parse_args()

    # Set the logging level based on the arguments
    logging.basicConfig(level=args.log_level)

    logging.debug("Arguments: {args}".format(args=args))

    # Download and process the sitemaps
    for sitemap in args.sitemaps:
        for url in download_sitemap(sitemap):
            archive_url(url)

if __name__ == "__main__":
    main()
