import pytest
from wayback_machine_archiver.clients import SPN2Client
from requests.adapters import HTTPAdapter
import requests


@pytest.fixture
def session():
    session = requests.Session()
    session.mount("https://", HTTPAdapter())
    session.mount("http://", HTTPAdapter())
    return session


def test_spn2_client_archive_placeholder(requests_mock, session):
    """
    Tests the placeholder archive method for SPN2Client.
    It should currently behave exactly like the LegacyClient.
    """
    url = "https://web.archive.org/save/yahoo.com"
    requests_mock.head(url)
    client = SPN2Client(session=session)
    client.archive(url, rate_limit_wait=0)
    assert True  # Will raise if it fails


def test_spn2_client_archive_placeholder_with_404(requests_mock, session):
    """
    Tests the placeholder archive method for SPN2Client with an error status.
    """
    url = "https://web.archive.org/save/yahoo.com"
    requests_mock.head(url, status_code=404)
    with pytest.raises(requests.exceptions.HTTPError):
        client = SPN2Client(session=session)
        client.archive(url, rate_limit_wait=0)
