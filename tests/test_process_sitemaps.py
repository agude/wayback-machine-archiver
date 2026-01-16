"""Tests for sitemaps.process_sitemaps orchestration function."""

import logging

import pytest
import requests

from wayback_machine_archiver.sitemaps import LOCAL_PREFIX, process_sitemaps

# Test data
VALID_SITEMAP_XML = """<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
    <url><loc>https://example.com/page1</loc></url>
    <url><loc>https://example.com/page2</loc></url>
</urlset>
"""

INVALID_XML = "not valid xml at all <><><>"


@pytest.fixture
def session():
    """Create a requests session for testing."""
    return requests.Session()


def test_process_sitemaps_with_remote_sitemap(requests_mock, session):
    """Verify that process_sitemaps downloads and parses remote sitemaps."""
    url = "https://example.com/sitemap.xml"
    requests_mock.get(url, content=VALID_SITEMAP_XML.encode("UTF-8"))

    result = process_sitemaps([url], session)

    assert result == {"https://example.com/page1", "https://example.com/page2"}


def test_process_sitemaps_with_local_sitemap(session, tmp_path):
    """Verify that process_sitemaps loads and parses local sitemaps."""
    file = tmp_path / "sitemap.xml"
    file.write_bytes(VALID_SITEMAP_XML.encode("UTF-8"))
    local_path = f"{LOCAL_PREFIX}{file}"

    result = process_sitemaps([local_path], session)

    assert result == {"https://example.com/page1", "https://example.com/page2"}


def test_process_sitemaps_combines_multiple_sources(requests_mock, session, tmp_path):
    """Verify that URLs from multiple sitemaps are combined into one set."""
    # Set up remote sitemap
    remote_url = "https://example.com/sitemap.xml"
    requests_mock.get(remote_url, content=VALID_SITEMAP_XML.encode("UTF-8"))

    # Set up local sitemap with different URLs
    local_sitemap = """<?xml version="1.0" encoding="UTF-8"?>
    <urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
        <url><loc>https://other.com/page3</loc></url>
    </urlset>
    """
    file = tmp_path / "sitemap.xml"
    file.write_bytes(local_sitemap.encode("UTF-8"))
    local_path = f"{LOCAL_PREFIX}{file}"

    result = process_sitemaps([remote_url, local_path], session)

    assert result == {
        "https://example.com/page1",
        "https://example.com/page2",
        "https://other.com/page3",
    }


def test_process_sitemaps_handles_xml_parse_error(requests_mock, session, caplog):
    """Verify that XML parse errors are caught, logged, and processing continues."""
    url = "https://example.com/bad-sitemap.xml"
    requests_mock.get(url, content=INVALID_XML.encode("UTF-8"))

    with caplog.at_level(logging.ERROR):
        result = process_sitemaps([url], session)

    assert result == set()
    assert "not valid XML" in caplog.text


def test_process_sitemaps_handles_network_error(requests_mock, session, caplog):
    """Verify that network errors are caught, logged, and processing continues."""
    good_url = "https://example.com/sitemap.xml"
    bad_url = "https://bad.com/sitemap.xml"

    requests_mock.get(good_url, content=VALID_SITEMAP_XML.encode("UTF-8"))
    requests_mock.get(bad_url, status_code=500)

    with caplog.at_level(logging.ERROR):
        result = process_sitemaps([bad_url, good_url], session)

    # Should still get URLs from the good sitemap
    assert result == {"https://example.com/page1", "https://example.com/page2"}
    assert "An error occurred" in caplog.text


def test_process_sitemaps_empty_list(session):
    """Verify that an empty sitemap list returns an empty set."""
    result = process_sitemaps([], session)

    assert result == set()
