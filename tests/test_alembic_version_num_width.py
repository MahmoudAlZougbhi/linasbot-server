"""Disposable PostgreSQL: widen version_num before the live long revision id."""

from __future__ import annotations

import os
import subprocess
import sys
import time
from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import DataError, OperationalError, ProgrammingError

ROOT = Path(__file__).resolve().parents[1]
LONG_ID = "20260814_meta_credential_archived_at"
WIDEN_ID = "20260814_widen_ver_num"
MERGE_ID = "20260815_merge_sfu_meta_cred"
HEAD_ID = "20260826_omnichannel_rel"
OLDER_HEAD = "20260812_meta_app_registry"
SFU_HEAD = "20260813_sfu_channels_enabled"
DEFAULT_ALEMBIC_PYTHON = Path("/tmp/linas-alembic-114/bin/python")


def _alembic_python() -> str:
    configured = (os.getenv("LINAS_TEST_ALEMBIC_PYTHON") or "").strip()
    venv = (os.getenv("LINAS_QG_VENV") or "").strip()
    candidates = [configured, str(DEFAULT_ALEMBIC_PYTHON), f"{venv}/bin/python" if venv else ""]
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


def _ensure_psycopg2() -> None:
    try:
        import psycopg2  # noqa: F401

        return
    except ImportError:
        pass
    venv_root = DEFAULT_ALEMBIC_PYTHON.parent.parent
    for site in venv_root.glob("lib/python*/site-packages"):
        sys.path.append(str(site))
        try:
            import psycopg2  # noqa: F401

            return
        except ImportError:
            sys.path.pop()
    pytest.skip("psycopg2 is required for disposable PostgreSQL alembic tests")


def _docker_available() -> bool:
    return subprocess.run(["docker", "info"], check=False, capture_output=True).returncode == 0


def _wait_for_postgres(url: str) -> None:
    engine = create_engine(url, pool_pre_ping=True)
    deadline = time.time() + 40
    last_error = ""
    while time.time() < deadline:
        try:
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            return
        except OperationalError as exc:
            last_error = type(exc).__name__
            time.sleep(0.4)
    raise RuntimeError(f"disposable PostgreSQL did not become ready ({last_error})")


@pytest.fixture(scope="module")
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
        yield configured
        return
    if not _docker_available():
        pytest.skip("Docker is not available to start disposable PostgreSQL")
    name = f"linas-alembic-width-{os.getpid()}"
    run = subprocess.run(
        [
            "docker",
            "run",
            "-d",
            "--rm",
            "--name",
            name,
            "-e",
            "POSTGRES_PASSWORD=linas-test",
            "-e",
            "POSTGRES_DB=alembic_width",
            "-p",
            "127.0.0.1::5432",
            "postgres:16-alpine",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    if run.returncode != 0:
        pytest.skip(f"could not start disposable PostgreSQL: {run.stderr.strip() or run.stdout.strip()}")
    try:
        port_proc = subprocess.run(
            ["docker", "port", name, "5432/tcp"],
            check=True,
            capture_output=True,
            text=True,
        )
        host_port = port_proc.stdout.strip().rsplit(":", 1)[-1]
        url = f"postgresql+psycopg2://postgres:linas-test@127.0.0.1:{host_port}/alembic_width"
        _wait_for_postgres(url)
        yield url
    finally:
        subprocess.run(["docker", "stop", "-t", "2", name], check=False, capture_output=True)


def _version_meta(url: str) -> tuple[int | None, set[str]]:
    engine = create_engine(url, pool_pre_ping=True)
    with engine.connect() as conn:
        maxlen = conn.execute(
            text(
                """
                SELECT character_maximum_length
                FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND table_name = 'alembic_version'
                  AND column_name = 'version_num'
                """
            )
        ).scalar()
        rows = conn.execute(text("SELECT version_num FROM alembic_version")).all()
    return (int(maxlen) if maxlen is not None else None, {str(row[0]) for row in rows})


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


def _alembic_ok(url: str, *args: str) -> None:
    completed = _alembic(url, *args)
    if completed.returncode != 0:
        raise AssertionError(completed.stderr or completed.stdout)


def test_env_py_overrides_alembic_114_default_version_num_width() -> None:
    source = (ROOT / "alembic" / "env.py").read_text(encoding="utf-8")
    assert "DefaultImpl.version_table_impl" in source
    assert "_VERSION_NUM_WIDTH = 64" in source
    assert "version_table_impl is required" in source


def test_fresh_and_older_head_postgres_can_stamp_the_long_revision(postgres_url: str) -> None:
    _alembic_ok(postgres_url, "upgrade", OLDER_HEAD)
    _maxlen, current = _version_meta(postgres_url)
    assert OLDER_HEAD in current
    assert all(len(item) <= 32 for item in current)

    engine = create_engine(postgres_url, pool_pre_ping=True)
    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE alembic_version ALTER COLUMN version_num TYPE VARCHAR(32)"))
    insert_failed = False
    with engine.connect() as conn:
        trans = conn.begin()
        try:
            conn.execute(text("INSERT INTO alembic_version(version_num) VALUES (:vid)"), {"vid": LONG_ID})
            trans.commit()
        except (DataError, ProgrammingError):
            trans.rollback()
            insert_failed = True
    assert insert_failed is True

    maxlen, current = _version_meta(postgres_url)
    assert maxlen == 32
    assert LONG_ID not in current

    _alembic_ok(postgres_url, "upgrade", LONG_ID)
    maxlen, current = _version_meta(postgres_url)
    assert maxlen == 64
    assert current == {LONG_ID}

    with engine.connect() as conn:
        archived = conn.execute(
            text(
                """
                SELECT EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_schema = 'public'
                      AND table_name = 'meta_binding_credentials'
                      AND column_name = 'archived_at'
                )
                """
            )
        ).scalar()
    assert archived is True

    _alembic_ok(postgres_url, "upgrade", "head")
    maxlen, current = _version_meta(postgres_url)
    assert maxlen == 64
    assert current == {HEAD_ID}

    _alembic_ok(postgres_url, "downgrade", "-1")
    maxlen, current = _version_meta(postgres_url)
    assert current == {"20260825_tenant_runtime_cfg"}

    _alembic_ok(postgres_url, "downgrade", "-1")
    maxlen, current = _version_meta(postgres_url)
    assert current == {"20260824_prod_search_meta"}

    _alembic_ok(postgres_url, "downgrade", "-1")
    maxlen, current = _version_meta(postgres_url)
    assert current == {"20260823_tiktok_biz"}

    _alembic_ok(postgres_url, "downgrade", "-1")
    maxlen, current = _version_meta(postgres_url)
    assert current == {"20260822_product_images_max5"}

    _alembic_ok(postgres_url, "downgrade", "-1")
    maxlen, current = _version_meta(postgres_url)
    assert current == {"20260821_request_drafts"}

    _alembic_ok(postgres_url, "downgrade", "-1")
    maxlen, current = _version_meta(postgres_url)
    assert current == {"20260820_request_graphs"}

    _alembic_ok(postgres_url, "downgrade", "-1")
    maxlen, current = _version_meta(postgres_url)
    assert current == {"20260817_web_chat_ha"}

    _alembic_ok(postgres_url, "downgrade", "-1")
    maxlen, current = _version_meta(postgres_url)
    assert current == {"20260819_prod_img_idx"}

    _alembic_ok(postgres_url, "downgrade", "-1")
    maxlen, current = _version_meta(postgres_url)
    assert current == {"20260818_ai_services"}

    _alembic_ok(postgres_url, "downgrade", "-1")
    maxlen, current = _version_meta(postgres_url)
    assert current == {"20260818_ai_products_phase2"}

    _alembic_ok(postgres_url, "downgrade", "-1")
    maxlen, current = _version_meta(postgres_url)
    assert current == {"20260817_ai_products"}

    _alembic_ok(postgres_url, "downgrade", "-1")
    maxlen, current = _version_meta(postgres_url)
    assert current == {"20260816_pending_downgrade"}

    _alembic_ok(postgres_url, "downgrade", "-1")
    maxlen, current = _version_meta(postgres_url)
    assert current == {MERGE_ID}

    # Alembic 1.14 merge -1 is Ambiguous walk (two parents). The merge is a
    # schema no-op; stamp --purge of both live heads restores the pre-merge rows.
    relative = _alembic(postgres_url, "downgrade", "-1")
    assert relative.returncode != 0
    assert "Ambiguous walk" in (relative.stderr or "")
    _alembic_ok(postgres_url, "stamp", "--purge", SFU_HEAD, LONG_ID)
    maxlen, current = _version_meta(postgres_url)
    assert maxlen == 64
    assert current == {SFU_HEAD, LONG_ID}
    assert WIDEN_ID not in current
