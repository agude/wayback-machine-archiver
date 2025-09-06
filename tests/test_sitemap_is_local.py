from wayback_machine_archiver.sitemaps import sitemap_is_local, LOCAL_PREFIX


def test_local():
    URIS = (
        "/tmp/sitemap.xml",
        "{prefix}/tmp/sitemap.xml".format(prefix=LOCAL_PREFIX),
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
