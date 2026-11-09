import json
from datetime import UTC, datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest

from ztm_ingest.ingest import run_once
from ztm_ingest.storage import LocalWriter, build_envelope, build_path

NOW = datetime(2026, 11, 7, 15, 58, 30, tzinfo=UTC)


def fixed_clock(*times):
    """A clock that returns the given times in order, one per call."""
    return iter(times).__next__


def test_build_path_is_hive_partitioned():
    assert (
        build_path("vehicle_positions", 1, NOW)
        == "vehicle_positions/type=1/date=2026-11-07/hour=15/20261107T155830Z.json"
    )


@pytest.mark.parametrize(
    "not_utc",
    [
        datetime(2026, 11, 7, 16, 58, 30),  # naive: no timezone at all
        datetime(2026, 11, 7, 16, 58, 30, tzinfo=timezone(timedelta(hours=1))),  # Warsaw time
    ],
)
def test_build_path_rejects_times_that_are_not_utc(not_utc):
    with pytest.raises(ValueError, match="UTC"):
        build_path("vehicle_positions", 1, not_utc)


def test_envelope_keeps_payload_untouched(sample_records):
    doc = json.loads(
        build_envelope(
            sample_records,
            source="test-source",
            vehicle_type=1,
            requested_at=NOW,
            received_at=NOW + timedelta(seconds=2),
            environment="dev",
        )
    )
    assert doc["payload"] == sample_records
    assert doc["_meta"]["record_count"] == 2
    assert doc["_meta"]["requested_at_utc"] == "2026-11-07T15:58:30+00:00"
    assert doc["_meta"]["received_at_utc"] == "2026-11-07T15:58:32+00:00"
    assert doc["_meta"]["source"] == "test-source"


def test_local_writer_creates_partition_dirs(tmp_path):
    loc = LocalWriter(str(tmp_path)).write("a/b/c.json", b"{}")
    assert (tmp_path / "a" / "b" / "c.json").read_bytes() == b"{}"
    assert loc.endswith("c.json")
    assert not list(tmp_path.rglob("*.tmp"))


def test_run_once_writes_one_file(settings, sample_records, tmp_path):
    client = MagicMock()
    client.fetch_vehicle_positions.return_value = sample_records
    writer = LocalWriter(str(tmp_path))

    loc = run_once(settings, client, writer, 1, clock=fixed_clock(NOW, NOW))

    assert loc is not None
    doc = json.loads(open(loc, encoding="utf-8").read())
    assert doc["_meta"]["vehicle_type"] == 1
    assert len(doc["payload"]) == 2
    assert doc["_meta"]["source"] == settings.api_base_url


def test_run_once_partitions_by_response_time(settings, sample_records, tmp_path):
    # Retries made the request take 45 s and cross into the next hour.
    requested = datetime(2026, 11, 7, 15, 59, 50, tzinfo=UTC)
    received = datetime(2026, 11, 7, 16, 0, 35, tzinfo=UTC)
    client = MagicMock()
    client.fetch_vehicle_positions.return_value = sample_records

    loc = run_once(
        settings, client, LocalWriter(str(tmp_path)), 1, clock=fixed_clock(requested, received)
    )

    assert loc is not None
    assert "hour=16" in loc
    assert loc.endswith("20261107T160035Z.json")
    meta = json.loads(open(loc, encoding="utf-8").read())["_meta"]
    assert meta["requested_at_utc"] == "2026-11-07T15:59:50+00:00"
    assert meta["received_at_utc"] == "2026-11-07T16:00:35+00:00"


def test_run_once_default_clock_is_utc(settings, sample_records, tmp_path):
    # No fake clock: this is the code path the real collector uses.
    client = MagicMock()
    client.fetch_vehicle_positions.return_value = sample_records

    loc = run_once(settings, client, LocalWriter(str(tmp_path)), 1)

    assert loc is not None
    meta = json.loads(open(loc, encoding="utf-8").read())["_meta"]
    assert meta["requested_at_utc"].endswith("+00:00")
    assert meta["received_at_utc"] >= meta["requested_at_utc"]


def test_run_once_skips_empty_feed(settings, tmp_path):
    client = MagicMock()
    client.fetch_vehicle_positions.return_value = []
    writer = LocalWriter(str(tmp_path))
    assert run_once(settings, client, writer, 1, clock=fixed_clock(NOW, NOW)) is None
    assert not list(tmp_path.rglob("*.json"))


def test_run_once_still_writes_when_some_records_are_malformed(settings, sample_records, tmp_path):
    # Bronze keeps raw data; validation is only a metric here.
    sample_records.append({"unexpected": "shape"})
    client = MagicMock()
    client.fetch_vehicle_positions.return_value = sample_records
    writer = LocalWriter(str(tmp_path))
    assert run_once(settings, client, writer, 1, clock=fixed_clock(NOW, NOW)) is not None
