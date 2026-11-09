import logging
import signal
from unittest.mock import MagicMock

import pytest

from ztm_ingest import cli
from ztm_ingest.client import ApiError


def _patch(monkeypatch, tmp_path, run_once):
    monkeypatch.setenv("ZTM_API_KEY", "test-key")
    monkeypatch.setenv("ZTM_LOCAL_ROOT", str(tmp_path))
    monkeypatch.setattr(cli, "run_once", run_once)
    monkeypatch.setattr(cli, "ZtmClient", MagicMock())


def test_single_run_polls_each_requested_type(monkeypatch, tmp_path):
    run_once = MagicMock()
    _patch(monkeypatch, tmp_path, run_once)

    assert cli.main(["--type", "1", "2"]) == 0

    assert [c.args[3] for c in run_once.call_args_list] == [1, 2]


def test_api_error_does_not_crash_the_collector(monkeypatch, tmp_path, caplog):
    run_once = MagicMock(side_effect=[ApiError("HTTP 401"), None])
    _patch(monkeypatch, tmp_path, run_once)

    assert cli.main(["--type", "1", "2"]) == 1  # a failed single run exits non-zero

    assert run_once.call_count == 2  # type 2 was still attempted
    [record] = [r for r in caplog.records if r.levelno == logging.ERROR]
    assert record.getMessage() == "poll failed"
    assert record.error == "HTTP 401"
    assert record.vehicle_type == 1
    assert record.exc_info is None  # expected failure: no traceback noise


def test_unexpected_error_is_logged_with_traceback_and_collector_continues(
    monkeypatch, tmp_path, caplog
):
    # e.g. the disk is full or blob storage is down: not an ApiError.
    run_once = MagicMock(side_effect=[OSError("disk full"), None])
    _patch(monkeypatch, tmp_path, run_once)

    assert cli.main(["--type", "1", "2"]) == 1

    assert run_once.call_count == 2
    [record] = [r for r in caplog.records if r.levelno == logging.ERROR]
    assert record.getMessage() == "poll failed unexpectedly"
    assert record.exc_info is not None
    assert "disk full" in str(record.exc_info[1])


def test_interval_mode_keeps_polling_until_stopped(monkeypatch, tmp_path):
    run_once = MagicMock(side_effect=[OSError("disk full"), None, None, None])
    _patch(monkeypatch, tmp_path, run_once)
    sleeps = []

    def fake_sleep(seconds):
        # Instead of waiting, record the wait. On the second wait, simulate Ctrl+C.
        sleeps.append(seconds)
        if len(sleeps) == 2:
            signal.raise_signal(signal.SIGINT)

    monkeypatch.setattr(cli.time, "sleep", fake_sleep)

    assert cli.main(["--type", "1", "2", "--interval", "30"]) == 0

    assert run_once.call_count == 4  # two rounds of two types, despite the first failure
    assert len(sleeps) == 2
    assert all(0 < s <= 30 for s in sleeps)


def test_signal_handlers_are_restored_after_main(monkeypatch, tmp_path):
    _patch(monkeypatch, tmp_path, MagicMock())
    before = signal.getsignal(signal.SIGINT)

    cli.main(["--type", "1"])

    assert signal.getsignal(signal.SIGINT) is before


def test_rejects_unknown_vehicle_type(monkeypatch, tmp_path):
    run_once = MagicMock()
    _patch(monkeypatch, tmp_path, run_once)

    with pytest.raises(SystemExit) as exc:
        cli.main(["--type", "3"])

    assert exc.value.code == 2
    run_once.assert_not_called()
