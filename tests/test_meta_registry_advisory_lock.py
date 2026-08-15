"""Regression coverage for the shared Meta registry PostgreSQL lock."""

from __future__ import annotations

import os
import threading
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

from scripts.ha.rekey_meta_whatsapp_credentials import REKEY_ADVISORY_LOCK_KEY
from services.meta_app_registry_pg_store import (
    acquire_registry_advisory_lock,
    release_registry_advisory_lock,
)


class _RecordingSession:
    def __init__(self, dialect_name: str) -> None:
        self._bind = SimpleNamespace(dialect=SimpleNamespace(name=dialect_name))
        self.executed: list[tuple[str, dict[str, int] | None]] = []

    def get_bind(self) -> object:
        return self._bind

    def execute(self, statement: object, params: dict[str, int] | None = None) -> None:
        self.executed.append((str(statement), params))


def test_registry_lock_is_transaction_scoped_and_release_cannot_unlock_early() -> None:
    session = _RecordingSession("postgresql")

    acquire_registry_advisory_lock(session)  # type: ignore[arg-type]
    release_registry_advisory_lock(session)  # type: ignore[arg-type]

    assert len(session.executed) == 1
    statement, params = session.executed[0]
    assert "pg_advisory_xact_lock" in statement
    assert "pg_advisory_lock(" not in statement
    assert "pg_advisory_unlock" not in statement
    assert params and isinstance(params["k"], int)


def test_registry_lock_remains_a_noop_for_non_postgres_sessions() -> None:
    session = _RecordingSession("sqlite")

    acquire_registry_advisory_lock(session)  # type: ignore[arg-type]
    release_registry_advisory_lock(session)  # type: ignore[arg-type]

    assert session.executed == []


@pytest.mark.integration
def test_two_postgres_connections_block_until_owner_transaction_commits() -> None:
    """Exercise the real wrapper against an explicitly local, dedicated test DB.

    This test never falls back to either runtime database variable.  Set
    ``LINAS_TEST_POSTGRES_ADVISORY_LOCK_URL`` to opt in.
    """

    raw_url = (os.getenv("LINAS_TEST_POSTGRES_ADVISORY_LOCK_URL") or "").strip()
    if not raw_url:
        pytest.skip("dedicated local PostgreSQL advisory-lock test URL is not configured")
    url = make_url(raw_url)
    if not url.drivername.startswith("postgresql"):
        pytest.fail("advisory-lock integration URL must use PostgreSQL")
    if (url.host or "").lower() not in {"localhost", "127.0.0.1", "::1"}:
        pytest.fail("advisory-lock integration URL must point to local dedicated test PostgreSQL")

    engine = create_engine(url, pool_size=2, max_overflow=0, future=True)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)
    owner = factory()
    contender_started = threading.Event()
    contender_acquired = threading.Event()

    try:
        owner.begin()
        owner_pid = int(owner.scalar(text("SELECT pg_backend_pid()")))
        acquire_registry_advisory_lock(owner)

        def _contend() -> int:
            with factory() as contender:
                contender.begin()
                contender.execute(text("SET LOCAL statement_timeout = '5s'"))
                contender_pid = int(contender.scalar(text("SELECT pg_backend_pid()")))
                contender_started.set()
                acquire_registry_advisory_lock(contender)
                contender_acquired.set()
                release_registry_advisory_lock(contender)
                contender.commit()
                return contender_pid

        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(_contend)
            assert contender_started.wait(timeout=2)
            assert not contender_acquired.wait(timeout=0.25)

            # The compatibility release is deliberately a no-op.  The second
            # connection must remain blocked until the owner commits.
            release_registry_advisory_lock(owner)
            assert not contender_acquired.wait(timeout=0.25)

            owner.commit()
            assert contender_acquired.wait(timeout=3)
            contender_pid = future.result(timeout=3)

        assert contender_pid != owner_pid
    finally:
        if owner.in_transaction():
            owner.rollback()
        owner.close()
        engine.dispose()


@pytest.mark.integration
def test_cross_product_rekey_lock_excludes_a_second_postgres_transaction() -> None:
    """Prove the dedicated rekey xact lock is fail-fast and commit-scoped."""

    raw_url = (os.getenv("LINAS_TEST_POSTGRES_ADVISORY_LOCK_URL") or "").strip()
    if not raw_url:
        pytest.skip("dedicated local PostgreSQL advisory-lock test URL is not configured")
    url = make_url(raw_url)
    if not url.drivername.startswith("postgresql"):
        pytest.fail("advisory-lock integration URL must use PostgreSQL")
    if (url.host or "").lower() not in {"localhost", "127.0.0.1", "::1"}:
        pytest.fail("advisory-lock integration URL must point to local dedicated test PostgreSQL")

    engine = create_engine(url, pool_size=2, max_overflow=0, future=True)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)
    owner = factory()
    contender = factory()
    try:
        owner.begin()
        contender.begin()
        assert owner.scalar(
            text("SELECT pg_try_advisory_xact_lock(:key)"),
            {"key": REKEY_ADVISORY_LOCK_KEY},
        )
        assert not contender.scalar(
            text("SELECT pg_try_advisory_xact_lock(:key)"),
            {"key": REKEY_ADVISORY_LOCK_KEY},
        )
        owner.commit()
        assert contender.scalar(
            text("SELECT pg_try_advisory_xact_lock(:key)"),
            {"key": REKEY_ADVISORY_LOCK_KEY},
        )
        contender.rollback()
    finally:
        if owner.in_transaction():
            owner.rollback()
        if contender.in_transaction():
            contender.rollback()
        owner.close()
        contender.close()
        engine.dispose()
