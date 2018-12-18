import requests
import re
import xml.etree.ElementTree as ET


def archive_url(url):
    """Submit a url to the Internet Archive to archive."""
    SAVE_URL = "https://web.archive.org/save/"
    r = requests.get(SAVE_URL + url)

    # Raise `requests.exceptions.HTTPError` if 4XX or 5XX status
    r.raise_for_status()


def get_namespace(element):
    """Extract the namespace using a regular expression."""
    match = re.match('\{.*\}', element.tag)
    return match.group(0) if match else ''


def download_sitemap(site_map_url):
    """Download the sitemap of the target website."""
    r = requests.get(site_map_url)
    root = ET.fromstring(r.text)

    # Sitemaps use a namespace in the XML, which we need to read
    ns = get_namespace(root)

    urls = []
    for loc_node in root.findall(".//{}loc".format(ns)):
        urls.append(loc_node.text)

    return set(urls)


if __name__ == "__main__":

    urls = download_sitemap("https://alexgude.com/sitemap.xml")
    for url in urls:
        print(url)
        print("\n")
        archive_url(url)
