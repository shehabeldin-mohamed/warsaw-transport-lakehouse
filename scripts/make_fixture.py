from __future__ import annotations

import argparse
import csv
import io
import json
import shutil
import zipfile
from collections.abc import Callable, Iterable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

DATASET = "vehicle_positions"
WARSAW = ZoneInfo("Europe/Warsaw")
GTFS_SMALL_FILES = ("agency.txt", "feed_info.txt", "attributions.txt")


def poll_time(path: Path) -> datetime:
    """The poll time is in the file name, e.g. 20261109T175530Z.json."""
    return datetime.strptime(path.stem, "%Y%m%dT%H%M%SZ").replace(tzinfo=UTC)


def cut(source: Path, dest: Path, start: datetime, end: datetime, lines: set[str]) -> int:
    """Copy polls in [start, end) to `dest`, keeping only records on `lines`."""
    written = 0
    for path in sorted((source / DATASET).rglob("*.json")):
        if not start <= poll_time(path) < end:
            continue
        doc = json.loads(path.read_text(encoding="utf-8"))
        doc["payload"] = [r for r in doc["payload"] if r.get("Lines") in lines]
        doc["_meta"]["record_count"] = len(doc["payload"])

        target = dest / path.relative_to(source)
        target.parent.mkdir(parents=True, exist_ok=True)
        # One record per line keeps git diffs readable if the fixture is ever regenerated.
        records = ",\n".join(json.dumps(r, ensure_ascii=False) for r in doc["payload"])
        meta = json.dumps(doc["_meta"], ensure_ascii=False)
        target.write_text(f'{{"_meta": {meta},\n"payload": [\n{records}\n]}}\n', encoding="utf-8")
        written += 1
    return written


def _read_csv(archive: zipfile.ZipFile, name: str) -> Iterable[dict[str, str]]:
    with archive.open(name) as f:
        yield from csv.DictReader(io.TextIOWrapper(f, encoding="utf-8-sig"))


def _write_csv(
    archive: zipfile.ZipFile,
    source: zipfile.ZipFile,
    name: str,
    keep: Callable[[dict[str, str]], bool],
) -> list[dict[str, str]]:
    rows = [r for r in _read_csv(source, name) if keep(r)]
    with source.open(name) as f:
        header = io.TextIOWrapper(f, encoding="utf-8-sig").readline().strip().split(",")
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=header, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    archive.writestr(name, buffer.getvalue())
    return rows


def _seconds(gtfs_time: str) -> int:
    h, m, s = (int(part) for part in gtfs_time.split(":"))
    return h * 3600 + m * 60 + s


def cut_gtfs(source: Path, dest: Path, start: datetime, end: datetime, lines: set[str]) -> Path:
    """Copy the newest GTFS zip downloaded by `start`, keeping only trips of `lines` that
    run within an hour of the window, plus the stops and calendar dates they need."""
    candidates = [p for p in sorted((source / "gtfs").rglob("*.zip")) if poll_time(p) <= start]
    if not candidates:
        raise SystemExit(f"no GTFS zip downloaded before {start:%Y-%m-%d %H:%M} UTC")
    zip_path = candidates[-1]

    local_start, local_end = start.astimezone(WARSAW), end.astimezone(WARSAW)
    days = {local_start.date() - timedelta(days=1), local_start.date()}
    windows = {}
    for day in days:
        midnight = datetime.combine(day, datetime.min.time(), WARSAW)
        windows[day.strftime("%Y%m%d")] = (
            (local_start - midnight).total_seconds() - 3600,
            (local_end - midnight).total_seconds() + 3600,
        )

    with zipfile.ZipFile(zip_path) as src:
        services: dict[str, set[str]] = {}
        for r in _read_csv(src, "calendar_dates.txt"):
            if r["date"] in windows and r["exception_type"] == "1":
                services.setdefault(r["service_id"], set()).add(r["date"])

        route_ids = {
            r["route_id"] for r in _read_csv(src, "routes.txt") if r["route_short_name"] in lines
        }
        trip_ids = {
            r["trip_id"]
            for r in _read_csv(src, "trips.txt")
            if r["route_id"] in route_ids and r["service_id"] in services
        }
        trip_service = {
            r["trip_id"]: r["service_id"]
            for r in _read_csv(src, "trips.txt")
            if r["trip_id"] in trip_ids
        }

        spans: dict[str, tuple[int, int]] = {}
        for r in _read_csv(src, "stop_times.txt"):
            if r["trip_id"] in trip_ids:
                t = _seconds(r["departure_time"])
                low, high = spans.get(r["trip_id"], (t, t))
                spans[r["trip_id"]] = (min(low, t), max(high, t))
        trip_ids = {
            trip
            for trip, (low, high) in spans.items()
            if any(
                low <= windows[day][1] and high >= windows[day][0]
                for day in services[trip_service[trip]]
            )
        }
        kept_services = {trip_service[t] for t in trip_ids}

        target = dest / zip_path.relative_to(source)
        target.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as out:
            for name in GTFS_SMALL_FILES:
                if name in src.namelist():
                    out.writestr(name, src.read(name))
            _write_csv(out, src, "routes.txt", lambda r: r["route_id"] in route_ids)
            _write_csv(out, src, "trips.txt", lambda r: r["trip_id"] in trip_ids)
            stop_times = _write_csv(out, src, "stop_times.txt", lambda r: r["trip_id"] in trip_ids)
            stop_ids = {r["stop_id"] for r in stop_times}
            _write_csv(out, src, "stops.txt", lambda r: r["stop_id"] in stop_ids)
            _write_csv(
                out,
                src,
                "calendar_dates.txt",
                lambda r: r["service_id"] in kept_services and r["date"] in windows,
            )
    print(f"kept {len(trip_ids)} trips, {len(stop_times)} stop times, {len(stop_ids)} stops")
    return target


def main() -> None:
    parser = argparse.ArgumentParser(description="Cut a small bronze slice for tests.")
    parser.add_argument("--source", type=Path, default=Path("data/bronze"))
    parser.add_argument("--dest", type=Path, default=Path("tests/fixtures/bronze"))
    parser.add_argument("--start", required=True, help="UTC, e.g. 2026-11-09T17:55:00")
    parser.add_argument("--end", required=True, help="UTC, exclusive")
    parser.add_argument("--lines", nargs="+", required=True, help="line numbers to keep")
    args = parser.parse_args()

    start = datetime.fromisoformat(args.start).replace(tzinfo=UTC)
    end = datetime.fromisoformat(args.end).replace(tzinfo=UTC)
    if args.dest.exists():
        shutil.rmtree(args.dest)  # regenerate from scratch, never mix two slices
    n = cut(args.source, args.dest, start, end, set(args.lines))
    print(f"wrote {n} files to {args.dest}")
    gtfs = cut_gtfs(args.source, args.dest, start, end, set(args.lines))
    print(f"wrote {gtfs}")


if __name__ == "__main__":
    main()
