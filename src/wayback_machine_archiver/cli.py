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
        help="Specifies the URLs of the pages to archive.",
    )
    parser.add_argument(
        "--file",
        help="Specifies the path to a file containing URLs to save, one per line.",
        required=False,
    )
    parser.add_argument(
        "--sitemaps",
        nargs="+",
        default=[],
        help="Specifies one or more URIs to sitemaps listing pages to archive. Local paths must be prefixed with '{f}'.".format(
            f=LOCAL_PREFIX
        ),
        required=False,
    )
    parser.add_argument(
        "--log",
        help="Sets the logging level. Defaults to WARNING (case-insensitive).",
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
        help="Redirects logs to a specified file instead of the console.",
        dest="log_file",
        default=None,
    )
    parser.add_argument(
        "--archive-sitemap-also",
        help="Submits the URL of the sitemap itself to be archived.",
        dest="archive_sitemap",
        default=False,
        action="store_true",
    )
    parser.add_argument(
        "--rate-limit-wait",
        help="Specifies the number of seconds to wait between submissions. A minimum of 5 seconds is enforced for authenticated users. Defaults to 15.",
        dest="rate_limit_in_sec",
        default=15,
        type=int,
    )
    parser.add_argument(
        "--random-order",
        help="Randomizes the order of pages before archiving.",
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
        help="Captures a web page even if it returns an error (e.g., 404, 500).",
    )
    api_group.add_argument(
        "--capture-outlinks",
        action="store_true",
        help="Captures web page outlinks automatically. Note: this can significantly increase the total number of captures and runtime.",
    )
    api_group.add_argument(
        "--capture-screenshot",
        action="store_true",
        help="Captures a full page screenshot.",
    )
    api_group.add_argument(
        "--delay-wb-availability",
        action="store_true",
        help="Reduces load on Internet Archive systems by making the capture publicly available after ~12 hours instead of immediately.",
    )
    api_group.add_argument(
        "--force-get",
        action="store_true",
        help="Bypasses the headless browser check, which can speed up captures for non-HTML content (e.g., PDFs, images).",
    )
    api_group.add_argument(
        "--skip-first-archive",
        action="store_true",
        help="Speeds up captures by skipping the check for whether this is the first time a URL has been archived.",
    )
    api_group.add_argument(
        "--email-result",
        action="store_true",
        help="Sends an email report of the captured URLs to the user's registered email.",
    )
    api_group.add_argument(
        "--if-not-archived-within",
        type=str,
        metavar="<timedelta>",
        help="Captures only if the latest capture is older than <timedelta> (e.g., '3d 5h').",
    )
    api_group.add_argument(
        "--js-behavior-timeout",
        type=int,
        metavar="<seconds>",
        help="Runs JS code for <N> seconds after page load to trigger dynamic content. Defaults to 5, max is 30. Use 0 to disable for static pages.",
    )
    api_group.add_argument(
        "--capture-cookie",
        type=str,
        metavar="<cookie>",
        help="Uses an extra HTTP Cookie value when capturing the target page.",
    )
    api_group.add_argument(
        "--user-agent",
        type=str,
        metavar="<string>",
        dest="use_user_agent",
        help="Uses a custom HTTP User-Agent value when capturing the target page.",
    )

    return parser
