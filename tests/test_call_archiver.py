import pytest
from wayback_machine_archiver.clients import ArchiveClient
from requests.adapters import HTTPAdapter
import requests


@pytest.fixture
def session():
    session = requests.Session()
    session.mount("https://", HTTPAdapter())
    session.mount("http://", HTTPAdapter())
    return session


def test_call_archiver(requests_mock, session):
    url = "https://web.archive.org/save/yahoo.com"
    requests_mock.head(url)
    client = ArchiveClient(session=session)
    client.archive(url, rate_limit_wait=0)
    assert True  # client.archive will raise if it fails


def test_call_archiver_with_404(requests_mock, session):
    url = "https://web.archive.org/save/yahoo.com"
    requests_mock.head(url, status_code=404)
    with pytest.raises(requests.exceptions.HTTPError):
        client = ArchiveClient(session=session)
        client.archive(url, rate_limit_wait=0)
