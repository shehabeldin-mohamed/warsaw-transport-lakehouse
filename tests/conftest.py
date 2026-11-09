import os

import pytest

from ztm_ingest.config import Settings


@pytest.fixture(autouse=True)
def _isolate_environment(monkeypatch, tmp_path):
    """Make every test independent of the machine it runs on.

    Settings reads ZTM_* environment variables and a `.env` file in the current
    directory. A developer's real values (their API key, `ZTM_STORAGE_BACKEND=azure`)
    must never change test results, so remove the variables and run each test from
    an empty temporary directory where no `.env` exists.
    """
    for name in list(os.environ):
        if name.upper().startswith("ZTM_"):
            monkeypatch.delenv(name)
    monkeypatch.chdir(tmp_path)


SAMPLE_RECORDS = [
    {
        "Brigade": "5",
        "Lines": "119",
        "Lat": 52.206184,
        "Lon": 21.000183,
        "Time": "2026-11-07 16:58:27",
        "VehicleNumber": "1000",
    },
    {
        "Brigade": "5",
        "Lines": "119",
        "Lat": 52.2060926,
        "Lon": 21.0004211,
        "Time": "2026-11-07 16:58:42",
        "VehicleNumber": "1001",
    },
]


@pytest.fixture
def sample_records() -> list[dict]:
    return [dict(r) for r in SAMPLE_RECORDS]


@pytest.fixture
def settings(tmp_path) -> Settings:
    return Settings(api_key="test-key", local_root=str(tmp_path), max_retries=3)  # type: ignore[arg-type]
