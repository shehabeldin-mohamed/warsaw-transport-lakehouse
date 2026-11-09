"""One ingestion run: fetch -> sanity-check -> write raw file to bronze."""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from pydantic import ValidationError

from ztm_ingest.client import ZtmClient
from ztm_ingest.config import Settings
from ztm_ingest.models import VehiclePosition
from ztm_ingest.storage import BronzeWriter, build_envelope, build_path

log = logging.getLogger(__name__)

DATASET = "vehicle_positions"


def _utc_now() -> datetime:
    return datetime.now(UTC)


def run_once(
    settings: Settings,
    client: ZtmClient,
    writer: BronzeWriter,
    vehicle_type: int,
    clock: Callable[[], datetime] = _utc_now,
) -> str | None:
    """Poll once. Returns the written location, or None if the feed was empty.

    `clock` is read twice: before the request and after the response. With retries the
    two can be many seconds apart, and the response time is closer to when the API
    produced the data, so it decides the partition.
    """
    requested_at = clock()
    records = client.fetch_vehicle_positions(vehicle_type)
    received_at = clock()

    if not records:
        # Don't write empty files, but make it loud: an empty feed during the day is an incident.
        log.warning("empty feed", extra={"vehicle_type": vehicle_type})
        return None

    invalid = _count_invalid(records)
    if invalid:
        log.warning(
            "records failed schema validation",
            extra={"vehicle_type": vehicle_type, "invalid": invalid, "total": len(records)},
        )

    data = build_envelope(
        records,
        source=settings.api_base_url,
        vehicle_type=vehicle_type,
        requested_at=requested_at,
        received_at=received_at,
        environment=settings.environment,
    )
    location = writer.write(build_path(DATASET, vehicle_type, received_at), data)
    log.info(
        "poll written",
        extra={
            "vehicle_type": vehicle_type,
            "records": len(records),
            "location": location,
            "fetch_seconds": round((received_at - requested_at).total_seconds(), 3),
        },
    )
    return location


def _count_invalid(records: list[dict[str, Any]]) -> int:
    bad = 0
    for rec in records:
        try:
            VehiclePosition.model_validate(rec)
        except ValidationError:
            bad += 1
    return bad
