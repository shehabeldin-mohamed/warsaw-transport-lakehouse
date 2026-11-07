"""Runtime configuration, read from environment variables (12-factor style).

Nothing here is hard-coded per environment: dev/prod differ only by env vars.
"""

from __future__ import annotations

from typing import Literal

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="ZTM_", env_file=".env", extra="ignore")

    # --- API ---------------------------------------------------------------
    # The open data portal is migrating (api.um.warszawa.pl -> dane.um.warszawa.pl).
    # Keep URL and resource id configurable so a portal change is a config change,
    # not a code change.
    api_key: SecretStr
    api_base_url: str = "https://api.um.warszawa.pl/api/action/busestrams_get/"
    vehicle_resource_id: str = "f2e5503e-927d-4ad3-9500-4ab9e55deb59"
    request_timeout_s: float = 15.0
    max_retries: int = 4

    # --- Storage -----------------------------------------------------------
    storage_backend: Literal["local", "azure"] = "local"
    local_root: str = "data/bronze"
    # Azure (used when storage_backend == "azure"). Auth via DefaultAzureCredential,
    # so no storage keys live in config.
    azure_account_url: str = ""  # e.g. https://<account>.blob.core.windows.net
    azure_container: str = "bronze"

    environment: Literal["dev", "prod"] = "dev"
    log_level: str = "INFO"
