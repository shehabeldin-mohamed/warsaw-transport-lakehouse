import hashlib
import io
import json
import zipfile
from datetime import UTC, datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest
import requests
import tenacity

from ztm_ingest import cli
from ztm_ingest.gtfs import (
    REQUIRED_FILES,
    GtfsError,
    build_gtfs_paths,
    check_gtfs_zip,
    run_gtfs,
)
from ztm_ingest.storage import LocalWriter

NOW = datetime(2026, 11, 11, 3, 0, 5, tzinfo=UTC)


def _zip(names=REQUIRED_FILES):
    """A small in-memory zip containing the given (empty-ish) files."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name in names:
            archive.writestr(name, "header\n")
    return buffer.getvalue()


def _response(status=200, content=b"", headers=None):
    resp = MagicMock()
    resp.status_code = status
    resp.content = content
    resp.headers = headers or {}
    return resp


def _session(*responses):
    session = MagicMock()
    session.get.side_effect = list(responses)
    return session


def fixed_clock(*times):
    return iter(times).__next__


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    monkeypatch.setattr(tenacity.nap.time, "sleep", lambda _s: None)


def test_paths_are_partitioned_by_date():
    assert build_gtfs_paths(NOW) == (
        "gtfs/date=2026-11-11/20261111T030005Z.zip",
        "gtfs/date=2026-11-11/20261111T030005Z.meta.json",
    )


def test_paths_reject_times_that_are_not_utc():
    with pytest.raises(ValueError, match="UTC"):
        build_gtfs_paths(datetime(2026, 11, 11, 4, 0, 5, tzinfo=timezone(timedelta(hours=1))))


def test_valid_feed_returns_its_file_names():
    names = check_gtfs_zip(_zip(REQUIRED_FILES | {"calendar.txt"}))
    assert names == sorted(REQUIRED_FILES | {"calendar.txt"})


def test_html_error_page_is_rejected():
    with pytest.raises(GtfsError, match="not a zip"):
        check_gtfs_zip(b"<html>Service unavailable</html>")


def test_damaged_zip_is_rejected():
    # Files are stored uncompressed, so their bytes appear as-is in the zip. Changing
    # one makes its checksum (CRC) wrong, like a download damaged in transit.
    damaged = _zip().replace(b"header\n", b"HEADER\n", 1)
    with pytest.raises(GtfsError, match="corrupt file"):
        check_gtfs_zip(damaged)


def test_zip_without_timetable_files_is_rejected():
    with pytest.raises(GtfsError, match=r"missing: \['stop_times.txt'\]"):
        check_gtfs_zip(_zip(REQUIRED_FILES - {"stop_times.txt"}))


def test_run_writes_the_zip_unchanged_and_its_metadata(settings, tmp_path):
    data = _zip()
    session = _session(_response(content=data, headers={"ETag": '"abc"'}))

    loc = run_gtfs(
        settings,
        LocalWriter(str(tmp_path)),
        session=session,
        clock=fixed_clock(NOW - timedelta(seconds=4), NOW),
    )

    zip_file = tmp_path / "gtfs" / "date=2026-11-11" / "20261111T030005Z.zip"
    assert loc == str(zip_file)
    assert zip_file.read_bytes() == data  # bronze keeps the raw bytes
    meta = json.loads(zip_file.with_name("20261111T030005Z.meta.json").read_text("utf-8"))
    assert meta["source"] == settings.gtfs_url
    assert meta["sha256"] == hashlib.sha256(data).hexdigest()
    assert meta["size_bytes"] == len(data)
    assert meta["etag"] == '"abc"'
    assert meta["files"] == sorted(REQUIRED_FILES)
    assert meta["requested_at_utc"] == "2026-11-11T03:00:01+00:00"


def test_server_errors_are_retried(settings, tmp_path):
    session = _session(_response(503), _response(content=_zip()))
    run_gtfs(settings, LocalWriter(str(tmp_path)), session=session)
    assert session.get.call_count == 2


def test_network_errors_are_retried_then_raise(settings, tmp_path):
    session = MagicMock()
    session.get.side_effect = requests.ConnectionError("dns failure")
    with pytest.raises(GtfsError, match="network error: ConnectionError"):
        run_gtfs(settings, LocalWriter(str(tmp_path)), session=session)
    assert session.get.call_count == settings.max_retries


def test_not_found_is_not_retried_and_nothing_is_written(settings, tmp_path):
    session = _session(_response(404))
    with pytest.raises(GtfsError, match="HTTP 404"):
        run_gtfs(settings, LocalWriter(str(tmp_path)), session=session)
    assert session.get.call_count == 1
    assert not list(tmp_path.rglob("*.*"))


def test_cli_gtfs_command(monkeypatch, tmp_path):
    monkeypatch.setenv("ZTM_API_KEY", "test-key")
    monkeypatch.setenv("ZTM_LOCAL_ROOT", str(tmp_path))
    run = MagicMock()
    monkeypatch.setattr(cli, "run_gtfs", run)

    assert cli.main(["gtfs"]) == 0
    run.assert_called_once()


def test_cli_gtfs_failure_exits_non_zero(monkeypatch, tmp_path, caplog):
    monkeypatch.setenv("ZTM_API_KEY", "test-key")
    monkeypatch.setenv("ZTM_LOCAL_ROOT", str(tmp_path))
    monkeypatch.setattr(cli, "run_gtfs", MagicMock(side_effect=GtfsError("HTTP 404")))

    assert cli.main(["gtfs"]) == 1
    assert "gtfs download failed" in caplog.text


def test_cli_gtfs_unexpected_error_exits_non_zero(monkeypatch, tmp_path, caplog):
    monkeypatch.setenv("ZTM_API_KEY", "test-key")
    monkeypatch.setenv("ZTM_LOCAL_ROOT", str(tmp_path))
    monkeypatch.setattr(cli, "run_gtfs", MagicMock(side_effect=OSError("disk full")))

    assert cli.main(["gtfs"]) == 1
    [record] = [r for r in caplog.records if r.levelname == "ERROR"]
    assert record.getMessage() == "gtfs download failed unexpectedly"
    assert record.exc_info is not None
