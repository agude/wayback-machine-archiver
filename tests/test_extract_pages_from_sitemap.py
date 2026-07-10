# -*- coding: UTF-8 -*-
from wayback_machine_archiver.sitemaps import extract_urls_from_sitemap


def test_ascii_sitemap():
    SITEMAP = b"""<?xml version="1.0" encoding="UTF-8"?>
        <urlset xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xsi:schemaLocation="http://www.sitemaps.org/schemas/sitemap/0.9 http://www.sitemaps.org/schemas/sitemap/0.9/sitemap.xsd" xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
        <url>
        <loc>https://alexgude.com/blog/double-checking-538/</loc>
        <lastmod>2016-04-28T00:00:00+00:00</lastmod>
        </url>
        <url>
        <loc>https://alexgude.com/files/undergrad_thesis.pdf</loc>
        <lastmod>2019-05-09T16:19:45+00:00</lastmod>
        </url>
        </urlset>
    """

    URLS = {
        "https://alexgude.com/blog/double-checking-538/",
        "https://alexgude.com/files/undergrad_thesis.pdf",
    }

    page_urls, child_sitemaps = extract_urls_from_sitemap(SITEMAP)
    assert page_urls == URLS
    assert child_sitemaps == set()


def test_unicode_sitemap():
    SITEMAP = """<?xml version="1.0" encoding="UTF-8"?>
        <urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" xmlns:image="http://www.google.com/schemas/sitemap-image/1.1">
        <url>
        <loc>https://www.radiokeysmusic.com/home</loc>
        <changefreq>daily</changefreq>
        <priority>1.0</priority>
        <lastmod>2018-12-17</lastmod>
        <image:image>
        <image:loc>https://static1.squarespace.com/static/5c06e0ab1137a66237a2399c/t/5c0d6a4d562fa7678539d405/1544383062969/</image:loc>
        <image:title>Home</image:title>
        <image:caption>Tom, Stewart, Allante, &amp; Emily. Photo by Cory Cullington, 2018.</image:caption>
        </image:image>
        </url>
        <url>
        <loc>https://www.radiokeysmusic.com/about</loc>
        <changefreq>daily</changefreq>
        <priority>0.75</priority>
        <lastmod>2019-01-05</lastmod>
        <image:image>
        <image:loc>https://static1.squarespace.com/static/5c06e0ab1137a66237a2399c/t/5c0d6b5b6d2a7379672b9b34/1544896195646/IMG_9107.jpg</image:loc>
        <image:title>About - Story</image:title>
        <image:caption> instrumentation complimented by Emily’s velvety voice and Stewart’s </image:caption>
        </image:image>
        </url>
        </urlset>
    """.encode()

    URLS = {
        "https://www.radiokeysmusic.com/home",
        "https://www.radiokeysmusic.com/about",
    }

    page_urls, child_sitemaps = extract_urls_from_sitemap(SITEMAP)
    assert page_urls == URLS
    assert child_sitemaps == set()


def test_sitemap_index():
    SITEMAP_INDEX = b"""<?xml version="1.0" encoding="UTF-8"?>
        <sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
        <sitemap>
        <loc>https://example.com/sitemap1.xml</loc>
        </sitemap>
        <sitemap>
        <loc>https://example.com/sitemap2.xml</loc>
        </sitemap>
        </sitemapindex>
    """

    page_urls, child_sitemaps = extract_urls_from_sitemap(SITEMAP_INDEX)
    assert page_urls == set()
    assert child_sitemaps == {
        "https://example.com/sitemap1.xml",
        "https://example.com/sitemap2.xml",
    }
