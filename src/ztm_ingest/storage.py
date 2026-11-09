"""Bronze storage writers.

Layout (Hive-style partitions, so Auto Loader / Spark can infer them):

    vehicle_positions/type=<1|2>/date=YYYY-MM-DD/hour=HH/<poll_ts_utc>.json

Files are immutable and written once. Bronze is append-only.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Protocol

from ztm_ingest.config import Settings


class BronzeWriter(Protocol):
    def write(self, relative_path: str, data: bytes) -> str: ...


def build_path(dataset: str, vehicle_type: int, at: datetime) -> str:
    """Partitioned relative path for one poll. `at` must be timezone-aware UTC."""
    if at.utcoffset() != timedelta(0):
        # A local or naive time would put the file in the wrong date/hour partition.
        raise ValueError("partition time must be timezone-aware UTC")
    ts = at.strftime("%Y%m%dT%H%M%SZ")
    return f"{dataset}/type={vehicle_type}/date={at:%Y-%m-%d}/hour={at:%H}/{ts}.json"


def build_envelope(
    records: list[dict[str, Any]],
    *,
    source: str,
    vehicle_type: int,
    requested_at: datetime,
    received_at: datetime,
    environment: str,
) -> bytes:
    """Raw payload plus ingestion metadata. The records themselves are not modified."""
    doc = {
        "_meta": {
            "source": source,
            "vehicle_type": vehicle_type,
            "requested_at_utc": requested_at.isoformat(),
            "received_at_utc": received_at.isoformat(),
            "record_count": len(records),
            "environment": environment,
        },
        "payload": records,
    }
    return json.dumps(doc, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


class LocalWriter:
    def __init__(self, root: str) -> None:
        self._root = Path(root)

    def write(self, relative_path: str, data: bytes) -> str:
        target = self._root / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_suffix(".tmp")
        tmp.write_bytes(data)
        tmp.replace(target)  # atomic: readers never see half-written files
        return str(target)


class AzureBlobWriter:
    def __init__(self, account_url: str, container: str) -> None:
        # Imported lazily so local development does not need the azure extras.
        from azure.identity import DefaultAzureCredential
        from azure.storage.blob import BlobServiceClient

        service = BlobServiceClient(account_url, credential=DefaultAzureCredential())
        self._container = service.get_container_client(container)

    def write(self, relative_path: str, data: bytes) -> str:
        self._container.upload_blob(name=relative_path, data=data, overwrite=False)
        return f"{self._container.url}/{relative_path}"


def make_writer(settings: Settings) -> BronzeWriter:
    if settings.storage_backend == "azure":
        if not settings.azure_account_url:
            raise ValueError("ZTM_AZURE_ACCOUNT_URL is required for the azure backend")
        return AzureBlobWriter(settings.azure_account_url, settings.azure_container)
    return LocalWriter(settings.local_root)
