"""Daily GTFS schedule download into bronze.

The timetable is needed for punctuality: a bus can only be late compared to a
schedule. Warsaw's GTFS feed is built from ZTM's official timetable data by
Mikołaj Kuranowski (https://mkuran.pl/gtfs/) and refreshed daily.

Layout, one pair of files per download:

    gtfs/date=YYYY-MM-DD/<ts>.zip        the file exactly as downloaded
    gtfs/date=YYYY-MM-DD/<ts>.meta.json  source, timing, size, sha256, contents

The zip stays a zip in bronze (raw and immutable, like vehicle positions);
unpacking it into tables is the silver layer's job.
"""

from __future__ import annotations

import hashlib
import io
import json
import logging
import zipfile
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import requests
from tenacity import (
    before_sleep_log,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential_jitter,
)

from ztm_ingest.config import Settings
from ztm_ingest.storage import BronzeWriter

log = logging.getLogger(__name__)

DATASET = "gtfs"
# The files every GTFS feed must have to be usable for punctuality.
REQUIRED_FILES = frozenset({"agency.txt", "stops.txt", "routes.txt", "trips.txt", "stop_times.txt"})


class GtfsError(RuntimeError):
    """The download failed or isn't a usable GTFS feed."""


class TransientGtfsError(GtfsError):
    """Worth retrying (network problems, 5xx, 429)."""


def _utc_now() -> datetime:
    return datetime.now(UTC)


def build_gtfs_paths(at: datetime) -> tuple[str, str]:
    """Relative paths of the zip and its metadata. `at` must be timezone-aware UTC."""
    if at.utcoffset() != timedelta(0):
        raise ValueError("partition time must be timezone-aware UTC")
    base = f"{DATASET}/date={at:%Y-%m-%d}/{at:%Y%m%dT%H%M%SZ}"
    return f"{base}.zip", f"{base}.meta.json"


def check_gtfs_zip(data: bytes) -> list[str]:
    """Check that `data` is an intact GTFS zip. Returns the file names inside it.

    A server can answer 200 with an HTML error page, or a download can be cut short.
    Neither is raw data worth keeping, so they are rejected before anything is written.
    """
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile:
        raise GtfsError("download is not a zip file") from None
    with archive:
        names = sorted(archive.namelist())
        broken = archive.testzip()  # reads every member and checks its CRC
    if broken is not None:
        raise GtfsError(f"corrupt file inside the zip: {broken}")
    missing = REQUIRED_FILES - set(names)
    if missing:
        raise GtfsError(f"not a GTFS feed, missing: {sorted(missing)}")
    return names


def download_gtfs(settings: Settings, session: requests.Session) -> requests.Response:
    @retry(
        retry=retry_if_exception_type(TransientGtfsError),
        stop=stop_after_attempt(settings.max_retries),
        wait=wait_exponential_jitter(initial=1, max=30),
        before_sleep=before_sleep_log(log, logging.WARNING),
        reraise=True,
    )
    def _get() -> requests.Response:
        try:
            resp = session.get(
                settings.gtfs_url,
                headers={"User-Agent": settings.user_agent},
                timeout=settings.gtfs_timeout_s,
            )
        except requests.RequestException as exc:
            raise TransientGtfsError(f"network error: {type(exc).__name__}") from None
        if resp.status_code == 429 or resp.status_code >= 500:
            raise TransientGtfsError(f"HTTP {resp.status_code}")
        if resp.status_code != 200:
            raise GtfsError(f"HTTP {resp.status_code}")
        return resp

    return _get()


def run_gtfs(
    settings: Settings,
    writer: BronzeWriter,
    session: requests.Session | None = None,
    clock: Callable[[], datetime] = _utc_now,
) -> str:
    """Download the feed, check it, and write the zip plus its metadata to bronze."""
    requested_at = clock()
    resp = download_gtfs(settings, session or requests.Session())
    received_at = clock()

    data = resp.content
    files = check_gtfs_zip(data)
    zip_path, meta_path = build_gtfs_paths(received_at)
    meta = {
        "source": settings.gtfs_url,
        "requested_at_utc": requested_at.isoformat(),
        "received_at_utc": received_at.isoformat(),
        "size_bytes": len(data),
        # The hash shows whether two downloads are the same feed, without opening them.
        "sha256": hashlib.sha256(data).hexdigest(),
        # What the server says about its version of the file, useful when debugging.
        "etag": resp.headers.get("ETag"),
        "last_modified": resp.headers.get("Last-Modified"),
        "files": files,
        "environment": settings.environment,
    }

    location = writer.write(zip_path, data)
    # The metadata is written last: if it exists, the zip next to it is complete.
    writer.write(meta_path, json.dumps(meta, indent=2).encode("utf-8"))
    log.info(
        "gtfs written",
        extra={
            "location": location,
            "size_bytes": len(data),
            "fetch_seconds": round((received_at - requested_at).total_seconds(), 3),
        },
    )
    return location
