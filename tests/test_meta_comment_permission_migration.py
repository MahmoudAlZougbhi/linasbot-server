"""Alembic upgrade/downgrade + pre-LB backfill for comment permission columns."""

from __future__ import annotations

import os
import subprocess
from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy import create_engine, inspect, text

from tests.docker_test_containers import docker_available, start_disposable_postgres
from tests.web_chat_acceptance_support import (
    _ensure_psycopg2,
    _wait_for_postgres,
)

ROOT = Path(__file__).resolve().parents[1]
PREV_HEAD = "20260825_tenant_runtime_cfg"
HEAD_ID = "20260826_omnichannel_rel"
DEFAULT_ALEMBIC_PYTHON = Path("/tmp/linas-alembic-114/bin/python")
COMMENT_PERM_COLUMNS = (
    "comment_permission_status",
    "comment_permission_verified_at",
    "comment_permission_source",
    "comment_permission_credential_id",
    "comment_permission_token_fingerprint",
)


def _alembic_python() -> str:
    configured = (os.getenv("LINAS_TEST_ALEMBIC_PYTHON") or "").strip()
    venv = (os.getenv("LINAS_QG_VENV") or "").strip()
    candidates = [
        configured,
        str(DEFAULT_ALEMBIC_PYTHON),
        f"{venv}/bin/python" if venv else "",
        str(ROOT / ".venv/bin/python"),
    ]
    for candidate in candidates:
        if not candidate or not Path(candidate).is_file():
            continue
        probe = subprocess.run(
            [candidate, "-c", "from alembic.config import Config; import psycopg2"],
            cwd="/tmp",
            check=False,
            capture_output=True,
            text=True,
        )
        if probe.returncode == 0:
            return candidate
    pytest.skip("Alembic 1.14 + psycopg2 interpreter is not available for disposable PostgreSQL")


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
        pytest.skip("Docker is required for disposable PostgreSQL alembic migration tests")
    generator = start_disposable_postgres(
        db_name="meta_comment_permission_migration",
        container_prefix="linas-alembic",
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


def _binding_columns(url: str) -> set[str]:
    engine = create_engine(url, pool_pre_ping=True)
    inspector = inspect(engine)
    return {column["name"] for column in inspector.get_columns("meta_asset_bindings")}


def _stamped(url: str) -> set[str]:
    engine = create_engine(url, pool_pre_ping=True)
    with engine.connect() as conn:
        rows = conn.execute(text("SELECT version_num FROM alembic_version")).all()
    return {str(row[0]) for row in rows}


@pytest.mark.integration
def test_comment_permission_migration_upgrade_downgrade_roundtrip(postgres_url: str) -> None:
    assert _alembic(postgres_url, "upgrade", PREV_HEAD).returncode == 0
    assert _stamped(postgres_url) == {PREV_HEAD}
    before = _binding_columns(postgres_url)
    assert not any(column in before for column in COMMENT_PERM_COLUMNS)

    upgrade = _alembic(postgres_url, "upgrade", HEAD_ID)
    assert upgrade.returncode == 0, upgrade.stderr or upgrade.stdout
    assert _stamped(postgres_url) == {HEAD_ID}
    after = _binding_columns(postgres_url)
    assert all(column in after for column in COMMENT_PERM_COLUMNS)

    engine = create_engine(postgres_url, pool_pre_ping=True)
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT comment_permission_status, comment_permission_verified_at FROM meta_asset_bindings LIMIT 1")
        ).first()
    if row is not None:
        assert str(row[0]) == "unknown"
        assert float(row[1] or 0) == 0.0

    downgrade = _alembic(postgres_url, "downgrade", PREV_HEAD)
    assert downgrade.returncode == 0, downgrade.stderr or downgrade.stdout
    assert _stamped(postgres_url) == {PREV_HEAD}
    reverted = _binding_columns(postgres_url)
    assert not any(column in reverted for column in COMMENT_PERM_COLUMNS)

    reupgrade = _alembic(postgres_url, "upgrade", HEAD_ID)
    assert reupgrade.returncode == 0, reupgrade.stderr or reupgrade.stdout
    assert _stamped(postgres_url) == {HEAD_ID}


@pytest.mark.integration
def test_comment_permission_migration_is_additive_only() -> None:
    path = ROOT / "alembic/versions/20260826_meta_comment_permission_verification.py"
    text = path.read_text(encoding="utf-8")
    upgrade_body = text.split("def upgrade", 1)[1].split("def downgrade", 1)[0]
    assert "drop_column" not in upgrade_body
    assert "drop_table" not in upgrade_body
