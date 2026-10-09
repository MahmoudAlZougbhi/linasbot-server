"""Postgres AI Setup publish. Used only when cm_store is pg or dual."""

from __future__ import annotations

import hashlib
import json
import time
import uuid
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Engine

from services.config_revision.store import bump, ensure_schema
from services.platform.feature_flags import flag_value


def cm_store_mode() -> str:
    mode = flag_value("cm_store")
    return mode if mode in {"disk", "file", "dual", "pg"} else "disk"


def uses_postgres() -> bool:
    return cm_store_mode() in {"pg", "dual"}


def _checksum(content: dict[str, Any]) -> str:
    body = json.dumps(content, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


class StaleRevision(Exception):
    http_status = 412


def publish(
    engine: Engine,
    *,
    tenant_id: str,
    content: dict[str, Any],
    published_by: str,
    expected_revision: int | None = None,
) -> dict[str, Any]:
    """One transaction: version, pointer, revision, outbox. Commit is all or nothing."""
    ensure_schema(engine)
    from services.platform.pg_jobs import ensure_schema as ensure_jobs

    ensure_jobs(engine)
    version_id = uuid.uuid4().hex
    checksum = _checksum(content)
    body = json.dumps(content, separators=(",", ":"), default=str)
    now = time.time()
    with engine.begin() as conn:
        if engine.dialect.name == "postgresql":
            conn.execute(text("SELECT pg_advisory_xact_lock(hashtext(:tenant))"), {"tenant": tenant_id})
        current = conn.execute(
            text("SELECT revision FROM config_revisions WHERE tenant_id = :tenant AND domain = 'cm'"),
            {"tenant": tenant_id},
        ).fetchone()
        have = int(current.revision) if current else 0
        if expected_revision is not None and have != expected_revision:
            raise StaleRevision()
        revision = bump(conn, tenant_id, "cm")
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS cm_versions (
                    tenant_id TEXT NOT NULL,
                    version_id TEXT NOT NULL,
                    revision INTEGER NOT NULL,
                    content TEXT NOT NULL,
                    checksum TEXT NOT NULL,
                    created_by TEXT NOT NULL,
                    created_at DOUBLE PRECISION NOT NULL,
                    PRIMARY KEY (tenant_id, version_id)
                )
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS cm_published (
                    tenant_id TEXT PRIMARY KEY,
                    version_id TEXT NOT NULL,
                    revision INTEGER NOT NULL,
                    published_at DOUBLE PRECISION NOT NULL,
                    published_by TEXT NOT NULL,
                    checksum TEXT NOT NULL
                )
                """
            )
        )
        conn.execute(
            text(
                """
                INSERT INTO cm_versions (
                    tenant_id, version_id, revision, content, checksum, created_by, created_at
                ) VALUES (
                    :tenant, :version, :revision, :content, :checksum, :actor, :now
                )
                """
            ),
            {
                "tenant": tenant_id,
                "version": version_id,
                "revision": revision,
                "content": body,
                "checksum": checksum,
                "actor": published_by,
                "now": now,
            },
        )
        conn.execute(
            text(
                """
                INSERT INTO cm_published (tenant_id, version_id, revision, published_at, published_by, checksum)
                VALUES (:tenant, :version, :revision, :now, :actor, :checksum)
                ON CONFLICT (tenant_id) DO UPDATE SET
                    version_id = excluded.version_id,
                    revision = excluded.revision,
                    published_at = excluded.published_at,
                    published_by = excluded.published_by,
                    checksum = excluded.checksum
                """
            ),
            {
                "tenant": tenant_id,
                "version": version_id,
                "revision": revision,
                "now": now,
                "actor": published_by,
                "checksum": checksum,
            },
        )
        conn.execute(
            text(
                """
                INSERT INTO platform_jobs (
                    id, queue, job_type, tenant_id, payload, status, idempotency_key,
                    attempts, max_attempts, run_after, lease_until, lease_owner,
                    last_error, created_at, updated_at
                ) VALUES (
                    :id, 'embeddings', 'reindex', :tenant, :payload, 'queued', :idem,
                    0, 5, :now, NULL, '',
                    NULL, :now, :now
                )
                """
            ),
            {
                "id": uuid.uuid4().hex,
                "tenant": tenant_id,
                "payload": json.dumps({"revision": revision, "version_id": version_id}),
                "idem": f"reindex:{tenant_id}:{revision}",
                "now": now,
            },
        )
    return {"tenant_id": tenant_id, "version_id": version_id, "revision": revision, "checksum": checksum}


def read_published(engine: Engine, tenant_id: str) -> dict[str, Any] | None:
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT version_id, revision, checksum FROM cm_published WHERE tenant_id = :tenant"),
            {"tenant": tenant_id},
        ).fetchone()
    if row is None:
        return None
    return {"version_id": row.version_id, "revision": int(row.revision), "checksum": row.checksum}
