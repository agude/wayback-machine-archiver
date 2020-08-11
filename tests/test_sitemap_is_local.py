from wayback_machine_archiver.archiver import sitemap_is_local


def test_local():
    URIS = (
        "/tmp/sitemap.xml",
        "file:///tmp/sitemap.xml",
    )
    for uri in URIS:
        assert sitemap_is_local(uri)


def test_remote():
    URIS = (
        "https://alexgude.com/sitemap.xml",
        "http://charles.uno/sitemap.xml",
    )
    for uri in URIS:
        assert not sitemap_is_local(uri)
