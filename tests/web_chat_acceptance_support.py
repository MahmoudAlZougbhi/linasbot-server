"""Shared fixtures and helpers for Website Chat acceptance tests."""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import sessionmaker

from db.session import reset_engine_for_tests
from services.web_chat.config_models import WebChatWidgetConfig
from services.web_chat.pg_models import (
    WebChatDeliveryIdempotencyRow,
    WebChatMessageRow,
    WebChatOperationRow,
    WebChatVisitorSessionRow,
    WebChatWidgetRow,
)
from services.web_chat.store_file import WebChatFileStore
from services.web_chat.store_pg import WebChatPgStore
from tests.docker_test_containers import docker_available, start_disposable_postgres

ROOT = Path(__file__).resolve().parents[1]
WIDGET_PROTOCOL_HARNESS = Path(__file__).resolve().parent / "fixtures" / "web_chat_widget_protocol.mjs"
DEFAULT_ALEMBIC_PYTHON = Path("/private/tmp/linas-wa-venv/bin/python")
DEFAULT_ALEMBIC_PYTHON_FALLBACK = Path("/tmp/linas-alembic-114/bin/python")

WEB_CHAT_STORE_PATCHES: tuple[str, ...] = (
    "services.web_chat.store.web_chat_store",
    "modules.web_chat_helpers.web_chat_store",
    "modules.web_chat_public_routes.web_chat_store",
    "services.web_chat.public_handlers.web_chat_store",
    "services.web_chat.delivery_outbox.web_chat_store",
    "modules.web_chat_mobile_routes.web_chat_store",
    "services.web_chat.followup_delivery.web_chat_store",
)

WEB_CHAT_HA_MODELS = (
    WebChatVisitorSessionRow,
    WebChatMessageRow,
    WebChatDeliveryIdempotencyRow,
    WebChatWidgetRow,
    WebChatOperationRow,
)


def patch_web_chat_store(monkeypatch: pytest.MonkeyPatch, store: WebChatPgStore | WebChatFileStore) -> None:
    for target in WEB_CHAT_STORE_PATCHES:
        monkeypatch.setattr(target, store)


def seed_acceptance_widget(store: WebChatPgStore | WebChatFileStore, *, tenant_id: str = "biz") -> tuple[str, str]:
    widget = store.update_widget(
        tenant_id,
        site_url="https://shop.example.com",
        enabled=True,
        integration_mode="linas_widget",
    )
    return widget.widget_key, widget.tenant_id


def seed_widget_config(store: WebChatPgStore, config: WebChatWidgetConfig) -> WebChatWidgetConfig:
    from services.web_chat.ha_repository import with_ha_session
    from services.web_chat.store_pg import _save_widget_row

    with with_ha_session() as db:
        _save_widget_row(db, config)
    return config


def seed_prefix_widget_pair(
    store: WebChatPgStore,
    *,
    prefix: str = "wk1234567890",
) -> tuple[str, str]:
    """Register two widgets sharing the same 12-char localStorage prefix."""
    from services.web_chat.config_models import WebChatWidgetConfig
    from services.web_chat.ha_repository import with_ha_session
    from services.web_chat.store_pg import _save_widget_row

    key_a = prefix + "aaaaaaaaaaaa"
    key_b = prefix + "bbbbbbbbbbbb"
    now = time.time()
    with with_ha_session() as db:
        for tenant_id, widget_key in (("biz-a", key_a), ("biz-b", key_b)):
            config = WebChatWidgetConfig(
                tenant_id=tenant_id,
                widget_key=widget_key,
                site_url="https://shop.example.com",
                enabled=True,
                created_at=now,
                updated_at=now,
                integration_mode="linas_widget",
            )
            _save_widget_row(db, config)
    return key_a, key_b


def patch_entitlements(
    monkeypatch: pytest.MonkeyPatch,
    *,
    tenant_id: str = "biz",
    ent_root: Path | None = None,
) -> None:
    from services.billing_backend import billing_uses_postgres
    from services.entitlements_service import EntitlementsStore
    from tests.web_chat_acceptance_billing import wire_pg_billing_stores

    if billing_uses_postgres():
        wire_pg_billing_stores(monkeypatch)
        from services.entitlements_service import entitlements_store

        entitlements_store.set_plan(tenant_id=tenant_id, plan_id="max", status="active", source="admin")
        return

    from services import entitlements_service as es
    from services.membership import web_gate as wg

    root = ent_root or Path(tempfile.mkdtemp(prefix="web_chat_ent_"))
    ent = EntitlementsStore(root=root / "ent")
    monkeypatch.setattr(es, "entitlements_store", ent)
    monkeypatch.setattr(wg, "entitlements_store", ent)
    ent.set_plan(tenant_id=tenant_id, plan_id="max", status="active", source="admin")


def patch_ai_eligible(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "services.web_chat.processor.evaluate_web_ai_eligibility",
        lambda *_a, **_k: (True, None),
    )
    monkeypatch.setattr(
        "services.web_chat.public_handlers.evaluate_web_ai_eligibility",
        lambda *_a, **_k: (True, None),
    )


def patch_whatsapp_runtime_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Stable Meta adapter env for acceptance servers under full-suite pollution."""
    from services.whatsapp_adapters.whatsapp_factory import WhatsAppFactory

    monkeypatch.setenv("WHATSAPP_API_TOKEN", "acceptance-test-token")
    monkeypatch.setenv("WHATSAPP_PHONE_NUMBER_ID", "acceptance-phone-id")
    WhatsAppFactory._current_adapter = None
    WhatsAppFactory._current_provider = "meta"


def patch_acceptance_eligibility(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, *, tenant_id: str = "biz") -> int:
    """Wire PG credit ledger (via acceptance_pg_ha_env) and seed starter credits."""
    patch_ai_eligible(monkeypatch)
    from tests.web_chat_acceptance_billing import seed_acceptance_credit_ledger, wire_pg_billing_stores

    wire_pg_billing_stores(monkeypatch)
    return seed_acceptance_credit_ledger(tenant_id=tenant_id, plan_id="starter")


def patch_ai_reply(monkeypatch: pytest.MonkeyPatch, reply: str = "Acceptance AI reply") -> None:
    from unittest.mock import MagicMock

    from services.web_chat.persistence import PersistOutcome, PersistResult

    persist_mock = AsyncMock(return_value=PersistResult(outcome=PersistOutcome.CREATED, conversation_id="conv-accept"))
    monkeypatch.setattr(
        "services.customer_reply_v2.orchestrator.run_customer_reply_v2_dm",
        AsyncMock(return_value=MagicMock(reply=reply)),
    )
    monkeypatch.setattr("services.web_chat.persistence.persist_web_chat_message", persist_mock)
    monkeypatch.setattr("services.web_chat.processor.persist_web_chat_message", persist_mock)


def bootstrap_http(client: TestClient, widget_key: str) -> dict[str, Any]:
    res = client.post(
        "/api/web-chat/session",
        json={"widget_key": widget_key},
        headers={"Origin": "https://shop.example.com"},
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body.get("session_authority")
    assert body.get("session_id")
    return body


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _start_disposable_postgres(*, db_name: str, container_prefix: str) -> Iterator[str]:
    """Start or reuse a local disposable PostgreSQL container for integration tests."""
    _ensure_psycopg2()
    configured = (os.getenv("LINAS_TEST_POSTGRES_ADVISORY_LOCK_URL") or "").strip()
    if configured:
        from sqlalchemy.engine import make_url

        parsed = make_url(configured)
        if not parsed.drivername.startswith("postgresql"):
            pytest.fail("LINAS_TEST_POSTGRES_ADVISORY_LOCK_URL must use PostgreSQL")
        if (parsed.host or "").lower() not in {"localhost", "127.0.0.1", "::1"}:
            pytest.fail("LINAS_TEST_POSTGRES_ADVISORY_LOCK_URL must be local disposable PostgreSQL")
        _wait_for_postgres(configured)
        yield configured
        return
    if not docker_available():
        pytest.fail("Docker is required to start disposable PostgreSQL for advisory-lock tests")
    try:
        yield from start_disposable_postgres(
            db_name=db_name,
            container_prefix=container_prefix,
            wait_for_ready=_wait_for_postgres,
        )
    except RuntimeError as exc:
        pytest.fail(str(exc))


@pytest.fixture(scope="session")
def postgres_advisory_lock_url() -> Iterator[str]:
    """Disposable local PostgreSQL for Meta registry advisory-lock integration tests."""
    generator = _start_disposable_postgres(
        db_name="meta_registry_advisory_lock",
        container_prefix="linas-advisory-lock",
    )
    url = next(generator)
    try:
        yield url
    finally:
        generator.close()


def _alembic_python() -> str:
    configured = (os.getenv("LINAS_TEST_ALEMBIC_PYTHON") or "").strip()
    venv = (os.getenv("LINAS_QG_VENV") or "").strip()
    candidates = [
        configured,
        str(DEFAULT_ALEMBIC_PYTHON),
        str(DEFAULT_ALEMBIC_PYTHON_FALLBACK),
        f"{venv}/bin/python" if venv else "",
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
    pytest.fail("Alembic 1.14 + psycopg2 interpreter is required for PostgreSQL acceptance")


def _ensure_psycopg2() -> None:
    try:
        import psycopg2  # noqa: F401

        return
    except ImportError:
        pass
    for candidate in (
        DEFAULT_ALEMBIC_PYTHON,
        DEFAULT_ALEMBIC_PYTHON_FALLBACK,
        Path((os.getenv("LINAS_QG_VENV") or "").strip()) / "bin" / "python",
    ):
        if not candidate.is_file():
            continue
        venv_root = candidate.parent.parent
        for site in venv_root.glob("lib/python*/site-packages"):
            sys.path.append(str(site))
            try:
                import psycopg2  # noqa: F401

                return
            except ImportError:
                sys.path.pop()
    pytest.fail("psycopg2 is required for PostgreSQL acceptance tests")


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
    pytest.fail(f"disposable PostgreSQL did not become ready ({last_error})")


def _alembic_upgrade(url: str) -> None:
    python_bin = _alembic_python()
    env = os.environ.copy()
    env["DATABASE_URL"] = url
    env["LINAS_WHATSAPP_DATABASE_URL"] = url
    env["PYTHONPATH"] = str(ROOT)
    completed = subprocess.run(
        [python_bin, "-m", "alembic", "upgrade", "head"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )
    if completed.returncode != 0:
        pytest.fail(f"alembic upgrade failed: {completed.stderr or completed.stdout}")


def _probe_live_http(base_url: str, path: str, *, timeout: float = 1.0) -> bool:
    try:
        with urllib.request.urlopen(f"{base_url.rstrip('/')}{path}", timeout=timeout) as response:
            return response.status == 200
    except (urllib.error.URLError, TimeoutError, ValueError):
        return False


def node_available() -> bool:
    try:
        proc = subprocess.run(["node", "--version"], check=False, capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.TimeoutExpired):
        return False
    return proc.returncode == 0


def run_widget_protocol_harness(
    *,
    scenario: str,
    api_base: str,
    widget_key: str,
    origin: str = "https://shop.example.com",
    extra_env: dict[str, str] | None = None,
) -> dict[str, Any]:
    env = os.environ.copy()
    env.update(
        {
            "WEB_CHAT_API_BASE": api_base.rstrip("/"),
            "WEB_CHAT_WIDGET_KEY": widget_key,
            "WEB_CHAT_ORIGIN": origin,
            "WEB_CHAT_SCENARIO": scenario,
        }
    )
    if extra_env:
        env.update(extra_env)
    proc = subprocess.run(
        ["node", str(WIDGET_PROTOCOL_HARNESS)],
        cwd=ROOT,
        env=env,
        check=False,
        capture_output=True,
        text=True,
        timeout=60,
    )
    if proc.returncode != 0:
        raise AssertionError(
            f"widget protocol harness failed ({scenario}): stdout={proc.stdout!r} stderr={proc.stderr!r}"
        )
    return json.loads(proc.stdout.strip().splitlines()[-1])


def _create_ha_engine(db_path: Path):
    url = f"sqlite:///{db_path}"
    engine = create_engine(url, future=True)

    @event.listens_for(engine, "connect")
    def _fk(dbapi_conn, _connection_record) -> None:  # type: ignore[no-untyped-def]
        dbapi_conn.execute("PRAGMA foreign_keys=ON")

    for model in WEB_CHAT_HA_MODELS:
        model.__table__.create(engine, checkfirst=True)
    return engine, url


def _wait_for_acceptance_postgres(url: str) -> None:
    _wait_for_postgres(url)
    _alembic_upgrade(url)


@pytest.fixture(scope="session")
def postgres_acceptance_url() -> Iterator[str]:
    """Disposable local PostgreSQL with full alembic head (mandatory acceptance backend)."""
    _ensure_psycopg2()
    configured = (os.getenv("LINAS_TEST_WEB_CHAT_POSTGRES_URL") or "").strip() or (
        os.getenv("LINAS_TEST_ALEMBIC_POSTGRES_URL") or ""
    ).strip()
    if configured:
        from sqlalchemy.engine import make_url

        parsed = make_url(configured)
        if not parsed.drivername.startswith("postgresql"):
            pytest.fail("configured PostgreSQL acceptance URL must use a PostgreSQL driver")
        if (parsed.host or "").lower() not in {"localhost", "127.0.0.1", "::1"}:
            pytest.fail("configured PostgreSQL acceptance URL must be local disposable PostgreSQL")
        _wait_for_postgres(configured)
        _alembic_upgrade(configured)
        yield configured
        return
    if not docker_available():
        pytest.fail("Docker is required to start disposable PostgreSQL for acceptance tests")
    generator = _start_acceptance_postgres()
    url = next(generator)
    try:
        yield url
    finally:
        generator.close()


def _start_acceptance_postgres() -> Iterator[str]:
    yield from start_disposable_postgres(
        db_name="web_chat_accept",
        container_prefix="linas-web-chat-accept",
        wait_for_ready=_wait_for_acceptance_postgres,
    )


def _truncate_web_chat_pg_tables(url: str) -> None:
    engine = create_engine(url, pool_pre_ping=True)
    with engine.begin() as conn:
        conn.execute(
            text(
                "TRUNCATE web_chat_delivery_idempotency, web_chat_messages, "
                "web_chat_operations, web_chat_visitor_sessions, web_chat_widgets "
                "RESTART IDENTITY CASCADE"
            )
        )


@pytest.fixture()
def acceptance_pg_ha_env(postgres_acceptance_url: str, monkeypatch: pytest.MonkeyPatch) -> Iterator[str]:
    """PostgreSQL HA + billing credit ledger for mandatory acceptance."""
    from tests.web_chat_acceptance_billing import truncate_billing_pg_tables

    _truncate_web_chat_pg_tables(postgres_acceptance_url)
    truncate_billing_pg_tables(postgres_acceptance_url)
    monkeypatch.setenv("LINAS_WHATSAPP_DATABASE_URL", postgres_acceptance_url)
    monkeypatch.setenv("LINAS_BILLING_BACKEND", "postgres")
    monkeypatch.delenv("LINAS_WHATSAPP_ALLOW_SQLITE", raising=False)
    reset_engine_for_tests()
    yield postgres_acceptance_url
    reset_engine_for_tests()


@pytest.fixture()
def web_chat_pg_store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, acceptance_pg_ha_env: str) -> WebChatPgStore:
    from tests.web_chat_acceptance_billing import wire_pg_billing_stores

    store = WebChatPgStore()
    patch_web_chat_store(monkeypatch, store)
    wire_pg_billing_stores(monkeypatch)
    return store


@pytest.fixture()
def acceptance_ha_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[str]:
    """SQLite HA tables (supplementary only; not used for mandatory PG acceptance)."""
    from datetime import datetime

    from services.web_chat import operation as web_chat_operation

    def _sqlite_now() -> datetime:
        return datetime.utcnow()

    monkeypatch.setattr(web_chat_operation, "_now", _sqlite_now)

    engine, url = _create_ha_engine(tmp_path / "acceptance_ha.db")
    monkeypatch.setenv("LINAS_WHATSAPP_DATABASE_URL", url)
    monkeypatch.setenv("LINAS_WHATSAPP_ALLOW_SQLITE", "true")
    monkeypatch.setenv("WEB_CHAT_ALLOW_FILE_STORE", "true")
    reset_engine_for_tests()
    yield url
    engine.dispose()
    reset_engine_for_tests()


@pytest.fixture()
def acceptance_store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, acceptance_pg_ha_env: str) -> WebChatPgStore:
    store = WebChatPgStore()
    patch_web_chat_store(monkeypatch, store)
    return store


@pytest.fixture()
def acceptance_client(acceptance_store: WebChatPgStore, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("WEB_CHAT_PUBLIC_AVAILABILITY", "true")
    patch_entitlements(monkeypatch, ent_root=tmp_path)
    patch_ai_eligible(monkeypatch)
    patch_whatsapp_runtime_env(monkeypatch)
    from main import app

    return TestClient(app)


@pytest.fixture()
def acceptance_live_server(
    acceptance_store: WebChatPgStore, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Iterator[str]:
    import uvicorn

    monkeypatch.setenv("WEB_CHAT_PUBLIC_AVAILABILITY", "true")
    patch_entitlements(monkeypatch, ent_root=tmp_path)
    patch_ai_eligible(monkeypatch)
    patch_whatsapp_runtime_env(monkeypatch)
    from main import app

    port = _free_port()
    base_url = f"http://127.0.0.1:{port}"
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error")
    server = uvicorn.Server(config)

    def _serve() -> None:
        server.run()

    thread = threading.Thread(target=_serve, daemon=True)
    thread.start()
    deadline = time.time() + 20
    ready = False
    while time.time() < deadline:
        if _probe_live_http(base_url, "/web-chat/widget-runtime.js"):
            ready = True
            break
        time.sleep(0.1)
    if not ready:
        server.should_exit = True
        pytest.fail("live acceptance TCP server did not become ready")
    try:
        yield base_url
    finally:
        server.should_exit = True


@pytest.fixture()
def web_chat_ha_db(acceptance_pg_ha_env: str) -> Any:
    """Session factory bound to the mandatory PostgreSQL acceptance database."""
    engine = create_engine(acceptance_pg_ha_env, future=True)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    return Session
