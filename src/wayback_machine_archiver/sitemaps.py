from __future__ import annotations

import logging
import re
import xml.etree.ElementTree as ET
from xml.etree.ElementTree import Element, ParseError

import requests

LOCAL_PREFIX = "file://"

__all__ = ["LOCAL_PREFIX", "process_sitemaps"]


def get_namespace(element: Element) -> str:
    """Extract the namespace from an XML element."""
    match = re.match(r"\{.*\}", element.tag)
    return match.group(0) if match else ""


def download_remote_sitemap(sitemap_url: str, session: requests.Session) -> bytes:
    """Download a remote sitemap file."""
    logging.debug("Downloading: %s", sitemap_url)
    r = session.get(sitemap_url)
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
    return sitemap_url.startswith(LOCAL_PREFIX) or sitemap_url.startswith("/")


def extract_urls_from_sitemap(sitemap_bytes: bytes) -> set[str]:
    """Parse XML sitemap bytes and extract URLs."""
    root = ET.fromstring(sitemap_bytes)
    namespace = get_namespace(root)
    loc_nodes = root.findall(f".//{namespace}loc")
    return {node.text for node in loc_nodes if node.text is not None}


def process_sitemaps(
    sitemap_urls: list[str],
    session: requests.Session,
) -> set[str]:
    """
    Given a list of sitemap URLs, downloads/loads them and returns a set of all unique URLs found.
    """
    all_urls: set[str] = set()
    for sitemap_url in sitemap_urls:
        try:
            if sitemap_is_local(sitemap_url):
                logging.debug("The sitemap '%s' is local.", sitemap_url)
                sitemap_xml = load_local_sitemap(sitemap_url)
            else:
                logging.debug("The sitemap '%s' is remote.", sitemap_url)
                sitemap_xml = download_remote_sitemap(sitemap_url, session)

            extracted_urls = extract_urls_from_sitemap(sitemap_xml)
            all_urls.update(extracted_urls)
        except ParseError:
            logging.error(
                "Failed to parse sitemap from '%s'. The content is not valid XML. Please ensure the URL points directly to a sitemap.xml file. Skipping this sitemap.",
                sitemap_url,
            )
        except (requests.exceptions.RequestException, OSError) as e:
            # RequestException: network errors for remote sitemaps
            # OSError: file read errors for local sitemaps
            logging.error(
                "An error occurred while processing sitemap '%s': %s. Skipping.",
                sitemap_url,
                e,
            )
    return all_urls
