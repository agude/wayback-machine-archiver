from wayback_machine_archiver.sitemaps import LOCAL_PREFIX, sitemap_is_local


def test_local():
    assert sitemap_is_local(f"{LOCAL_PREFIX}/tmp/sitemap.xml")


def test_bare_slash_is_not_local():
    assert not sitemap_is_local("/tmp/sitemap.xml")


def test_remote():
    URIS = (
        "https://alexgude.com/sitemap.xml",
        "http://charles.uno/sitemap.xml",
    )
    for uri in URIS:
        assert not sitemap_is_local(uri)
