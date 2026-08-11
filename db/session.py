"""PostgreSQL session factory for WhatsApp Cloud coexistence SoT.

Fail closed when WhatsApp Cloud runtime requires a database and
LINAS_WHATSAPP_DATABASE_URL / DATABASE_URL is unset or unreachable.
Never silently fall back to a file-backed WhatsApp binding store.
"""

from __future__ import annotations

import os
from collections.abc import Generator
from contextlib import contextmanager
from typing import Any

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

_ENGINE: Engine | None = None
_SESSION_FACTORY: sessionmaker[Session] | None = None


class WhatsAppDatabaseUnavailable(RuntimeError):
    """Honest unavailable state — PostgreSQL is required for WhatsApp Cloud SoT."""

    code = "WHATSAPP_DB_UNAVAILABLE"


def database_url() -> str | None:
    raw = (os.getenv("LINAS_WHATSAPP_DATABASE_URL") or os.getenv("DATABASE_URL") or "").strip()
    return raw or None


def whatsapp_db_configured() -> bool:
    return bool(database_url())


def _sqlite_allowed() -> bool:
    return (os.getenv("LINAS_WHATSAPP_ALLOW_SQLITE") or "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def get_engine(*, require: bool = True) -> Engine:
    global _ENGINE, _SESSION_FACTORY
    url = database_url()
    if not url:
        if require:
            raise WhatsAppDatabaseUnavailable(
                "WhatsApp Cloud PostgreSQL is not configured. Set LINAS_WHATSAPP_DATABASE_URL "
                "(or DATABASE_URL). File-backed WhatsApp stores are not a live fallback."
            )
        raise WhatsAppDatabaseUnavailable("DATABASE_URL not set")
    if _ENGINE is None:
        if url.startswith("sqlite:"):
            if not _sqlite_allowed():
                raise WhatsAppDatabaseUnavailable(
                    "SQLite is not permitted for WhatsApp SoT unless "
                    "LINAS_WHATSAPP_ALLOW_SQLITE=true (tests only)."
                )
            _ENGINE = create_engine(url, future=True)
        else:
            if not (url.startswith("postgresql://") or url.startswith("postgresql+psycopg2://")):
                raise WhatsAppDatabaseUnavailable(
                    f"Unsupported WhatsApp database URL scheme (PostgreSQL required): {url.split(':', 1)[0]}"
                )
            _ENGINE = create_engine(
                url,
                pool_pre_ping=True,
                pool_size=int(os.getenv("LINAS_WHATSAPP_DB_POOL_SIZE") or "5"),
                max_overflow=int(os.getenv("LINAS_WHATSAPP_DB_MAX_OVERFLOW") or "10"),
                future=True,
            )
        _SESSION_FACTORY = sessionmaker(bind=_ENGINE, autoflush=False, autocommit=False, future=True)
    return _ENGINE


def reset_engine_for_tests() -> None:
    global _ENGINE, _SESSION_FACTORY
    if _ENGINE is not None:
        _ENGINE.dispose()
    _ENGINE = None
    _SESSION_FACTORY = None


@contextmanager
def whatsapp_session(*, require: bool = True) -> Generator[Session, None, None]:
    get_engine(require=require)
    assert _SESSION_FACTORY is not None
    session = _SESSION_FACTORY()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def ping_whatsapp_db() -> dict[str, Any]:
    if not whatsapp_db_configured():
        return {
            "configured": False,
            "reachable": False,
            "status": "unavailable",
            "detail": "LINAS_WHATSAPP_DATABASE_URL / DATABASE_URL not set",
        }
    try:
        engine = get_engine(require=True)
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return {"configured": True, "reachable": True, "status": "ok"}
    except Exception as exc:  # noqa: BLE001 — surface honest error to operators
        return {
            "configured": True,
            "reachable": False,
            "status": "unavailable",
            "detail": f"{type(exc).__name__}: {exc}",
        }
