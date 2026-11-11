from __future__ import annotations

import argparse
import json
import shutil
from datetime import UTC, datetime
from pathlib import Path

DATASET = "vehicle_positions"


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


if __name__ == "__main__":
    main()
