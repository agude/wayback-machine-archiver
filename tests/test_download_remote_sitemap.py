import pytest
from wayback_machine_archiver.sitemaps import download_remote_sitemap
from requests.adapters import HTTPAdapter
import requests


SITEMAP = """<?xml version="1.0" encoding="UTF-8"?>
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


@pytest.fixture
def session():
    session = requests.Session()
    session.mount("https://", HTTPAdapter())
    session.mount("http://", HTTPAdapter())
    return session


def test_download_remote_sitemap(requests_mock, session):
    url = "https://www.radiokeysmusic.com/sitemap.xml"
    requests_mock.get(url, text=SITEMAP)
    returned_contents = download_remote_sitemap(url, session)
    assert returned_contents == SITEMAP.encode("UTF-8")


def test_download_remote_sitemap_with_status_error(requests_mock, session):
    url = "https://www.radiokeysmusic.com/sitemap.xml"
    requests_mock.get(url, text=SITEMAP, status_code=404)
    with pytest.raises(requests.exceptions.HTTPError):
        download_remote_sitemap(url, session)
