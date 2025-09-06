import pytest
from wayback_machine_archiver.clients import SPN2Client
from requests.adapters import HTTPAdapter
import requests
import urllib.parse


@pytest.fixture
def session():
    session = requests.Session()
    session.mount("https://", HTTPAdapter())
    session.mount("http://", HTTPAdapter())
    return session


@pytest.mark.parametrize(
    "api_params",
    [
        (None),
        ({"capture_outlinks": "1", "js_behavior_timeout": 0}),
        ({"capture_screenshot": "1", "force_get": "1"}),
    ],
)
def test_spn2_client_submit_capture(requests_mock, session, api_params):
    """
    Verify that submit_capture sends a correct POST request, including optional
    API parameters, and returns the job_id.
    """
    access_key = "test-access"
    secret_key = "test-secret"
    url_to_archive = "https://example.com"
    expected_job_id = "c4b1-4f2a-ac04-1d1225e98695"

    requests_mock.post(
        SPN2Client.SAVE_URL, json={"job_id": expected_job_id}, status_code=200
    )

    client = SPN2Client(session=session, access_key=access_key, secret_key=secret_key)
    job_id = client.submit_capture(
        url_to_archive, rate_limit_wait=0, api_params=api_params
    )

    # Assertions
    assert job_id == expected_job_id
    history = requests_mock.request_history
    assert len(history) == 1
    request = history[0]
    assert request.method == "POST"
    assert request.url == SPN2Client.SAVE_URL
    assert f"LOW {access_key}:{secret_key}" == request.headers["Authorization"]

    expected_payload = {"url": url_to_archive}
    if api_params:
        expected_payload.update(api_params)
    expected_body = urllib.parse.urlencode(expected_payload)
    assert request.text == expected_body


def test_spn2_client_check_status_success(requests_mock, session):
    """
    Verify check_status correctly parses a 'success' response.
    """
    job_id = "test-job-123"
    status_url = SPN2Client.STATUS_URL_TEMPLATE.format(job_id=job_id)
    success_payload = {
        "status": "success",
        "original_url": "https://example.com",
        "timestamp": "20250101000000",
    }
    requests_mock.get(status_url, json=success_payload)

    client = SPN2Client(session=session, access_key="key", secret_key="secret")
    status_data = client.check_status(job_id)

    assert status_data == success_payload


def test_spn2_client_check_status_pending(requests_mock, session):
    """
    Verify check_status correctly parses a 'pending' response.
    """
    job_id = "test-job-456"
    status_url = SPN2Client.STATUS_URL_TEMPLATE.format(job_id=job_id)
    pending_payload = {"status": "pending"}
    requests_mock.get(status_url, json=pending_payload)

    client = SPN2Client(session=session, access_key="key", secret_key="secret")
    status_data = client.check_status(job_id)

    assert status_data == pending_payload


def test_spn2_client_check_status_error(requests_mock, session):
    """
    Verify check_status correctly parses an 'error' response.
    """
    job_id = "test-job-789"
    status_url = SPN2Client.STATUS_URL_TEMPLATE.format(job_id=job_id)
    error_payload = {"status": "error", "message": "Too many redirects."}
    requests_mock.get(status_url, json=error_payload)

    client = SPN2Client(session=session, access_key="key", secret_key="secret")
    status_data = client.check_status(job_id)

    assert status_data == error_payload
