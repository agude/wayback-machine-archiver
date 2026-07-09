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


def test_process_sitemaps_recurses_into_sitemap_index(requests_mock, session):
    """Verify that a sitemap index is recursed to fetch child sitemaps."""
    index_url = "https://example.com/sitemap_index.xml"
    child_url = "https://example.com/sitemap1.xml"

    index_xml = f"""<?xml version="1.0" encoding="UTF-8"?>
    <sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
        <sitemap><loc>{child_url}</loc></sitemap>
    </sitemapindex>
    """
    child_xml = """<?xml version="1.0" encoding="UTF-8"?>
    <urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
        <url><loc>https://example.com/deep-page</loc></url>
    </urlset>
    """

    requests_mock.get(index_url, content=index_xml.encode("UTF-8"))
    requests_mock.get(child_url, content=child_xml.encode("UTF-8"))

    result = process_sitemaps([index_url], session)

    assert result == {"https://example.com/deep-page"}
    assert requests_mock.call_count == 2


def test_process_sitemaps_respects_depth_limit(requests_mock, session, caplog):
    """Verify that sitemap index recursion stops at the depth limit."""
    from wayback_machine_archiver.sitemaps import MAX_SITEMAP_INDEX_DEPTH

    urls = [
        f"https://example.com/sitemap_level{i}.xml"
        for i in range(MAX_SITEMAP_INDEX_DEPTH + 2)
    ]

    for i in range(MAX_SITEMAP_INDEX_DEPTH + 1):
        child = urls[i + 1]
        xml = f"""<?xml version="1.0" encoding="UTF-8"?>
        <sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
            <sitemap><loc>{child}</loc></sitemap>
        </sitemapindex>
        """
        requests_mock.get(urls[i], content=xml.encode("UTF-8"))

    with caplog.at_level(logging.WARNING):
        result = process_sitemaps([urls[0]], session)

    assert result == set()
    assert "depth limit" in caplog.text
