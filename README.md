# Wayback Machine Archiver

Wayback Machine Archiver (Archiver for short) is a command-line utility
written in Python to back up web pages using the [Internet Archive][ia].

[ia]: https://archive.org/

## Installation

The best way to install Archiver is with `pip`:

```bash
pip install wayback-machine-archiver
```

This will give you access to the script simply by calling:

```bash
archiver --help
```

You can also install it directly from a local clone of this repository:

```bash
git clone https://github.com/agude/wayback-machine-archiver.git
cd wayback-machine-archiver
pip install .
```

All dependencies are handled automatically. Archiver supports Python 3.8+.

## Usage

The archiver is simple to use from the command line.

### Command-Line Examples

**Archive a single page:**
```bash
archiver https://alexgude.com
```

**Archive all pages from a sitemap:**
```bash
archiver --sitemaps https://alexgude.com/sitemap.xml
```

**Archive from a local sitemap file:**
(Note the `file://` prefix is required)
```bash
archiver --sitemaps file://sitemap.xml
```

**Archive from a text file of URLs:**
(The file should contain one URL per line)
```bash
archiver --file urls.txt
```

**Combine multiple sources:**
```bash
archiver https://radiokeysmusic.com --sitemaps https://charles.uno/sitemap.xml
```

**Use advanced API options:**
(Capture a screenshot and skip if archived in the last 10 days)
```bash
archiver https://alexgude.com --capture-screenshot --if-not-archived-within 10d
```

**Archive the sitemap URL itself:**
```bash
archiver --sitemaps https://alexgude.com/sitemaps.xml --archive-sitemap-also
```

## Authentication (Required)

As of version 3.0.0, this tool requires authentication with the Internet
Archive's SPN2 API. This change was made to ensure all archiving jobs are
reliable and their final success or failure status can be confirmed. The
previous, less reliable method for unauthenticated users has been removed.

If you run the script without credentials, it will exit with an error message.

**To set up authentication:**

1.  Get your S3-style API keys from your Internet Archive account settings:
    [https://archive.org/account/s3.php](https://archive.org/account/s3.php)

2.  Create a `.env` file in the directory where you run the `archiver`
    command. Add your keys to it:
    ```
    INTERNET_ARCHIVE_ACCESS_KEY="YOUR_ACCESS_KEY_HERE"
    INTERNET_ARCHIVE_SECRET_KEY="YOUR_SECRET_KEY_HERE"
    ```

The script will automatically detect this file (or the equivalent environment
variables) and use the authenticated API.

## Help

For a full list of command-line flags, Archiver has built-in help displayed
with `archiver --help`:

```
usage: archiver [-h] [--version] [--file FILE]
                [--sitemaps SITEMAPS [SITEMAPS ...]]
                [--log {DEBUG,INFO,WARNING,ERROR,CRITICAL}]
                [--log-to-file LOG_FILE]
                [--archive-sitemap-also]
                [--rate-limit-wait RATE_LIMIT_IN_SEC]
                [--random-order] [--capture-all]
                [--capture-outlinks] [--capture-screenshot]
                [--delay-wb-availability] [--force-get]
                [--skip-first-archive] [--email-result]
                [--if-not-archived-within <timedelta>]
                [--js-behavior-timeout <seconds>]
                [--capture-cookie <cookie>]
                [--user-agent <string>]
                [urls ...]

A script to backup a web pages with Internet Archive

positional arguments:
  urls                  Specifies the URLs of the pages to archive.

options:
  -h, --help            show this help message and exit
  --version             show program's version number and exit
  --file FILE           Specifies the path to a file containing URLs to save,
                        one per line.
  --sitemaps SITEMAPS [SITEMAPS ...]
                        Specifies one or more URIs to sitemaps listing pages
                        to archive. Local paths must be prefixed with
                        'file://'.
  --log {DEBUG,INFO,WARNING,ERROR,CRITICAL}
                        Sets the logging level. Defaults to WARNING
                        (case-insensitive).
  --log-to-file LOG_FILE
                        Redirects logs to a specified file instead of the
                        console.
  --archive-sitemap-also
                        Submits the URL of the sitemap itself to be archived.
  --rate-limit-wait RATE_LIMIT_IN_SEC
                        Specifies the number of seconds to wait between
                        submissions. A minimum of 5 seconds is enforced for
                        authenticated users. Defaults to 15.
  --random-order        Randomizes the order of pages before archiving.

SPN2 API Options:
  Control the behavior of the Internet Archive capture API.

  --capture-all         Captures a web page even if it returns an error (e.g.,
                        404, 500).
  --capture-outlinks    Captures web page outlinks automatically. Note: this
                        can significantly increase the total number of
                        captures and runtime.
  --capture-screenshot  Captures a full page screenshot.
  --delay-wb-availability
                        Reduces load on Internet Archive systems by making the
                        capture publicly available after ~12 hours instead of
                        immediately.
  --force-get           Bypasses the headless browser check, which can speed
                        up captures for non-HTML content (e.g., PDFs, images).
  --skip-first-archive  Speeds up captures by skipping the check for whether
                        this is the first time a URL has been archived.
  --email-result        Sends an email report of the captured URLs to the
                        user's registered email.
  --if-not-archived-within <timedelta>
                        Captures only if the latest capture is older than
                        <timedelta> (e.g., '3d 5h').
  --js-behavior-timeout <seconds>
                        Runs JS code for <N> seconds after page load to
                        trigger dynamic content. Defaults to 5, max is 30. Use
                        0 to disable for static pages.
  --capture-cookie <cookie>
                        Uses an extra HTTP Cookie value when capturing the
                        target page.
  --user-agent <string>
                        Uses a custom HTTP User-Agent value when capturing the
                        target page.
```

## Setting Up a `Sitemap.xml` for Github Pages

It is easy to automatically generate a sitemap for a Github Pages Jekyll site.
Simply use [jekyll/jekyll-sitemap][jsm].

Setup instructions can be found on the above site; they require changing just
a single line of your site's `_config.yml`.

[jsm]: https://github.com/jekyll/jekyll-sitemap
