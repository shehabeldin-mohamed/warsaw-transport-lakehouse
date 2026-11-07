"""One ingestion run: fetch -> sanity-check -> write raw file to bronze."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from pydantic import ValidationError

from ztm_ingest.client import ZtmClient
from ztm_ingest.config import Settings
from ztm_ingest.models import VehiclePosition
from ztm_ingest.storage import BronzeWriter, build_envelope, build_path

log = logging.getLogger(__name__)

DATASET = "vehicle_positions"


def run_once(
    settings: Settings,
    client: ZtmClient,
    writer: BronzeWriter,
    vehicle_type: int,
    now: datetime | None = None,
) -> str | None:
    """Poll once. Returns the written location, or None if the feed was empty."""
    polled_at = now or datetime.now(UTC)
    records = client.fetch_vehicle_positions(vehicle_type)

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
        vehicle_type=vehicle_type,
        polled_at=polled_at,
        environment=settings.environment,
    )
    location = writer.write(build_path(DATASET, vehicle_type, polled_at), data)
    log.info(
        "poll written",
        extra={"vehicle_type": vehicle_type, "records": len(records), "location": location},
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
