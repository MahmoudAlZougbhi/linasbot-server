"""Persist ConversationState + pending actions per conversation. Not a customer wallet."""

from __future__ import annotations

import json
import os
import threading
from hashlib import sha256
from pathlib import Path
from typing import Any

from services.customer_ai.contracts.turn import ConversationState, CustomerTurn
from services.membership.pg_store import memory_forced

_LOCK = threading.Lock()
_MEMORY: dict[str, dict[str, Any]] = {}


def reset_conversation_store_for_tests() -> None:
    with _LOCK:
        _MEMORY.clear()
    from services.membership.pg_store import optional_message_session

    with optional_message_session() as session:
        if session is None:
            return
        from services.customer_ai.conversation_store_pg import pg_reset, table_ready

        if table_ready(session):
            pg_reset(session)


def _key(tenant_id: str, conversation_id: str) -> str:
    return f"{(tenant_id or '').strip()}:{(conversation_id or '').strip()}"


def _persist_enabled() -> bool:
    return not memory_forced()


def _sql_ready() -> bool:
    if not _persist_enabled():
        return False
    from services.membership.pg_store import optional_message_session

    with optional_message_session() as session:
        if session is None:
            return False
        from services.customer_ai.conversation_store_pg import table_ready

        return table_ready(session)


def _path_for(key: str) -> Path:
    root = (os.getenv("LINASBOT_DATA_ROOT") or os.getenv("LINAS_DATA_ROOT") or "data").strip()
    digest = sha256(key.encode("utf-8")).hexdigest()[:24]
    return Path(root) / "customer_ai" / "conversations" / f"{digest}.json"


def _load_pg(key: str) -> dict[str, Any] | None:
    from services.membership.pg_store import optional_message_session

    with optional_message_session() as session:
        if session is None:
            return None
        from services.customer_ai.conversation_store_pg import pg_get, table_ready

        if not table_ready(session):
            return None
        return pg_get(session, key)


def _persist_pg(key: str, tenant_id: str, conversation_id: str, payload: dict[str, Any]) -> None:
    from services.membership.pg_store import optional_message_session

    with optional_message_session() as session:
        if session is None:
            return
        from services.customer_ai.conversation_store_pg import pg_upsert, table_ready

        if table_ready(session):
            pg_upsert(
                session,
                store_key=key,
                tenant_id=tenant_id,
                conversation_id=conversation_id,
                payload=payload,
            )


def _load_disk(key: str) -> dict[str, Any] | None:
    path = _path_for(key)
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return data if isinstance(data, dict) else None


def known_conversation_tenant_ids() -> list[str]:
    """Tenants already present on conversation rows. Do not invent ids."""
    with _LOCK:
        ids = {key.split(":", 1)[0] for key in _MEMORY if ":" in key}
    if _persist_enabled():
        from services.membership.pg_store import optional_message_session

        with optional_message_session() as session:
            if session is not None:
                from services.customer_ai.conversation_store_pg import pg_tenant_ids, table_ready

                if table_ready(session):
                    ids.update(pg_tenant_ids(session))
    return sorted(tid for tid in ids if tid)


def load_conversation(tenant_id: str, conversation_id: str) -> dict[str, Any] | None:
    key = _key(tenant_id, conversation_id)
    if not tenant_id.strip() or not conversation_id.strip():
        return None
    if not _persist_enabled():
        with _LOCK:
            return dict(_MEMORY[key]) if key in _MEMORY else None
    data = _load_pg(key)
    if data is None:
        data = _load_disk(key)
        if data is not None:
            _persist_pg(key, tenant_id, conversation_id, data)
    if data is None:
        if _sql_ready():
            return None
        with _LOCK:
            return dict(_MEMORY[key]) if key in _MEMORY else None
    with _LOCK:
        _MEMORY[key] = data
    return dict(data)


def save_conversation(
    tenant_id: str,
    conversation_id: str,
    state: ConversationState,
    pending: list[dict[str, Any]] | None = None,
    *,
    history: list[dict[str, Any]] | None = None,
) -> None:
    key = _key(tenant_id, conversation_id)
    if not tenant_id.strip() or not conversation_id.strip():
        return
    existing: dict[str, Any] = {}
    if history is None:
        if _persist_enabled():
            existing = _load_pg(key) or _load_disk(key) or {}
        if not existing and not _sql_ready():
            with _LOCK:
                existing = dict(_MEMORY.get(key) or {})
    with _LOCK:
        kept_history = list(history) if history is not None else list(existing.get("history") or [])
        payload = {
            "state": state.model_dump(),
            "pending": list(pending or []),
            "history": kept_history,
        }
        _MEMORY[key] = payload
    if not _persist_enabled():
        return
    path = _path_for(key)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        tmp.replace(path)
    except Exception:
        pass
    _persist_pg(key, tenant_id, conversation_id, payload)


def hydrate_turn_state(turn: CustomerTurn) -> CustomerTurn:
    raw = load_conversation(turn.tenant_id, turn.conversation_id)
    if raw is None:
        return turn
    try:
        stored = ConversationState.model_validate(raw.get("state") or {})
    except Exception:
        stored = turn.state
    extra = dict(turn.extra)
    extra["pending_actions"] = list(raw.get("pending") or [])
    return turn.model_copy(update={"state": stored, "extra": extra})


def remember_turn(turn: CustomerTurn, pending: list[dict[str, Any]] | None = None) -> None:
    current = load_conversation(turn.tenant_id, turn.conversation_id) or {}
    if pending is not None:
        rows = list(pending)
    else:
        rows = list(current.get("pending") or [])
    save_conversation(turn.tenant_id, turn.conversation_id, turn.state, rows)
