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


def test_spn2_client_submit_capture(requests_mock, session):
    """
    Verify that submit_capture sends a correct POST request and returns the job_id.
    """
    access_key = "test-access"
    secret_key = "test-secret"
    url_to_archive = "https://example.com"
    expected_job_id = "c4b1-4f2a-ac04-1d1225e98695"

    # Mock the POST request to the SPN2 API
    requests_mock.post(
        SPN2Client.SAVE_URL, json={"job_id": expected_job_id}, status_code=200
    )

    client = SPN2Client(session=session, access_key=access_key, secret_key=secret_key)
    job_id = client.submit_capture(url_to_archive)

    # Assertions
    assert job_id == expected_job_id
    history = requests_mock.request_history
    assert len(history) == 1
    request = history[0]
    assert request.method == "POST"
    assert request.url == SPN2Client.SAVE_URL
    assert f"LOW {access_key}:{secret_key}" == request.headers["Authorization"]
    assert f"url={url_to_archive}" == request.text
