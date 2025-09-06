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

    # --- SPN2 API Options ---
    api_group = parser.add_argument_group(
        "SPN2 API Options", "Control the behavior of the Internet Archive capture API."
    )
    api_group.add_argument(
        "--capture-all",
        action="store_true",
        help="Capture a web page even if it returns an error (e.g., 404, 500).",
    )
    api_group.add_argument(
        "--capture-outlinks",
        action="store_true",
        help="Capture web page outlinks automatically.",
    )
    api_group.add_argument(
        "--capture-screenshot",
        action="store_true",
        help="Capture a full page screenshot.",
    )
    api_group.add_argument(
        "--delay-wb-availability",
        action="store_true",
        help="Make the capture available in the Wayback Machine after ~12 hours.",
    )
    api_group.add_argument(
        "--force-get",
        action="store_true",
        help="Force the use of a simple HTTP GET request to capture the target URL.",
    )
    api_group.add_argument(
        "--skip-first-archive",
        action="store_true",
        help="Skip checking if a capture is the first archive, making captures faster.",
    )
    api_group.add_argument(
        "--email-result",
        action="store_true",
        help="Send an email report of the captured URLs to the user's registered email.",
    )
    api_group.add_argument(
        "--if-not-archived-within",
        type=str,
        metavar="<timedelta>",
        help="Capture only if the latest capture is older than <timedelta> (e.g., '3d 5h').",
    )
    api_group.add_argument(
        "--js-behavior-timeout",
        type=int,
        metavar="<seconds>",
        help="Run JS code for <N> seconds after page load. Defaults to 5.",
    )
    api_group.add_argument(
        "--capture-cookie",
        type=str,
        metavar="<cookie>",
        help="Use an extra HTTP Cookie value when capturing the target page.",
    )
    api_group.add_argument(
        "--user-agent",
        type=str,
        metavar="<string>",
        dest="use_user_agent",
        help="Use a custom HTTP User-Agent value when capturing the target page.",
    )

    return parser
