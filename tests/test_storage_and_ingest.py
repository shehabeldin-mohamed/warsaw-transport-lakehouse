import json
from datetime import UTC, datetime
from unittest.mock import MagicMock

from ztm_ingest.ingest import run_once
from ztm_ingest.storage import LocalWriter, build_envelope, build_path

NOW = datetime(2026, 11, 7, 15, 58, 30, tzinfo=UTC)


def test_build_path_is_hive_partitioned():
    assert (
        build_path("vehicle_positions", 1, NOW)
        == "vehicle_positions/type=1/date=2026-11-07/hour=15/20261107T155830Z.json"
    )


def test_envelope_keeps_payload_untouched(sample_records):
    doc = json.loads(
        build_envelope(sample_records, vehicle_type=1, polled_at=NOW, environment="dev")
    )
    assert doc["payload"] == sample_records
    assert doc["_meta"]["record_count"] == 2
    assert doc["_meta"]["polled_at_utc"].startswith("2026-11-07T15:58:30")


def test_local_writer_creates_partition_dirs(tmp_path):
    loc = LocalWriter(str(tmp_path)).write("a/b/c.json", b"{}")
    assert (tmp_path / "a" / "b" / "c.json").read_bytes() == b"{}"
    assert loc.endswith("c.json")
    assert not list(tmp_path.rglob("*.tmp"))


def test_run_once_writes_one_file(settings, sample_records, tmp_path):
    client = MagicMock()
    client.fetch_vehicle_positions.return_value = sample_records
    writer = LocalWriter(str(tmp_path))

    loc = run_once(settings, client, writer, 1, now=NOW)

    assert loc is not None
    doc = json.loads(open(loc, encoding="utf-8").read())
    assert doc["_meta"]["vehicle_type"] == 1
    assert len(doc["payload"]) == 2


def test_run_once_skips_empty_feed(settings, tmp_path):
    client = MagicMock()
    client.fetch_vehicle_positions.return_value = []
    assert run_once(settings, client, LocalWriter(str(tmp_path)), 1, now=NOW) is None
    assert not list(tmp_path.rglob("*.json"))


def test_run_once_still_writes_when_some_records_are_malformed(settings, sample_records, tmp_path):
    # Bronze keeps raw data; validation is only a metric here.
    sample_records.append({"unexpected": "shape"})
    client = MagicMock()
    client.fetch_vehicle_positions.return_value = sample_records
    assert run_once(settings, client, LocalWriter(str(tmp_path)), 1, now=NOW) is not None
