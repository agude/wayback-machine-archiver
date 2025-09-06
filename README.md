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

The archiver is simple to use from the command line. The examples below work
regardless of which execution mode you are using.

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
                [--random-order]
                [urls ...]

A script to backup a web pages with Internet Archive

positional arguments:
  urls                  the URLs of the pages to archive

options:
  -h, --help            show this help message and exit
  --version             show program's version number and exit
  --file FILE           path to a file containing urls to save (one url per line)
  --sitemaps SITEMAPS [SITEMAPS ...]
                        one or more URIs to sitemaps listing pages to archive;
                        local paths must be prefixed with 'file://'
  --log {DEBUG,INFO,WARNING,ERROR,CRITICAL}
                        set the logging level, defaults to WARNING
                        (case-insensitive)
  --log-to-file LOG_FILE
                        redirect logs to a file
  --archive-sitemap-also
                        also submit the URL of the sitemap to be archived
  --rate-limit-wait RATE_LIMIT_IN_SEC
                        number of seconds to wait between page requests to
                        avoid flooding the archive site, defaults to 15
  --random-order        randomize the order of pages before archiving
```

## Setting Up a `Sitemap.xml` for Github Pages

It is easy to automatically generate a sitemap for a Github Pages Jekyll site.
Simply use [jekyll/jekyll-sitemap][jsm].

Setup instructions can be found on the above site; they require changing just
a single line of your site's `_config.yml`.

[jsm]: https://github.com/jekyll/jekyll-sitemap
