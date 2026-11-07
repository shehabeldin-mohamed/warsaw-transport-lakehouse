import pytest

from ztm_ingest.config import Settings

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
