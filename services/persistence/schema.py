"""Postgres tables that replace the Firestore document stores."""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.orm import Session

_STATEMENTS = (
    """
    CREATE TABLE IF NOT EXISTS linas_chat_threads (
        tenant_id TEXT NOT NULL,
        conversation_id TEXT NOT NULL,
        user_id TEXT NOT NULL,
        channel TEXT NOT NULL DEFAULT '',
        conversation_state TEXT NOT NULL DEFAULT 'bot_active',
        last_message_at TEXT NOT NULL,
        last_message_text TEXT NOT NULL DEFAULT '',
        user_name TEXT NOT NULL DEFAULT '',
        user_phone TEXT NOT NULL DEFAULT '',
        operator_id TEXT NOT NULL DEFAULT '',
        human_takeover_active INTEGER NOT NULL DEFAULT 0,
        unread_count INTEGER NOT NULL DEFAULT 0,
        message_count INTEGER NOT NULL DEFAULT 0,
        payload_json TEXT NOT NULL DEFAULT '{}',
        PRIMARY KEY (tenant_id, conversation_id)
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS linas_chat_threads_inbox
    ON linas_chat_threads (tenant_id, last_message_at, conversation_id)
    """,
    """
    CREATE TABLE IF NOT EXISTS linas_chat_messages (
        tenant_id TEXT NOT NULL,
        conversation_id TEXT NOT NULL,
        message_id TEXT NOT NULL,
        role TEXT NOT NULL,
        body TEXT NOT NULL DEFAULT '',
        sent_at TEXT NOT NULL,
        metadata_json TEXT NOT NULL DEFAULT '{}',
        PRIMARY KEY (tenant_id, conversation_id, message_id)
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS linas_chat_messages_thread
    ON linas_chat_messages (tenant_id, conversation_id, sent_at)
    """,
    """
    CREATE TABLE IF NOT EXISTS linas_inbound_events (
        event_id TEXT PRIMARY KEY,
        tenant_id TEXT NOT NULL DEFAULT '',
        state TEXT NOT NULL,
        record_json TEXT NOT NULL,
        updated_at REAL NOT NULL
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS linas_inbound_events_state
    ON linas_inbound_events (state, updated_at)
    """,
    """
    CREATE TABLE IF NOT EXISTS linas_dashboard_users (
        user_id TEXT PRIMARY KEY,
        email TEXT NOT NULL DEFAULT '',
        tenant_id TEXT NOT NULL DEFAULT '',
        record_json TEXT NOT NULL
    )
    """,
    """
    CREATE UNIQUE INDEX IF NOT EXISTS linas_dashboard_users_email
    ON linas_dashboard_users (email)
    WHERE email <> ''
    """,
)


def ensure_schema(session: Session) -> None:
    for statement in _STATEMENTS:
        session.execute(text(statement))
    session.flush()
