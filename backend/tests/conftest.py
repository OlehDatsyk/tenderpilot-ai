"""Test fixtures: isolated SQLite database migrated with Alembic, mocked AI providers, helpers."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

from cryptography.fernet import Fernet

_TMP = Path(tempfile.mkdtemp(prefix="tenderpilot-tests-"))
os.environ.update(
    {
        "ENVIRONMENT": "test",
        "TENDERPILOT_IGNORE_ENV_FILE": "1",
        # Set TEST_DATABASE_URL to run the suite against PostgreSQL (CI does). The database is wiped between tests.
        "DATABASE_URL": os.environ.get("TEST_DATABASE_URL") or f"sqlite:///{(_TMP / 'test.db').as_posix()}",
        "SECRET_KEY": "test-secret-key-that-is-long-enough-1234567890",
        "ENCRYPTION_KEY": Fernet.generate_key().decode(),  # random per test session
        "AI_PROVIDER": "none",
        "STORAGE_BACKEND": "database",
        "MAX_UPLOAD_MB": "2",
        "RATE_LIMIT_AUTH_PER_MINUTE": "1000",
        "RATE_LIMIT_AI_PER_MINUTE": "1000",
        "CORS_ORIGINS": "http://localhost:5173",
    }
)

import json  # noqa: E402
import uuid  # noqa: E402

import pytest  # noqa: E402
from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine, event  # noqa: E402

from app.ai.base import RawCompletion  # noqa: E402
from app.ai.providers import register_adapter  # noqa: E402
from app.core.ratelimit import limiter  # noqa: E402
from app.db.base import Base  # noqa: E402
from app.db.session import configure_engine  # noqa: E402

BACKEND_DIR = Path(__file__).resolve().parents[1]
PASSWORD = "Sup3r-secret-pass"


def _engine():
    from app.core.config import Settings

    url = Settings(_env_file=None).database_url
    if not url.startswith("sqlite"):
        return create_engine(url)
    engine = create_engine(url, connect_args={"check_same_thread": False})

    @event.listens_for(engine, "connect")
    def _fk(dbapi_conn, _):
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA foreign_keys=ON")
        cur.close()

    return engine


@pytest.fixture(scope="session")
def engine():
    eng = _engine()
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    with eng.begin() as conn:
        cfg.attributes["connection"] = conn
        if eng.dialect.name != "sqlite":  # start from a clean schema on a reused PostgreSQL test DB
            command.downgrade(cfg, "base")
        command.upgrade(cfg, "head")
    configure_engine(eng)
    yield eng
    eng.dispose()


@pytest.fixture(autouse=True)
def clean_db(engine):
    yield
    with engine.begin() as conn:
        for table in reversed(Base.metadata.sorted_tables):
            conn.execute(table.delete())
    limiter.reset()


@pytest.fixture
def client(engine):
    from app.main import app

    with TestClient(app) as c:
        yield c


class Account:
    def __init__(self, client: TestClient, email: str, tokens: dict):
        self.client = client
        self.email = email
        self.tokens = tokens

    @property
    def headers(self) -> dict:
        return {"Authorization": f"Bearer {self.tokens['access_token']}"}

    def get(self, url, **kw):
        return self.client.get(url, headers=self.headers, **kw)

    def post(self, url, **kw):
        return self.client.post(url, headers=self.headers, **kw)

    def patch(self, url, **kw):
        return self.client.patch(url, headers=self.headers, **kw)

    def put(self, url, **kw):
        return self.client.put(url, headers=self.headers, **kw)

    def delete(self, url, **kw):
        return self.client.delete(url, headers=self.headers, **kw)

    @property
    def me(self) -> dict:
        return self.get("/api/v1/auth/me").json()


def register(client: TestClient, email: str | None = None, org: str = "Acme Bids", **extra) -> Account:
    email = email or f"user-{uuid.uuid4().hex[:8]}@example.com"
    r = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": PASSWORD, "full_name": "Test User", "organization_name": org, **extra},
    )
    assert r.status_code == 201, r.text
    return Account(client, email, r.json())


@pytest.fixture
def alice(client) -> Account:
    return register(client, "alice@example.com", "Alice Org")


@pytest.fixture
def bob(client) -> Account:
    return register(client, "bob@example.com", "Bob Org")


def make_tender(acct: Account, **fields) -> dict:
    body = {"title": "Managed IT services", "buyer": "City Council", "reference": "CC-001", **fields}
    r = acct.post("/api/v1/tenders", json=body)
    assert r.status_code == 201, r.text
    return r.json()


TENDER_TEXT = (
    "Invitation to Tender\nContracting Authority: Example City Council\nTender Reference: ECC-2027-01\n"
    "Bidders must hold a valid ISO 27001 certification.\n"
    "The supplier shall provide a service desk available from 08:00 to 18:00.\n"
    "Pricing must be submitted as a fixed monthly fee.\n"
    "Quality will be weighted at 60% and price at 40%.\n"
    "The deadline for receipt of tenders is 3 February 2027 at 12:00.\n"
)


def upload_txt(acct: Account, tender_id: str, text: str = TENDER_TEXT, name: str = "itt.txt") -> dict:
    r = acct.post(f"/api/v1/tenders/{tender_id}/documents", files={"file": (name, text.encode(), "text/plain")})
    assert r.status_code == 201, r.text
    return r.json()


def set_provider(acct: Account, provider: str, api_key: str | None = None, model: str = "") -> dict:
    body: dict = {"provider": provider, "model": model}
    if api_key is not None:
        body["api_key"] = api_key
    r = acct.put("/api/v1/organization/ai-settings", json=body)
    assert r.status_code == 200, r.text
    return r.json()


class FakeAdapter:
    """Mocked provider. Records prompts; returns queued responses or a schema-appropriate default."""

    name = "anthropic"

    def __init__(self):
        self.calls: list[dict] = []
        self.queue: list[str] = []

    def complete(self, config, system, user, max_tokens):
        self.calls.append({"system": system, "user": user, "config": config})
        if self.queue:
            return RawCompletion(self.queue.pop(0), 100, 50)
        if "bid/no-bid advisor" in system:
            data = {
                "recommendation": "bid",
                "score": 72,
                "summary": "Good fit.",
                "factors": [{"name": "Eligibility", "rating": "strong", "score": 8, "assessment": "Meets criteria."}],
                "advantages": ["Strong fit"],
                "risks": ["Tight deadline"],
                "missing_information": [],
                "next_steps": ["Start drafting"],
            }
        elif "senior proposal manager" in system:
            data = {
                "sections": [
                    {"title": "Executive Summary", "guidance": "Summarise.", "requirement_numbers": []},
                    {"title": "ISO response", "guidance": "Answer ISO.", "requirement_numbers": [1]},
                ]
            }
        elif "senior proposal writer" in system:
            data = {"content": "Our approach... [COMPANY INFORMATION REQUIRED]: certificate number.", "unanswered_points": ["Certificate number"]}
        elif "research assistant" in system:
            data = {
                "answer": "The ISO 27001 certification is mandatory.",
                "supported": True,
                "sources": [{"document": "itt.txt", "location": "Section 1", "quote": "Bidders must hold a valid ISO 27001 certification."}],
            }
        else:
            data = {
                "overview": {
                    "buyer": "Example City Council",
                    "title": "ITT",
                    "reference": "ECC-2027-01",
                    "submission_deadline": "3 February 2027",
                    "contract_duration": None,
                    "estimated_value": None,
                    "summary": "IT services.",
                },
                "requirements": [
                    {
                        "description": "Hold ISO 27001 certification",
                        "category": "certification",
                        "is_mandatory": True,
                        "priority": "critical",
                        "source_document": "itt.txt",
                        "page": 7,
                        "quote": "Bidders must hold a valid ISO 27001 certification.",
                        "confidence": 0.9,
                    },
                    {
                        "description": "Provide 24/7 drone delivery",
                        "category": "technical",
                        "is_mandatory": True,
                        "priority": "high",
                        "source_document": "itt.txt",
                        "page": 3,
                        "quote": "Drones must deliver everything 24/7.",
                        "confidence": 0.4,
                    },
                ],
                "evaluation_criteria": [
                    {
                        "name": "Quality",
                        "weight": "60%",
                        "description": "",
                        "source_document": "itt.txt",
                        "page": None,
                        "quote": "Quality will be weighted at 60% and price at 40%.",
                    }
                ],
                "important_dates": [],
                "submission_instructions": [],
                "risks": [],
                "missing_information": ["Contract value not stated"],
            }
        return RawCompletion(json.dumps(data), 1000, 200)


@pytest.fixture
def fake_ai():
    from app.ai.providers.anthropic_provider import AnthropicAdapter

    fake = FakeAdapter()
    register_adapter("anthropic", fake)
    yield fake
    register_adapter("anthropic", AnthropicAdapter())
