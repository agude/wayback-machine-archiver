# Github Pages Archiver

Github Pages Archiver (GPA) is a commandline utility to backup Github Pages using
[Internet Archive][ia].

[ia]: https://archive.org/

## Installation

Since GPA is still pre-1.0, the only way to install it is to clone this
repository and run `pip install .` in the directory with `setup.py`. This will
install the library, and the command line tool `archiver` which is used to
queue pages for backup.

## Usage

You can schedule a backup by specifying the URL of a Github Pages [`sitemap.xml`][sitemap]:

[sitemap]: https://en.wikipedia.org/wiki/Sitemaps

`archiver https://alexgude.com/sitemap.xml`

This will backup every page of my website, [alexgude.com][ag].

[ag]: https://alexgude.com

You can backup multiple sites (or a single site using multiple sitemaps) by
specifying multiple URLs:

`archiver https://alexgude.com/sitemap.xml https://charles.uno/sitemap.xml`

## Setting Up a `Sitemap.xml`

It is easy to automatically generate a sitemap for a Github Pages Jekyll site.
Simply use [jekyll/jekyll-sitemap][jsm].

Setup instructions can be found on the above site; they require changing just
a single line of your site's `_config.yml`.

[jsm]: https://github.com/jekyll/jekyll-sitemap
