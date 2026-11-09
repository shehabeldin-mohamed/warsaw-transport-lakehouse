"""Runtime configuration, read from environment variables (12-factor style).

Nothing here is hard-coded per environment: dev/prod differ only by env vars.
"""

from __future__ import annotations

from typing import Literal, Self

from pydantic import SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="ZTM_", env_file=".env", extra="ignore")

    # --- API ---------------------------------------------------------------
    # The portal moved from api.um.warszawa.pl to dane.um.warszawa.pl. The URL stays
    # configurable so a future portal change is a config change, not a code change.
    api_key: SecretStr
    api_base_url: str = "https://dane.um.warszawa.pl/api/action/get_ztm_lokalizacja_pojazdow"
    # Some portals sit behind a firewall that rejects Python's default User-Agent with a 403.
    # Override with ZTM_USER_AGENT if this one is ever blocked too.
    user_agent: str = "ztm-ingest/0.1"
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

    @model_validator(mode="after")
    def _check_azure_settings(self) -> Self:
        # Fail at startup with a clear message, not later on the first write.
        if self.storage_backend == "azure":
            if not self.azure_account_url:
                raise ValueError("ZTM_AZURE_ACCOUNT_URL is required when ZTM_STORAGE_BACKEND=azure")
            if not self.azure_account_url.startswith("https://"):
                raise ValueError("ZTM_AZURE_ACCOUNT_URL must start with https://")
        return self
