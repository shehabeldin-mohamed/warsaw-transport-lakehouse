from unittest.mock import MagicMock

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


def test_api_error_does_not_crash_the_collector(monkeypatch, tmp_path):
    run_once = MagicMock(side_effect=[ApiError("HTTP 401"), None])
    _patch(monkeypatch, tmp_path, run_once)

    assert cli.main(["--type", "1", "2"]) == 0

    assert run_once.call_count == 2  # type 2 was still attempted
