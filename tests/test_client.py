from unittest.mock import MagicMock

import pytest
import requests
import tenacity

from ztm_ingest.client import ApiError, TransientApiError, ZtmClient


def _response(status=200, json_body=None, json_error=False):
    resp = MagicMock()
    resp.status_code = status
    if json_error:
        resp.json.side_effect = ValueError("bad json")
    else:
        resp.json.return_value = json_body
    return resp


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    monkeypatch.setattr(tenacity.nap.time, "sleep", lambda _s: None)


def test_returns_records_from_result_key(settings, sample_records):
    session = MagicMock()
    session.get.return_value = _response(json_body={"result": sample_records})
    assert ZtmClient(settings, session).fetch_vehicle_positions(1) == sample_records


def test_rejects_unknown_vehicle_type(settings):
    with pytest.raises(ValueError):
        ZtmClient(settings, MagicMock()).fetch_vehicle_positions(3)


def test_retries_on_500_then_succeeds(settings, sample_records):
    session = MagicMock()
    session.get.side_effect = [
        _response(500),
        _response(json_body={"result": sample_records}),
    ]
    assert ZtmClient(settings, session).fetch_vehicle_positions(1) == sample_records
    assert session.get.call_count == 2


def test_gives_up_after_max_retries(settings):
    session = MagicMock()
    session.get.return_value = _response(503)
    with pytest.raises(TransientApiError):
        ZtmClient(settings, session).fetch_vehicle_positions(1)
    assert session.get.call_count == settings.max_retries


def test_does_not_retry_client_errors(settings):
    session = MagicMock()
    session.get.return_value = _response(401)
    with pytest.raises(ApiError):
        ZtmClient(settings, session).fetch_vehicle_positions(1)
    assert session.get.call_count == 1


def test_string_result_is_treated_as_api_error(settings):
    # The API sometimes answers 200 with {"result": "<error text>"}
    session = MagicMock()
    session.get.return_value = _response(json_body={"result": "Błędny apikey"})
    with pytest.raises(TransientApiError):
        ZtmClient(settings, session).fetch_vehicle_positions(1)


def test_api_key_never_leaks_into_error_message(settings):
    session = MagicMock()
    session.get.side_effect = requests.ConnectionError(
        "https://api.um.warszawa.pl/?apikey=test-key failed"
    )
    with pytest.raises(TransientApiError) as exc:
        ZtmClient(settings, session).fetch_vehicle_positions(1)
    assert "test-key" not in str(exc.value)
    assert exc.value.__cause__ is None
