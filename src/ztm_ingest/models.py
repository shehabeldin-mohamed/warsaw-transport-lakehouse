"""Typed view of one vehicle position as returned by the API.

Used for *validation/metrics at ingestion time only*. Bronze keeps the raw payload
untouched; cleaning and typing for analytics happens in the silver layer.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class VehiclePosition(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="allow")

    brigade: str = Field(alias="Brigade")
    lines: str = Field(alias="Lines")
    lat: float = Field(alias="Lat")
    lon: float = Field(alias="Lon")
    time: str = Field(alias="Time")  # local Warsaw time, no timezone
    vehicle_number: str = Field(alias="VehicleNumber")
