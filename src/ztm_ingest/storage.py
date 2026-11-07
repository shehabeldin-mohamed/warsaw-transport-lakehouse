"""Bronze storage writers.

Layout (Hive-style partitions, so Auto Loader / Spark can infer them):

    vehicle_positions/type=<1|2>/date=YYYY-MM-DD/hour=HH/<poll_ts_utc>.json

Files are immutable and written once. Bronze is append-only.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Protocol

from ztm_ingest.config import Settings


class BronzeWriter(Protocol):
    def write(self, relative_path: str, data: bytes) -> str: ...


def build_path(dataset: str, vehicle_type: int, polled_at: datetime) -> str:
    """Partitioned relative path for one poll. `polled_at` must be timezone-aware UTC."""
    ts = polled_at.strftime("%Y%m%dT%H%M%SZ")
    return f"{dataset}/type={vehicle_type}/date={polled_at:%Y-%m-%d}/hour={polled_at:%H}/{ts}.json"


def build_envelope(
    records: list[dict[str, Any]], *, vehicle_type: int, polled_at: datetime, environment: str
) -> bytes:
    """Raw payload plus ingestion metadata. The records themselves are not modified."""
    doc = {
        "_meta": {
            "source": "um.warszawa.pl/busestrams_get",
            "vehicle_type": vehicle_type,
            "polled_at_utc": polled_at.isoformat(),
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
