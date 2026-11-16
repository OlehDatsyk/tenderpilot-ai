"""Production configuration guards."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.core.config import Settings

GOOD = {
    "environment": "production",
    "secret_key": "x" * 48,
    "database_url": "postgres://u:p@db.internal:5432/tp",
    "cors_origins": "https://app.example.com",
    "_env_file": None,
}


def test_production_accepts_safe_settings_and_normalises_db_url():
    s = Settings(**GOOD)
    assert s.database_url.startswith("postgresql+psycopg://")
    assert s.cors_origin_list == ["https://app.example.com"]


@pytest.mark.parametrize(
    "override",
    [
        {"secret_key": "too-short"},
        {"database_url": "sqlite:///prod.db"},
        {"cors_origins": "*"},
        {"storage_backend": "local"},
    ],
)
def test_production_rejects_unsafe_settings(override):
    with pytest.raises(ValidationError):
        Settings(**{**GOOD, **override})


def test_development_generates_ephemeral_secret():
    s = Settings(environment="development", secret_key="", _env_file=None)
    assert len(s.secret_key) >= 32


def test_production_sqlite_only_with_explicit_ephemeral_demo():
    s = Settings(**{**GOOD, "database_url": "sqlite:///./demo.db", "ephemeral_demo": True})
    assert s.database_url.startswith("sqlite") and s.ephemeral_demo


def test_health_reports_ephemeral_flag(client):
    assert client.get("/health").json()["ephemeral_data"] is False
