# -*- coding: UTF-8 -*-
from __future__ import unicode_literals
from wayback_machine_archiver.sitemaps import load_local_sitemap, LOCAL_PREFIX
import os.path
import pytest


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


def test_load_local_file_without_prefix(tmpdir):
    # Write a file using pytest's tmpdir so we can read it back
    file = tmpdir.join("sitemap.xml")
    file.write(SITEMAP)
    file_path = os.path.join(file.dirname, file.basename)

    # Read the file
    read_contents = load_local_sitemap(file_path)
    assert read_contents == SITEMAP


def test_load_local_file_with_prefix(tmpdir):
    # Write a file using pytest's tmpdir so we can read it back
    file = tmpdir.join("sitemap.xml")
    file.write(SITEMAP)
    file_path = os.path.join(LOCAL_PREFIX, file.dirname, file.basename)

    # Read the file
    read_contents = load_local_sitemap(file_path)
    assert read_contents == SITEMAP


def test_file_does_not_exist(tmpdir):
    file_path = "{}/tmp/not_a_real_file".format(LOCAL_PREFIX)

    with pytest.raises(IOError):
        load_local_sitemap(file_path)


def test_file_is_remote(tmpdir):
    file_path = "https://alexgude.com/sitemap.xml"

    with pytest.raises(IOError):
        load_local_sitemap(file_path)


def test_file_path_is_invalid(tmpdir):
    file_path = "tmp/file_path"

    with pytest.raises(IOError):
        load_local_sitemap(file_path)
