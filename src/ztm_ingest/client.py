"""HTTP client for the Warsaw open data vehicle-location endpoint (dane.um.warszawa.pl)."""

from __future__ import annotations

import logging
from typing import Any

import requests
from tenacity import (
    before_sleep_log,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential_jitter,
)

from ztm_ingest.config import Settings

log = logging.getLogger(__name__)

VEHICLE_TYPES = {1: "bus", 2: "tram"}


class ApiError(RuntimeError):
    """The API answered, but not with usable data."""


class TransientApiError(ApiError):
    """Worth retrying (network problems, 5xx, 429)."""


class ZtmClient:
    def __init__(self, settings: Settings, session: requests.Session | None = None) -> None:
        self._s = settings
        self._session = session or requests.Session()

    def fetch_vehicle_positions(self, vehicle_type: int) -> list[dict[str, Any]]:
        if vehicle_type not in VEHICLE_TYPES:
            raise ValueError(f"vehicle_type must be one of {sorted(VEHICLE_TYPES)}")

        @retry(
            retry=retry_if_exception_type(TransientApiError),
            stop=stop_after_attempt(self._s.max_retries),
            wait=wait_exponential_jitter(initial=1, max=30),
            before_sleep=before_sleep_log(log, logging.WARNING),
            reraise=True,
        )
        def _call() -> list[dict[str, Any]]:
            return self._fetch_once(vehicle_type)

        return _call()

    def _fetch_once(self, vehicle_type: int) -> list[dict[str, Any]]:
        # The key travels in a header.
        headers = {
            "Authorization": self._s.api_key.get_secret_value(),
            "User-Agent": self._s.user_agent,
        }
        try:
            resp = self._session.post(
                self._s.api_base_url,
                json={"type": vehicle_type},
                headers=headers,
                timeout=self._s.request_timeout_s,
            )
        except requests.RequestException as exc:
            # Keep exception text out of logs: it can echo request details.
            raise TransientApiError(f"network error: {type(exc).__name__}") from None

        if resp.status_code == 429 or resp.status_code >= 500:
            raise TransientApiError(f"HTTP {resp.status_code}")
        if resp.status_code != 200:
            raise ApiError(f"HTTP {resp.status_code}")

        try:
            body = resp.json()
        except ValueError:
            raise TransientApiError("response was not valid JSON") from None
        return self._extract_records(body)

    def _extract_records(self, body: Any) -> list[dict[str, Any]]:
        records = body.get("result") if isinstance(body, dict) else body
        if isinstance(records, str):
            message = records.replace(self._s.api_key.get_secret_value(), "***")[:200]
            raise ApiError(f"API returned an error message: {message!r}")
        if not isinstance(records, list):
            # Show the *shape* only (top-level keys), never values.
            shape = f"keys={sorted(body)}" if isinstance(body, dict) else type(body).__name__
            raise ApiError(f"unexpected response shape: {shape}")
        return records
