# src/wayback_machine_archiver/cli.py
import argparse
import logging
from . import __version__

LOCAL_PREFIX = "file://"


def create_parser():
    """Creates and returns the argparse parser."""
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
    return parser
