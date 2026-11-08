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
    session.post.return_value = _response(json_body={"result": sample_records})
    assert ZtmClient(settings, session).fetch_vehicle_positions(1) == sample_records


def test_request_matches_the_documented_api_call(settings, sample_records):
    session = MagicMock()
    session.post.return_value = _response(json_body={"result": sample_records})

    ZtmClient(settings, session).fetch_vehicle_positions(2)

    args, kwargs = session.post.call_args
    assert args[0] == settings.api_base_url
    assert kwargs["json"] == {"type": 2}
    assert kwargs["headers"] == {
        "Authorization": "test-key",  # raw token, no scheme prefix
        "User-Agent": settings.user_agent,
    }
    assert "params" not in kwargs  # the key must not be in the URL


def test_invalid_json_is_retried_then_raises(settings):
    session = MagicMock()
    session.post.return_value = _response(json_error=True)
    with pytest.raises(TransientApiError):
        ZtmClient(settings, session).fetch_vehicle_positions(1)
    assert session.post.call_count == settings.max_retries


def test_rejects_unknown_vehicle_type(settings):
    with pytest.raises(ValueError):
        ZtmClient(settings, MagicMock()).fetch_vehicle_positions(3)


def test_retries_on_500_then_succeeds(settings, sample_records):
    session = MagicMock()
    session.post.side_effect = [
        _response(500),
        _response(json_body={"result": sample_records}),
    ]
    assert ZtmClient(settings, session).fetch_vehicle_positions(1) == sample_records
    assert session.post.call_count == 2


def test_gives_up_after_max_retries(settings):
    session = MagicMock()
    session.post.return_value = _response(503)
    with pytest.raises(TransientApiError):
        ZtmClient(settings, session).fetch_vehicle_positions(1)
    assert session.post.call_count == settings.max_retries


def test_does_not_retry_client_errors(settings):
    session = MagicMock()
    session.post.return_value = _response(401)
    with pytest.raises(ApiError):
        ZtmClient(settings, session).fetch_vehicle_positions(1)
    assert session.post.call_count == 1


def test_string_result_is_a_permanent_error_with_visible_message(settings):
    session = MagicMock()
    session.post.return_value = _response(json_body={"result": "Błędny token"})
    with pytest.raises(ApiError, match="Błędny token") as exc:
        ZtmClient(settings, session).fetch_vehicle_positions(1)
    assert not isinstance(exc.value, TransientApiError)
    assert session.post.call_count == 1  # not retried


def test_error_message_is_redacted_and_truncated(settings):
    session = MagicMock()
    session.post.return_value = _response(json_body={"result": "bad key test-key " + "x" * 500})
    with pytest.raises(ApiError) as exc:
        ZtmClient(settings, session).fetch_vehicle_positions(1)
    assert "test-key" not in str(exc.value)
    assert len(str(exc.value)) < 300


def test_unknown_response_shape_reports_keys_not_values(settings):
    session = MagicMock()
    session.post.return_value = _response(json_body={"success": True, "data": {"secret": 1}})
    with pytest.raises(ApiError, match="keys=") as exc:
        ZtmClient(settings, session).fetch_vehicle_positions(1)
    assert "secret" not in str(exc.value)
    assert not isinstance(exc.value, TransientApiError)


def test_api_key_never_leaks_into_error_message(settings):
    session = MagicMock()
    session.post.side_effect = requests.ConnectionError("connection failed for token test-key")
    with pytest.raises(TransientApiError) as exc:
        ZtmClient(settings, session).fetch_vehicle_positions(1)
    assert "test-key" not in str(exc.value)
    assert exc.value.__cause__ is None
