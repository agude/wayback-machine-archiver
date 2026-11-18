from __future__ import annotations

import tempfile
from collections import Counter, deque
from dataclasses import dataclass
from pathlib import Path
from unittest.mock import patch

import requests
from hypothesis import given
from hypothesis import strategies as st

from wayback_machine_archiver import sitemaps
from wayback_machine_archiver.sitemaps import (
    MAX_SITEMAP_INDEX_DEPTH,
    extract_urls_from_sitemap,
    load_local_sitemap,
    process_sitemaps,
)

SITEMAP_NAMESPACE = "http://www.sitemaps.org/schemas/sitemap/0.9"
IMAGE_NAMESPACE = "http://www.google.com/schemas/sitemap-image/1.1"
XHTML_NAMESPACE = "http://www.w3.org/1999/xhtml"

url_paths = st.text(
    alphabet="abcdefghijklmnopqrstuvwxyz0123456789-_/.",
    min_size=0,
    max_size=12,
)
page_urls = st.sets(
    url_paths.map(lambda path: f"https://example.test/{path}"), min_size=1, max_size=5
)


def _namespace_attributes(*, with_sitemap_namespace: bool) -> str:
    sitemap_attribute = f' xmlns="{SITEMAP_NAMESPACE}"' if with_sitemap_namespace else ""
    return f'{sitemap_attribute} xmlns:image="{IMAGE_NAMESPACE}" xmlns:xhtml="{XHTML_NAMESPACE}"'


def _foreign_siblings() -> str:
    return (
        "<image:loc>https://ignored.test/image.jpg</image:loc>"
        '<xhtml:link rel="alternate" href="https://ignored.test/alternate" />'
    )


def _urlset_xml(urls: set[str], *, with_sitemap_namespace: bool) -> bytes:
    attributes = _namespace_attributes(with_sitemap_namespace=with_sitemap_namespace)
    entries = "".join(f"<url><loc>{url}</loc>{_foreign_siblings()}</url>" for url in sorted(urls))
    return f"<urlset{attributes}>{entries}</urlset>".encode()


def _sitemapindex_xml(urls: set[str], *, with_sitemap_namespace: bool) -> bytes:
    attributes = _namespace_attributes(with_sitemap_namespace=with_sitemap_namespace)
    entries = "".join(
        f"<sitemap><loc>{url}</loc>{_foreign_siblings()}</sitemap>" for url in sorted(urls)
    )
    return f"<sitemapindex{attributes}>{entries}</sitemapindex>".encode()


@given(urls=page_urls)
def test_round_trip_namespaced_urlsets_and_indexes(urls: set[str]) -> None:
    pages, child_sitemaps = extract_urls_from_sitemap(
        _urlset_xml(urls, with_sitemap_namespace=True)
    )
    assert pages == urls
    assert child_sitemaps == set()

    pages, child_sitemaps = extract_urls_from_sitemap(
        _sitemapindex_xml(urls, with_sitemap_namespace=True)
    )
    assert pages == set()
    assert child_sitemaps == urls


@given(urls=page_urls)
def test_round_trip_unqualified_urlsets_and_indexes(urls: set[str]) -> None:
    pages, child_sitemaps = extract_urls_from_sitemap(
        _urlset_xml(urls, with_sitemap_namespace=False)
    )
    assert pages == urls
    assert child_sitemaps == set()

    pages, child_sitemaps = extract_urls_from_sitemap(
        _sitemapindex_xml(urls, with_sitemap_namespace=False)
    )
    assert pages == set()
    assert child_sitemaps == urls


@given(
    url_path=url_paths.filter(bool),
    leading=st.text(alphabet=" \t\n", min_size=1, max_size=3),
    trailing=st.text(alphabet=" \t\n", min_size=0, max_size=3),
    use_cdata=st.booleans(),
)
def test_loc_whitespace_and_cdata_are_stripped(
    url_path: str,
    leading: str,
    trailing: str,
    use_cdata: bool,
) -> None:
    url = f"https://example.test/{url_path}"
    text = f"{leading}{url}{trailing}"
    loc_content = f"<![CDATA[{text}]]>" if use_cdata else text
    sitemap_xml = f"<urlset><url><loc>{loc_content}</loc></url></urlset>".encode()

    pages, child_sitemaps = extract_urls_from_sitemap(sitemap_xml)

    assert pages == {url}
    assert child_sitemaps == set()


@dataclass(frozen=True)
class SitemapNode:
    children: tuple[int, ...]
    page_url: str | None


@st.composite
def acyclic_sitemap_graphs(draw) -> tuple[SitemapNode, ...]:
    node_count = draw(st.integers(min_value=3, max_value=6))
    edges = [set() for _ in range(node_count)]
    # Keep a diamond in every example to exercise shared children.
    edges[0].update((1, 2))
    edges[1].add(2)

    for source in range(node_count):
        for target in range(source + 1, node_count):
            if target not in edges[source] and draw(st.booleans()):
                edges[source].add(target)

    return _nodes_from_edges(edges)


@st.composite
def cyclic_sitemap_graphs(draw) -> tuple[SitemapNode, ...]:
    node_count = draw(st.integers(min_value=1, max_value=6))
    edges = [set() for _ in range(node_count)]
    edges[0].add(0)

    for source in range(node_count):
        for target in range(node_count):
            if target not in edges[source] and draw(st.booleans()):
                edges[source].add(target)

    return _nodes_from_edges(edges)


def _nodes_from_edges(edges: list[set[int]]) -> tuple[SitemapNode, ...]:
    return tuple(
        SitemapNode(
            children=tuple(sorted(children)),
            page_url=None if children else f"https://example.test/page/{index}",
        )
        for index, children in enumerate(edges)
    )


def _graph_sitemap_xml(node: SitemapNode, node_urls: tuple[str, ...]) -> bytes:
    if node.children:
        entries = "".join(
            f"<sitemap><loc>{node_urls[index]}</loc></sitemap>" for index in node.children
        )
        return f"<sitemapindex>{entries}</sitemapindex>".encode()

    assert node.page_url is not None
    return f"<urlset><url><loc>{node.page_url}</loc></url></urlset>".encode()


def _reference_breadth_first(
    nodes: tuple[SitemapNode, ...], node_urls: tuple[str, ...]
) -> tuple[set[str], set[str]]:
    queue = deque([(0, 0)])
    visited_urls: set[str] = set()
    result_urls: set[str] = set()

    while queue:
        node_index, depth = queue.popleft()
        node_url = node_urls[node_index]
        if node_url in visited_urls:
            continue

        visited_urls.add(node_url)
        node = nodes[node_index]
        if node.page_url is not None:
            result_urls.add(node.page_url)
        elif depth < MAX_SITEMAP_INDEX_DEPTH:
            queue.extend((child_index, depth + 1) for child_index in node.children)

    return result_urls, visited_urls


def _assert_sitemap_graph_matches_reference(nodes: tuple[SitemapNode, ...]) -> None:
    node_urls = tuple(f"https://example.test/sitemap/{index}.xml" for index in range(len(nodes)))
    xml_by_url = {
        node_urls[index]: _graph_sitemap_xml(node, node_urls) for index, node in enumerate(nodes)
    }
    fetch_counts: Counter[str] = Counter()

    def fake_fetch(sitemap_url: str, _session: requests.Session) -> bytes:
        fetch_counts[sitemap_url] += 1
        return xml_by_url[sitemap_url]

    expected_urls, expected_fetches = _reference_breadth_first(nodes, node_urls)

    with (
        patch.object(sitemaps, "_fetch_sitemap_bytes", fake_fetch),
        patch.object(sitemaps.logging, "warning"),
        requests.Session() as session,
    ):
        actual_urls = process_sitemaps([node_urls[0]], session)

    assert actual_urls == expected_urls
    assert fetch_counts == Counter(expected_fetches)


@given(graph=acyclic_sitemap_graphs())
def test_acyclic_sitemap_graphs_match_reference_and_fetch_once(
    graph: tuple[SitemapNode, ...],
) -> None:
    _assert_sitemap_graph_matches_reference(graph)


@given(graph=cyclic_sitemap_graphs())
def test_cyclic_sitemap_graphs_match_reference_and_fetch_once(
    graph: tuple[SitemapNode, ...],
) -> None:
    _assert_sitemap_graph_matches_reference(graph)


@given(failure_mode=st.sampled_from(("invalid_xml", "io_error")))
def test_failed_sitemap_does_not_discard_successful_siblings(
    failure_mode: str,
) -> None:
    index_url = "https://example.test/index.xml"
    broken_url = "https://example.test/broken.xml"
    good_url = "https://example.test/good.xml"
    sitemap_index = (
        f"<sitemapindex><sitemap><loc>{broken_url}</loc></sitemap>"
        f"<sitemap><loc>{good_url}</loc></sitemap></sitemapindex>"
    ).encode()
    good_sitemap = b"<urlset><url><loc>https://example.test/page</loc></url></urlset>"

    def fake_fetch(sitemap_url: str, _session: requests.Session) -> bytes:
        if sitemap_url == index_url:
            return sitemap_index
        if sitemap_url == broken_url and failure_mode == "io_error":
            raise OSError("unreadable sitemap")
        if sitemap_url == broken_url:
            return b"<urlset><url>"
        return good_sitemap

    with patch.object(sitemaps, "_fetch_sitemap_bytes", fake_fetch), requests.Session() as session:
        actual_urls = process_sitemaps([index_url], session)

    assert actual_urls == {"https://example.test/page"}


def test_depth_cap_does_not_fetch_children_beyond_limit() -> None:
    node_urls = tuple(
        f"https://example.test/sitemap/{index}.xml" for index in range(MAX_SITEMAP_INDEX_DEPTH + 2)
    )
    xml_by_url = {
        node_urls[index]: (
            f"<sitemapindex><sitemap><loc>{node_urls[index + 1]}</loc></sitemap></sitemapindex>"
        ).encode()
        for index in range(MAX_SITEMAP_INDEX_DEPTH + 1)
    }
    xml_by_url[node_urls[-1]] = (
        b"<urlset><url><loc>https://example.test/too-deep</loc></url></urlset>"
    )
    fetched_urls: list[str] = []

    def fake_fetch(sitemap_url: str, _session: requests.Session) -> bytes:
        fetched_urls.append(sitemap_url)
        return xml_by_url[sitemap_url]

    with patch.object(sitemaps, "_fetch_sitemap_bytes", fake_fetch), requests.Session() as session:
        actual_urls = process_sitemaps([node_urls[0]], session)

    assert fetched_urls == list(node_urls[:-1])
    assert actual_urls == set()


@given(contents=st.binary(max_size=128))
def test_local_sitemap_path_and_file_uri_load_same_bytes(contents: bytes) -> None:
    with tempfile.TemporaryDirectory() as temporary_directory:
        sitemap_path = Path(temporary_directory) / "sitemap.xml"
        sitemap_path.write_bytes(contents)

        assert load_local_sitemap(str(sitemap_path)) == contents
        assert load_local_sitemap(f"file://{sitemap_path}") == contents
