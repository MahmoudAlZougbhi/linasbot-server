"""Postgres live chat history. Firestore stays the default until the flag is pg."""

from __future__ import annotations

import time
import uuid

from sqlalchemy import text
from sqlalchemy.engine import Engine

from services.platform.feature_flags import flag_value


def livechat_mode() -> str:
    mode = flag_value("livechat_store")
    return mode if mode in {"firestore", "legacy", "dual", "pg"} else "firestore"


def ensure_schema(engine: Engine) -> None:
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS conversations (
                    tenant_id TEXT NOT NULL,
                    conversation_id TEXT NOT NULL,
                    channel TEXT NOT NULL,
                    status TEXT NOT NULL,
                    unread_count INTEGER NOT NULL DEFAULT 0,
                    last_message_at DOUBLE PRECISION NOT NULL,
                    PRIMARY KEY (tenant_id, conversation_id)
                )
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS messages (
                    tenant_id TEXT NOT NULL,
                    conversation_id TEXT NOT NULL,
                    message_id TEXT NOT NULL,
                    direction TEXT NOT NULL,
                    body TEXT NOT NULL,
                    created_at DOUBLE PRECISION NOT NULL,
                    PRIMARY KEY (tenant_id, conversation_id, message_id)
                )
                """
            )
        )


def append_message(
    engine: Engine,
    *,
    tenant_id: str,
    conversation_id: str,
    body: str,
    direction: str = "in",
) -> str:
    ensure_schema(engine)
    message_id = uuid.uuid4().hex
    now = time.time()
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO conversations (
                    tenant_id, conversation_id, channel, status, unread_count, last_message_at
                ) VALUES (
                    :tenant, :conversation, 'web', 'open', 1, :now
                )
                ON CONFLICT (tenant_id, conversation_id) DO UPDATE SET
                    unread_count = conversations.unread_count + 1,
                    last_message_at = excluded.last_message_at
                """
            ),
            {"tenant": tenant_id, "conversation": conversation_id, "now": now},
        )
        conn.execute(
            text(
                """
                INSERT INTO messages (
                    tenant_id, conversation_id, message_id, direction, body, created_at
                ) VALUES (
                    :tenant, :conversation, :message, :direction, :body, :now
                )
                """
            ),
            {
                "tenant": tenant_id,
                "conversation": conversation_id,
                "message": message_id,
                "direction": direction,
                "body": body,
                "now": now,
            },
        )
    return message_id
