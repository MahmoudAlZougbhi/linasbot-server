"""Revision bumps share the write transaction. Readers compare revisions."""

from __future__ import annotations

import time
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Connection, Engine

DOMAINS = (
    "comment_rules",
    "channel_toggles",
    "web_chat",
    "smart_answer_languages",
    "dynamic_messages",
    "request_rules",
    "products",
    "faq",
    "usage_limits",
    "meta_comment_reply",
    "watchlist_pins",
    "economy_policy",
    "feature_flags",
    "team",
    "cm",
)

_ENGINE: Engine | None = None


def set_engine_for_tests(engine: Engine | None) -> None:
    global _ENGINE
    _ENGINE = engine


def _engine() -> Engine:
    if _ENGINE is not None:
        return _ENGINE
    from services.platform.pg_jobs import _engine as platform_engine

    return platform_engine()


def ensure_schema(engine: Engine) -> None:
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS config_revisions (
                    tenant_id TEXT NOT NULL,
                    domain TEXT NOT NULL,
                    revision INTEGER NOT NULL,
                    updated_at DOUBLE PRECISION NOT NULL,
                    PRIMARY KEY (tenant_id, domain)
                )
                """
            )
        )


def bump(conn: Connection, tenant: str, domain: str) -> int:
    if domain not in DOMAINS:
        raise ValueError(f"unknown config domain {domain}")
    row = conn.execute(
        text("SELECT revision FROM config_revisions WHERE tenant_id = :tenant AND domain = :domain"),
        {"tenant": tenant, "domain": domain},
    ).fetchone()
    now = time.time()
    if row is None:
        conn.execute(
            text(
                """
                INSERT INTO config_revisions (tenant_id, domain, revision, updated_at)
                VALUES (:tenant, :domain, 1, :now)
                """
            ),
            {"tenant": tenant, "domain": domain, "now": now},
        )
        return 1
    revision = int(row.revision) + 1
    conn.execute(
        text(
            """
            UPDATE config_revisions
            SET revision = :revision, updated_at = :now
            WHERE tenant_id = :tenant AND domain = :domain
            """
        ),
        {"revision": revision, "now": now, "tenant": tenant, "domain": domain},
    )
    return revision


def current(tenant: str, domain: str, *, engine: Engine | None = None) -> int:
    db = engine or _engine()
    ensure_schema(db)
    with db.connect() as conn:
        row = conn.execute(
            text("SELECT revision FROM config_revisions WHERE tenant_id = :tenant AND domain = :domain"),
            {"tenant": tenant, "domain": domain},
        ).fetchone()
    return int(row.revision) if row else 0


def subscribe(tenant: str, domain: str, *, seen: int, engine: Engine | None = None) -> dict[str, Any]:
    revision = current(tenant, domain, engine=engine)
    return {"tenant": tenant, "domain": domain, "revision": revision, "changed": revision != seen}
