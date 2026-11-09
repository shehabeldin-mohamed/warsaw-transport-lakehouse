import pytest
from pydantic import ValidationError

from ztm_ingest.config import Settings


def test_local_backend_needs_no_azure_settings():
    settings = Settings(api_key="k")  # type: ignore[arg-type]
    assert settings.storage_backend == "local"


def test_azure_backend_requires_account_url():
    with pytest.raises(ValidationError, match="ZTM_AZURE_ACCOUNT_URL is required"):
        Settings(api_key="k", storage_backend="azure")  # type: ignore[arg-type]


def test_azure_account_url_must_be_https():
    with pytest.raises(ValidationError, match="must start with https://"):
        Settings(
            api_key="k",  # type: ignore[arg-type]
            storage_backend="azure",
            azure_account_url="http://acct.blob.core.windows.net",
        )


def test_settings_are_read_from_environment_variables(monkeypatch):
    monkeypatch.setenv("ZTM_API_KEY", "from-env")
    monkeypatch.setenv("ZTM_STORAGE_BACKEND", "azure")
    monkeypatch.setenv("ZTM_AZURE_ACCOUNT_URL", "https://acct.blob.core.windows.net")

    settings = Settings()  # type: ignore[call-arg]

    assert settings.api_key.get_secret_value() == "from-env"
    assert settings.azure_account_url == "https://acct.blob.core.windows.net"


def test_api_key_is_hidden_when_settings_are_printed():
    settings = Settings(api_key="super-secret")  # type: ignore[arg-type]
    assert "super-secret" not in repr(settings)
    assert "super-secret" not in str(settings)
