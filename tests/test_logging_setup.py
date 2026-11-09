import io
import json
import logging
from pathlib import Path

import pytest

from ztm_ingest.logging_setup import JsonFormatter, configure_logging


@pytest.fixture
def capture():
    """A logger that writes JSON lines into a string we can read back."""
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JsonFormatter())
    logger = logging.getLogger("test_logging_setup")
    logger.handlers[:] = [handler]
    logger.propagate = False
    logger.setLevel(logging.DEBUG)
    yield logger, stream
    logger.handlers.clear()


def _lines(stream):
    return [json.loads(line) for line in stream.getvalue().splitlines()]


def test_extra_fields_become_top_level_keys(capture):
    logger, stream = capture
    logger.info("poll written", extra={"vehicle_type": 1, "records": 2})

    [doc] = _lines(stream)
    assert doc["message"] == "poll written"
    assert doc["level"] == "INFO"
    assert doc["logger"] == "test_logging_setup"
    assert doc["vehicle_type"] == 1
    assert doc["records"] == 2
    assert doc["ts"].endswith("+00:00")  # always UTC


def test_message_arguments_are_filled_in(capture):
    logger, stream = capture
    logger.error("poll failed: %s", "HTTP 503")

    [doc] = _lines(stream)
    assert doc["message"] == "poll failed: HTTP 503"
    assert "args" not in doc  # standard record attributes are not repeated


def test_exception_traceback_is_included(capture):
    logger, stream = capture
    try:
        raise ValueError("boom")
    except ValueError:
        logger.exception("poll failed")

    [doc] = _lines(stream)
    assert "ValueError: boom" in doc["exc_info"]


def test_values_json_cannot_encode_are_written_as_text(capture):
    logger, stream = capture
    logger.info("written", extra={"location": Path("data/bronze/x.json")})

    [doc] = _lines(stream)
    assert doc["location"].endswith("x.json")


def test_configure_logging_twice_adds_only_one_handler():
    root = logging.getLogger()
    before = list(root.handlers)
    try:
        configure_logging("INFO")
        configure_logging("INFO")
        ours = [h for h in root.handlers if h not in before]
        assert len(ours) == 1
        assert isinstance(ours[0].formatter, JsonFormatter)
    finally:
        root.handlers[:] = before
