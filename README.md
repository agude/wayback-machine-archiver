# Wayback Machine Archiver

Wayback Machine Archiver (Archiver for short) is a commandline utility writen
in Python to backup Github Pages using the [Internet Archive][ia].

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

You can also clone this repository:

```bash
git clone https://github.com/agude/wayback-machine-archiver.git
cd wayback-machine-archiver
python ./wayback_machine_archiver/archiver.py --help
```

If you clone the repository, Archiver can be installed as a local application
using the `setup.py` script:

```bash
git clone https://github.com/agude/wayback-machine-archiver.git
cd wayback-machine-archiver
./setup.py install
```

Which, like using `pip`, will give you access to the script by calling
`archiver`.

Archiver requires [the `requests` library][requests] by Kenneth Reitz.
Archiver supports Python 2.7, and Python 3.4+.

[requests]: https://github.com/kennethreitz/requests

## Usage

The simplest way to schedule a backup is by specifying the URL of a web page,
like so:

```bash
archiver https://alexgude.com
```

This will submit the main page of my blog, [alexgude.com][ag], to the Wayback
Machine for archiving.

[ag]: https://alexgude.com

You can also archive all the URLs specified in a [`sitemap.xml`][sitemap] as
follows:

[sitemap]: https://en.wikipedia.org/wiki/Sitemaps

```bash
archiver --sitemaps https://alexgude.com/sitemap.xml
```

This will backup every page listed in the sitemap of my website, [alexgude.com][ag].

You can also pass a sitemap.xml file (requires the `file://` prefix) to the archiver:

```bash
archiver --sitemaps file://sitemap.xml
```

You can backup multiple pages by specifying multiple URLs or sitemaps:

```bash
archiver https://radiokeysmusic.com --sitemaps https://charles.uno/sitemap.xml https://alexgude.com/sitemaps.xml
```

You can also backup multiple URLs by writing them to a file (for example,
`urls.txt`), one URL per line, and passing that file to archiver:

```bash
archiver --file urls.txt
```

Sitemaps often exclude themselves, so you can request that the sitemap itself
be backed up using the flag `--archive-sitemap-also`:

```bash
archiver --sitemaps https://alexgude.com/sitemaps.xml --archive-sitemap-also
```

## Help

For a full list of commandline flags, Archiver has a built-in help displayed
with `archiver --help`:

```
usage: Github Pages Archiver [-h] [--version] [--file FILE]
                             [--sitemaps SITEMAPS [SITEMAPS ...]]
                             [--log {DEBUG,INFO,WARNING,ERROR,CRITICAL}]
                             [--log-to-file LOG_FILE] [--archive-sitemap-also]
                             [--jobs JOBS]
                             [--rate-limit-wait RATE_LIMIT_IN_SEC]
                             [urls [urls ...]]

A script to backup a web pages with Internet Archive

positional arguments:
  urls                  the URLs of the pages to archive

optional arguments:
  -h, --help            show this help message and exit
  --version             show program's version number and exit
  --file FILE           path to a file containing urls to save (one url per
                        line)
  --sitemaps SITEMAPS [SITEMAPS ...]
                        one or more URLs to sitemaps listing pages to archive
  --log {DEBUG,INFO,WARNING,ERROR,CRITICAL}
                        set the logging level, defaults to WARNING
  --log-to-file LOG_FILE
                        redirect logs to a file
  --archive-sitemap-also
                        also submit the URL of the sitemap to be archived
  --jobs JOBS, -j JOBS  run this many concurrent URL submissions, defaults to
                        1
  --rate-limit-wait RATE_LIMIT_IN_SEC
                        number of seconds to wait between page requests to
                        avoid flooding the archive site, defaults to 5; also
                        used as the backoff factor for retries
```

## Setting Up a `Sitemap.xml` for Github Pages

It is easy to automatically generate a sitemap for a Github Pages Jekyll site.
Simply use [jekyll/jekyll-sitemap][jsm].

Setup instructions can be found on the above site; they require changing just
a single line of your site's `_config.yml`.

[jsm]: https://github.com/jekyll/jekyll-sitemap
