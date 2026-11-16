"""Migrations apply cleanly on an empty database and match the ORM models exactly."""

from __future__ import annotations

from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import create_engine, inspect

from app.db.base import Base
from tests.conftest import BACKEND_DIR


def test_upgrade_downgrade_and_no_drift(tmp_path):
    engine = create_engine(f"sqlite:///{(tmp_path / 'm.db').as_posix()}")
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    with engine.begin() as conn:
        cfg.attributes["connection"] = conn
        command.upgrade(cfg, "head")
    assert {"users", "tenders", "requirements", "documents", "stored_files"} <= set(inspect(engine).get_table_names())
    with engine.connect() as conn:
        diff = compare_metadata(MigrationContext.configure(conn, opts={"compare_type": True}), Base.metadata)
    assert diff == [], diff
    with engine.begin() as conn:
        cfg.attributes["connection"] = conn
        command.downgrade(cfg, "base")
    assert set(inspect(engine).get_table_names()) <= {"alembic_version"}
