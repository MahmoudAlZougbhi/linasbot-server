"""Alembic acceptance for Website Chat HA migration (20260817_web_chat_ha)."""

from __future__ import annotations

import os
import subprocess
from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text

from tests.docker_test_containers import docker_available, start_disposable_postgres
from tests.web_chat_acceptance_support import (
    _alembic_python,
    _ensure_psycopg2,
    _wait_for_postgres,
)

ROOT = Path(__file__).resolve().parents[1]
HEAD_ID = "20260817_web_chat_ha"
PREVIOUS_HEAD = "20260819_prod_img_idx"
MIGRATION_TABLES = frozenset(
    {
        "web_chat_visitor_sessions",
        "web_chat_messages",
        "web_chat_delivery_idempotency",
        "web_chat_widgets",
        "web_chat_operations",
    }
)


@pytest.fixture()
def postgres_url() -> Iterator[str]:
    _ensure_psycopg2()
    configured = (os.getenv("LINAS_TEST_ALEMBIC_POSTGRES_URL") or "").strip()
    if configured:
        from sqlalchemy.engine import make_url

        parsed = make_url(configured)
        if not parsed.drivername.startswith("postgresql"):
            pytest.fail("LINAS_TEST_ALEMBIC_POSTGRES_URL must be PostgreSQL")
        if (parsed.host or "").lower() not in {"localhost", "127.0.0.1", "::1"}:
            pytest.fail("LINAS_TEST_ALEMBIC_POSTGRES_URL must be local disposable PostgreSQL")
        _wait_for_postgres(configured)
        yield configured
        return
    if not docker_available():
        pytest.fail("Docker is required for disposable PostgreSQL alembic acceptance")
    generator = start_disposable_postgres(
        db_name="web_chat_ha",
        container_prefix="linas-web-chat-ha",
        wait_for_ready=_wait_for_postgres,
    )
    url = next(generator)
    try:
        yield url
    finally:
        generator.close()


def _alembic(url: str, *args: str) -> subprocess.CompletedProcess[str]:
    python_bin = _alembic_python()
    env = os.environ.copy()
    env["DATABASE_URL"] = url
    env["LINAS_WHATSAPP_DATABASE_URL"] = url
    env["PYTHONPATH"] = str(ROOT)
    return subprocess.run(
        [python_bin, "-m", "alembic", *args],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )


def _tables(url: str) -> set[str]:
    engine = create_engine(url, pool_pre_ping=True)
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                """
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = 'public'
                  AND table_name LIKE 'web_chat_%'
                """
            )
        ).all()
    return {str(row[0]) for row in rows}


@pytest.mark.integration
def test_clean_upgrade_creates_web_chat_tables(postgres_url: str) -> None:
    completed = _alembic(postgres_url, "upgrade", "head")
    assert completed.returncode == 0, completed.stderr or completed.stdout
    assert _tables(postgres_url) == set(MIGRATION_TABLES)
    engine = create_engine(postgres_url, pool_pre_ping=True)
    with engine.connect() as conn:
        stamped = {row[0] for row in conn.execute(text("SELECT version_num FROM alembic_version")).all()}
    assert stamped == {HEAD_ID}


@pytest.mark.integration
def test_previous_head_upgrade_then_web_chat_head(postgres_url: str) -> None:
    assert _alembic(postgres_url, "upgrade", PREVIOUS_HEAD).returncode == 0
    assert _tables(postgres_url) == set()
    assert _alembic(postgres_url, "upgrade", HEAD_ID).returncode == 0
    assert _tables(postgres_url) == set(MIGRATION_TABLES)


@pytest.mark.integration
def test_schema_absence_before_upgrade_has_no_web_chat_tables(postgres_url: str) -> None:
    assert _tables(postgres_url) == set()
    engine = create_engine(postgres_url, pool_pre_ping=True)
    with engine.connect() as conn:
        exists = conn.execute(text("SELECT to_regclass('public.web_chat_visitor_sessions') IS NOT NULL")).scalar()
    assert exists is False


@pytest.mark.integration
def test_rollback_and_replay_web_chat_migration(postgres_url: str) -> None:
    assert _alembic(postgres_url, "upgrade", "head").returncode == 0
    assert _tables(postgres_url) == set(MIGRATION_TABLES)
    assert _alembic(postgres_url, "downgrade", "-1").returncode == 0
    assert _tables(postgres_url) == set()
    assert _alembic(postgres_url, "upgrade", "head").returncode == 0
    assert _tables(postgres_url) == set(MIGRATION_TABLES)
