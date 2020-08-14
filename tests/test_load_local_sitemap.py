# -*- coding: UTF-8 -*-
from __future__ import unicode_literals
from wayback_machine_archiver.archiver import load_local_sitemap, LOCAL_PREFIX
import os.path
import pytest


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
