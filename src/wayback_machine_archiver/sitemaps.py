from __future__ import annotations

import logging
import re
from collections import deque
from xml.etree.ElementTree import Element, ParseError

import defusedxml.ElementTree as ET

import requests

from . import REQUEST_TIMEOUT

LOCAL_PREFIX = "file://"
MAX_SITEMAP_INDEX_DEPTH = 5

__all__ = ["LOCAL_PREFIX", "process_sitemaps"]


def get_namespace(element: Element) -> str:
    """Extract the namespace from an XML element."""
    match = re.match(r"\{.*\}", element.tag)
    return match.group(0) if match else ""


def download_remote_sitemap(sitemap_url: str, session: requests.Session) -> bytes:
    """Download a remote sitemap file."""
    logging.debug("Downloading: %s", sitemap_url)
    r = session.get(sitemap_url, timeout=REQUEST_TIMEOUT)
    r.raise_for_status()
    return r.content


def load_local_sitemap(sitemap_filepath: str) -> bytes:
    """Load a local sitemap file."""
    logging.debug("Loading local sitemap: %s", sitemap_filepath)
    if sitemap_filepath.startswith(LOCAL_PREFIX):
        sitemap_filepath = sitemap_filepath[len(LOCAL_PREFIX) :]
    with open(sitemap_filepath, "rb") as fp:
        return fp.read()


def sitemap_is_local(sitemap_url: str) -> bool:
    """Check if a sitemap URI is local."""
    return sitemap_url.startswith(LOCAL_PREFIX)


def _is_sitemap_index(root: Element, namespace: str) -> bool:
    """Check if the root element is a sitemapindex."""
    tag = root.tag.removeprefix(namespace)
    return tag == "sitemapindex"


def extract_urls_from_sitemap(sitemap_bytes: bytes) -> tuple[set[str], set[str]]:
    """Parse XML sitemap bytes and extract page URLs and child sitemap URLs.

    Returns (page_urls, child_sitemap_urls). For a regular urlset sitemap,
    child_sitemap_urls is empty. For a sitemapindex, page_urls is empty.
    """
    root = ET.fromstring(sitemap_bytes)
    namespace = get_namespace(root)
    loc_nodes = root.findall(f".//{namespace}loc")
    urls = {node.text for node in loc_nodes if node.text is not None}

    if _is_sitemap_index(root, namespace):
        return set(), urls
    return urls, set()


def _fetch_sitemap_bytes(
    sitemap_url: str, session: requests.Session
) -> bytes:
    """Fetch sitemap bytes from a local or remote source."""
    if sitemap_is_local(sitemap_url):
        logging.debug("The sitemap '%s' is local.", sitemap_url)
        return load_local_sitemap(sitemap_url)
    logging.debug("The sitemap '%s' is remote.", sitemap_url)
    return download_remote_sitemap(sitemap_url, session)


def process_sitemaps(
    sitemap_urls: list[str],
    session: requests.Session,
) -> set[str]:
    """
    Given a list of sitemap URLs, downloads/loads them and returns a set of all unique URLs found.
    Recurses into sitemap index files up to MAX_SITEMAP_INDEX_DEPTH levels.
    """
    all_urls: set[str] = set()
    queue: deque[tuple[str, int]] = deque((url, 0) for url in sitemap_urls)

    while queue:
        sitemap_url, depth = queue.popleft()
        try:
            sitemap_xml = _fetch_sitemap_bytes(sitemap_url, session)
            page_urls, child_sitemaps = extract_urls_from_sitemap(sitemap_xml)
            all_urls.update(page_urls)

            if child_sitemaps:
                if depth >= MAX_SITEMAP_INDEX_DEPTH:
                    logging.warning(
                        "Sitemap index recursion depth limit (%d) reached at '%s'. Skipping child sitemaps.",
                        MAX_SITEMAP_INDEX_DEPTH,
                        sitemap_url,
                    )
                else:
                    logging.info(
                        "Found sitemap index '%s' with %d child sitemaps.",
                        sitemap_url,
                        len(child_sitemaps),
                    )
                    queue.extend((url, depth + 1) for url in child_sitemaps)
        except ParseError:
            logging.error(
                "Failed to parse sitemap from '%s'. The content is not valid XML. Please ensure the URL points directly to a sitemap.xml file. Skipping this sitemap.",
                sitemap_url,
            )
        except (requests.exceptions.RequestException, OSError) as e:
            logging.error(
                "An error occurred while processing sitemap '%s': %s. Skipping.",
                sitemap_url,
                e,
            )
    return all_urls
