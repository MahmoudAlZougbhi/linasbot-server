"""Deployed commit identity. Never shells out to git."""

from __future__ import annotations

import os
import socket
from pathlib import Path


def git_sha() -> str:
    value = (os.getenv("GIT_SHA") or "").strip()
    if value:
        return value
    path = Path(os.getenv("LINAS_RELEASE_SHA_FILE") or "/var/lib/linasbot/release_git_sha")
    try:
        stored = path.read_text(encoding="utf-8").strip()
    except OSError:
        stored = ""
    return stored or "unknown"


def short_sha() -> str:
    value = git_sha()
    if value == "unknown":
        return value
    return value[:12]


def build_time() -> str:
    value = (os.getenv("LINAS_BUILD_TIME") or "").strip()
    if value:
        return value
    path = Path(os.getenv("LINAS_BUILD_TIME_FILE") or "/var/lib/linasbot/release_build_time")
    try:
        stored = path.read_text(encoding="utf-8").strip()
    except OSError:
        stored = ""
    return stored


def version_payload() -> dict[str, str]:
    from services.billing.membership.activation_readiness import expected_alembic_head

    head = ""
    try:
        from sqlalchemy import text

        from db.session import whatsapp_session

        with whatsapp_session(require=False) as session:
            if session is not None:
                found = session.execute(text("SELECT version_num FROM alembic_version")).scalars().all()
                head = str(found[0]) if found else ""
    except Exception:
        head = ""
    expected = ""
    try:
        expected = expected_alembic_head()
    except Exception:
        expected = ""
    voyage_429 = "0"
    try:
        from services.owner_portal.voyage_metrics import recent_count

        voyage_429 = str(recent_count(seconds=300))
    except Exception:
        voyage_429 = "0"
    return {
        "git_sha": git_sha(),
        "build_time": build_time(),
        "node": socket.gethostname(),
        "db_alembic_head": head,
        "expected_alembic_head": expected,
        "voyage_429_5m": voyage_429,
    }
