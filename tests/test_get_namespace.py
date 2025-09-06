from collections import namedtuple
from wayback_machine_archiver.sitemaps import get_namespace

ELEMENT = namedtuple("Element", "tag")


def test_good_namespace():
    NAMESPACE = "{http://www.sitemaps.org/schemas/sitemap/0.9}"
    test_element = ELEMENT("{namespace}urlset".format(namespace=NAMESPACE))

    assert get_namespace(test_element) == NAMESPACE


def test_no_match_namespace():
    NAMESPACE = ""
    test_element = ELEMENT("{namespace}urlset".format(namespace=NAMESPACE))

    assert get_namespace(test_element) == NAMESPACE
