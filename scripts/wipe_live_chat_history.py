"""Hard-delete Live Chat history. Keeps users, sessions, channels, and the inbound ledger."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from sqlalchemy import text

CHAT_DELETE_SQL = (
    "DELETE FROM linas_chat_messages",
    "DELETE FROM linas_chat_threads",
    "DELETE FROM web_chat_messages",
    "DELETE FROM web_chat_visitor_sessions",
    "DELETE FROM web_chat_delivery_idempotency",
    """
    DELETE FROM linas_documents
    WHERE parent = 'artifacts/linas-ai-bot-backend/live_chat_index'
       OR parent LIKE '%/conversations'
       OR parent LIKE '%/thread_messages'
    """,
)

REDIS_PATTERNS = ("linas:claim:inbox_counters:*",)


def chat_delete_statements() -> tuple[str, ...]:
    return CHAT_DELETE_SQL


def _engine() -> Any:
    from sqlalchemy import create_engine

    url = os.environ.get("LINAS_WHATSAPP_DATABASE_URL") or os.environ.get("DATABASE_URL")
    if not url:
        raise SystemExit("LINAS_WHATSAPP_DATABASE_URL is required")
    return create_engine(url)


def _count(conn: Any, sql: str) -> int:
    return int(conn.execute(text(sql)).scalar() or 0)


def wipe_postgres(conn: Any) -> dict[str, int]:
    before = {
        "threads": _count(conn, "SELECT COUNT(*) FROM linas_chat_threads"),
        "messages": _count(conn, "SELECT COUNT(*) FROM linas_chat_messages"),
        "web_visitors": _count(conn, "SELECT COUNT(*) FROM web_chat_visitor_sessions"),
        "web_messages": _count(conn, "SELECT COUNT(*) FROM web_chat_messages"),
        "index_docs": _count(
            conn,
            "SELECT COUNT(*) FROM linas_documents WHERE parent = 'artifacts/linas-ai-bot-backend/live_chat_index'",
        ),
        "conversation_docs": _count(conn, "SELECT COUNT(*) FROM linas_documents WHERE parent LIKE '%/conversations'"),
    }
    for statement in chat_delete_statements():
        conn.execute(text(statement))
    after_threads = _count(conn, "SELECT COUNT(*) FROM linas_chat_threads")
    after_messages = _count(conn, "SELECT COUNT(*) FROM linas_chat_messages")
    users = _count(
        conn,
        "SELECT COUNT(*) FROM linas_documents WHERE parent = 'artifacts/linas-ai-bot-backend/dashboard_users'",
    )
    inbound = _count(conn, "SELECT COUNT(*) FROM linas_inbound_events")
    return {
        **{f"deleted_{key}": value for key, value in before.items()},
        "threads_remaining": after_threads,
        "messages_remaining": after_messages,
        "dashboard_users_remaining": users,
        "inbound_events_remaining": inbound,
    }


def wipe_redis() -> int:
    url = (os.getenv("REDIS_URL") or "").strip()
    if not url:
        return 0
    import redis

    client = redis.Redis.from_url(url, decode_responses=True, socket_connect_timeout=1.5, socket_timeout=1.5)
    deleted = 0
    for pattern in REDIS_PATTERNS:
        for key in client.scan_iter(match=pattern, count=200):
            removed = client.delete(key)
            if isinstance(removed, int):
                deleted += removed
    return deleted


def wipe_guest_files() -> int:
    root = Path(os.getenv("LINASBOT_DATA_ROOT") or "/opt/linasbot_data") / "guest_chat"
    if not root.is_dir():
        return 0
    removed = 0
    for path in root.glob("*.json"):
        path.unlink()
        removed += 1
    return removed


def wipe_inbox_cache() -> None:
    candidates = [
        Path(os.getenv("LIVECHAT_UNIFIED_CACHE_PATH") or ""),
        Path(os.getenv("LINASBOT_DATA_ROOT") or "/opt/linasbot_data") / "live_chat_unified_cache.json",
        Path("/opt/linasbot/data/live_chat_unified_cache.json"),
    ]
    for path in candidates:
        if not str(path) or not path.is_file():
            continue
        path.write_text("{}\n", encoding="utf-8")


def main() -> None:
    engine = _engine()
    with engine.begin() as conn:
        counts = wipe_postgres(conn)
    counts["redis_keys"] = wipe_redis()
    counts["guest_files"] = wipe_guest_files()
    wipe_inbox_cache()
    print(json.dumps(counts, sort_keys=True))


if __name__ == "__main__":
    main()
