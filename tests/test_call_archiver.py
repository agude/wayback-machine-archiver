import pytest
from wayback_machine_archiver.archiver import call_archiver
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
    call_archiver(url, rate_limit_wait=0, session=session)
    assert True  # call_archiver will raise if it fails


def test_call_archiver_with_404(requests_mock, session):
    url = "https://web.archive.org/save/yahoo.com"
    requests_mock.head(url, status_code=404)
    with pytest.raises(requests.exceptions.HTTPError):
        call_archiver(url, rate_limit_wait=0, session=session)
