"""Durable platform-admin catalog overlays. Memory store stays for tests."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from services.membership.pg_store import memory_forced


def persist_enabled() -> bool:
    return not memory_forced()


def catalog_admin_path() -> Path:
    root = (os.getenv("LINASBOT_DATA_ROOT") or os.getenv("LINAS_DATA_ROOT") or "data").strip()
    return Path(root) / "platform" / "message_catalog_admin.json"


def reset_admin_state_for_tests() -> None:
    from services.membership.pg_store import optional_message_session

    with optional_message_session() as session:
        if session is None:
            return
        from services.membership.catalog_admin_pg import pg_reset, table_ready

        if table_ready(session):
            pg_reset(session)


def load_admin_state() -> dict[str, Any] | None:
    if not persist_enabled():
        return None
    from services.membership.pg_store import optional_message_session

    with optional_message_session() as session:
        if session is not None:
            from services.membership.catalog_admin_pg import pg_load, pg_upsert, table_ready

            if table_ready(session):
                found = pg_load(session)
                if found is not None:
                    return found
                disk = _load_disk()
                if disk is not None:
                    pg_upsert(
                        session,
                        draft=dict(disk.get("draft") or {}),
                        revision=int(disk.get("revision") or 1),
                        published=bool(disk.get("published")),
                        audit=[row for row in (disk.get("audit") or []) if isinstance(row, dict)],
                    )
                    return disk
                return None
    return _load_disk()


def save_admin_state(
    *,
    draft: dict[str, Any],
    revision: int,
    published: bool,
    audit: list[dict[str, Any]],
) -> None:
    if not persist_enabled():
        return
    payload = {
        "draft": draft,
        "revision": revision,
        "published": published,
        "audit": audit[-50:],
    }
    path = catalog_admin_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(path)
    except Exception:
        pass
    from services.membership.pg_store import optional_message_session

    with optional_message_session() as session:
        if session is None:
            return
        from services.membership.catalog_admin_pg import pg_upsert, table_ready

        if table_ready(session):
            pg_upsert(session, draft=draft, revision=revision, published=published, audit=audit)


def _load_disk() -> dict[str, Any] | None:
    path = catalog_admin_path()
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return data if isinstance(data, dict) else None
