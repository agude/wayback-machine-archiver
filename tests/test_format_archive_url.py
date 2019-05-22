from wayback_machine_archiver.archiver import format_archive_url


def test_archive_org():
    BASE = "https://web.archive.org/save/"
    URLS = (
        "https://alexgude.com",
        "http://charles.uno",
    )

    for url in URLS:
        assert BASE + url == format_archive_url(url)
