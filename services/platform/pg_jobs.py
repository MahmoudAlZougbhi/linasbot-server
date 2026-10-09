"""Postgres durable queue. Selected only when queue_backend=pg."""

from __future__ import annotations

import json
import random
import threading
import time
import uuid
from typing import Any

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError

from services.queues.models import QueueJob

PG_QUEUES = (
    "ai_reply",
    "embeddings",
    "outbound_send",
    "webhook_process",
    "owner_copilot",
    "maintenance",
)

_ENGINE: Engine | None = None
_SCHEMA_LOCK = threading.Lock()
_SCHEMA_READY: set[str] = set()


def set_engine_for_tests(engine: Engine | None) -> None:
    global _ENGINE
    _ENGINE = engine


def _engine() -> Engine:
    if _ENGINE is not None:
        return _ENGINE
    import os

    url = (os.getenv("LINAS_PLATFORM_DATABASE_URL") or os.getenv("LINAS_WHATSAPP_DATABASE_URL") or "").strip()
    if not url:
        raise RuntimeError("platform database url unset")
    return create_engine(url, pool_pre_ping=True)


def ensure_schema(engine: Engine) -> None:
    key = str(engine.url)
    if key in _SCHEMA_READY:
        return
    with _SCHEMA_LOCK:
        if key in _SCHEMA_READY:
            return
        _ensure_schema_locked(engine)
        _SCHEMA_READY.add(key)


def _ensure_schema_locked(engine: Engine) -> None:
    statements = (
        """
        CREATE TABLE IF NOT EXISTS platform_jobs (
            id TEXT PRIMARY KEY,
            queue TEXT NOT NULL,
            job_type TEXT NOT NULL,
            tenant_id TEXT NOT NULL,
            payload TEXT NOT NULL,
            status TEXT NOT NULL,
            idempotency_key TEXT,
            attempts INTEGER NOT NULL DEFAULT 0,
            max_attempts INTEGER NOT NULL DEFAULT 5,
            run_after DOUBLE PRECISION NOT NULL,
            lease_until DOUBLE PRECISION,
            lease_owner TEXT,
            last_error TEXT,
            created_at DOUBLE PRECISION NOT NULL,
            updated_at DOUBLE PRECISION NOT NULL
        )
        """,
        """
        CREATE UNIQUE INDEX IF NOT EXISTS ux_platform_jobs_idem
        ON platform_jobs (queue, idempotency_key)
        WHERE idempotency_key IS NOT NULL
        """,
        """
        CREATE TABLE IF NOT EXISTS platform_job_dlq (
            id TEXT PRIMARY KEY,
            job_id TEXT NOT NULL,
            queue TEXT NOT NULL,
            tenant_id TEXT NOT NULL,
            payload TEXT NOT NULL,
            reason TEXT NOT NULL,
            attempts INTEGER NOT NULL,
            created_at DOUBLE PRECISION NOT NULL
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS outbound_deliveries (
            idempotency_key TEXT PRIMARY KEY,
            tenant_id TEXT NOT NULL,
            provider TEXT NOT NULL,
            provider_message_id TEXT,
            created_at DOUBLE PRECISION NOT NULL
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS inbound_events (
            provider TEXT NOT NULL,
            provider_event_id TEXT NOT NULL,
            tenant_id TEXT NOT NULL,
            payload TEXT NOT NULL,
            status TEXT NOT NULL,
            created_at DOUBLE PRECISION NOT NULL,
            PRIMARY KEY (provider, provider_event_id)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS feature_flags (
            flag_key TEXT NOT NULL,
            scope TEXT NOT NULL,
            scope_id TEXT NOT NULL DEFAULT '',
            value TEXT NOT NULL,
            updated_by TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            PRIMARY KEY (flag_key, scope, scope_id)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS scheduler_leader (
            name TEXT PRIMARY KEY,
            owner TEXT NOT NULL
        )
        """,
    )
    with engine.begin() as conn:
        for statement in statements:
            conn.execute(text(statement))


def _job_from_row(row: Any) -> QueueJob:
    return QueueJob.from_dict(
        {
            "id": row.id,
            "queue": row.queue,
            "job_type": row.job_type,
            "tenant_id": row.tenant_id,
            "payload": json.loads(row.payload),
            "status": row.status,
            "created_at": row.created_at,
            "attempts": row.attempts,
            "max_attempts": row.max_attempts,
            "last_error": row.last_error,
            "idempotency_key": row.idempotency_key,
            "available_at": row.run_after,
            "updated_at": row.updated_at,
            "lease_owner": row.lease_owner or "",
        }
    )


def backoff_seconds(attempts: int, *, rng: random.Random | None = None) -> float:
    source = rng or random.Random()
    base = min(300.0, float(2 ** max(attempts, 1)))
    return base + source.random()


class PgDurableQueue:
    backend_name = "pg"

    def __init__(self, engine: Engine | None = None) -> None:
        self._engine = engine or _engine()
        ensure_schema(self._engine)

    def enqueue(self, job: QueueJob) -> QueueJob:
        now = time.time()
        payload = json.dumps(job.payload, separators=(",", ":"), default=str)
        with self._engine.begin() as conn:
            if job.idempotency_key:
                existing = conn.execute(
                    text(
                        """
                        SELECT * FROM platform_jobs
                        WHERE queue = :queue AND idempotency_key = :idem
                        """
                    ),
                    {"queue": job.queue, "idem": job.idempotency_key},
                ).fetchone()
                if existing is not None:
                    return _job_from_row(existing)
            conn.execute(
                text(
                    """
                    INSERT INTO platform_jobs (
                        id, queue, job_type, tenant_id, payload, status, idempotency_key,
                        attempts, max_attempts, run_after, lease_until, lease_owner,
                        last_error, created_at, updated_at
                    ) VALUES (
                        :id, :queue, :job_type, :tenant_id, :payload, 'queued', :idem,
                        0, :max_attempts, :run_after, NULL, '',
                        NULL, :now, :now
                    )
                    """
                ),
                {
                    "id": job.id,
                    "queue": job.queue,
                    "job_type": job.job_type,
                    "tenant_id": job.tenant_id,
                    "payload": payload,
                    "idem": job.idempotency_key,
                    "max_attempts": job.max_attempts,
                    "run_after": job.available_at or now,
                    "now": now,
                },
            )
        job.status = "queued"
        return job

    def claim(self, queue: str, *, worker_id: str, timeout: int = 5) -> QueueJob | None:
        now = time.time()
        lease_until = now + max(timeout, 1)
        skip = " FOR UPDATE SKIP LOCKED" if self._engine.dialect.name == "postgresql" else ""
        select_sql = f"""
            SELECT id FROM platform_jobs
            WHERE queue = :queue
              AND status IN ('queued', 'leased')
              AND run_after <= :now
              AND (lease_until IS NULL OR lease_until < :now)
            ORDER BY created_at
            LIMIT 1{skip}
        """
        with self._engine.begin() as conn:
            row = conn.execute(text(select_sql), {"queue": queue, "now": now}).fetchone()
            if row is None:
                return None
            updated = conn.execute(
                text(
                    """
                    UPDATE platform_jobs
                    SET status = 'leased', attempts = attempts + 1, lease_owner = :owner,
                        lease_until = :lease_until, updated_at = :now
                    WHERE id = :id
                      AND (lease_until IS NULL OR lease_until < :now)
                    """
                ),
                {"owner": worker_id, "lease_until": lease_until, "now": now, "id": row.id},
            )
            if not updated.rowcount:
                return None
            loaded = conn.execute(text("SELECT * FROM platform_jobs WHERE id = :id"), {"id": row.id}).one()
        return _job_from_row(loaded)

    def heartbeat(self, job: QueueJob, *, worker_id: str, extend_seconds: int = 30) -> bool:
        now = time.time()
        with self._engine.begin() as conn:
            result = conn.execute(
                text(
                    """
                    UPDATE platform_jobs
                    SET lease_until = :lease_until, updated_at = :now
                    WHERE id = :id AND lease_owner = :owner AND status = 'leased'
                    """
                ),
                {"lease_until": now + extend_seconds, "now": now, "id": job.id, "owner": worker_id},
            )
        return bool(result.rowcount)

    def release_lease(self, job: QueueJob, *, worker_id: str) -> None:
        now = time.time()
        with self._engine.begin() as conn:
            conn.execute(
                text(
                    """
                    UPDATE platform_jobs
                    SET status = 'queued', lease_owner = '', lease_until = NULL,
                        run_after = :now, updated_at = :now
                    WHERE id = :id AND lease_owner = :owner AND status = 'leased'
                    """
                ),
                {"now": now, "id": job.id, "owner": worker_id},
            )

    def complete(self, job: QueueJob) -> None:
        now = time.time()
        with self._engine.begin() as conn:
            conn.execute(
                text(
                    """
                    UPDATE platform_jobs
                    SET status = 'done', lease_until = NULL, updated_at = :now
                    WHERE id = :id
                    """
                ),
                {"now": now, "id": job.id},
            )

    def fail(self, job: QueueJob, *, error: str, retry: bool) -> bool:
        now = time.time()
        with self._engine.begin() as conn:
            current = conn.execute(text("SELECT * FROM platform_jobs WHERE id = :id"), {"id": job.id}).one()
            give_up = (not retry) or int(current.attempts) >= int(current.max_attempts)
            if give_up:
                conn.execute(
                    text(
                        """
                        INSERT INTO platform_job_dlq (
                            id, job_id, queue, tenant_id, payload, reason, attempts, created_at
                        ) VALUES (
                            :id, :job_id, :queue, :tenant_id, :payload, :reason, :attempts, :now
                        )
                        """
                    ),
                    {
                        "id": uuid.uuid4().hex,
                        "job_id": current.id,
                        "queue": current.queue,
                        "tenant_id": current.tenant_id,
                        "payload": current.payload,
                        "reason": error[:500],
                        "attempts": current.attempts,
                        "now": now,
                    },
                )
                conn.execute(
                    text(
                        """
                        UPDATE platform_jobs
                        SET status = 'dead', last_error = :error, lease_until = NULL, updated_at = :now
                        WHERE id = :id
                        """
                    ),
                    {"error": error[:500], "now": now, "id": job.id},
                )
                return False
            delay = backoff_seconds(int(current.attempts))
            conn.execute(
                text(
                    """
                    UPDATE platform_jobs
                    SET status = 'queued', last_error = :error, lease_owner = '', lease_until = NULL,
                        run_after = :run_after, updated_at = :now
                    WHERE id = :id
                    """
                ),
                {"error": error[:500], "run_after": now + delay, "now": now, "id": job.id},
            )
        return True

    def requeue_soft(self, job: QueueJob, *, delay_seconds: float = 1.0) -> None:
        self.release_lease(job, worker_id=job.lease_owner or "")

    def depth(self) -> dict[str, int]:
        with self._engine.connect() as conn:
            rows = conn.execute(
                text("SELECT queue, COUNT(*) AS n FROM platform_jobs WHERE status = 'queued' GROUP BY queue")
            ).fetchall()
        return {str(row.queue): int(row.n) for row in rows}

    def metrics(self) -> Any:
        from services.scale.queue_protocol import QueueMetrics

        return QueueMetrics(depth_by_queue=self.depth(), oldest_age_seconds={}, dlq_by_queue=self.dlq_depth())

    def ping(self) -> bool:
        with self._engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True

    def dlq_depth(self) -> dict[str, int]:
        with self._engine.connect() as conn:
            rows = conn.execute(text("SELECT queue, COUNT(*) AS n FROM platform_job_dlq GROUP BY queue")).fetchall()
        return {str(row.queue): int(row.n) for row in rows}

    def list_dlq(self, *, limit: int = 50) -> list[dict[str, Any]]:
        with self._engine.connect() as conn:
            rows = conn.execute(
                text(
                    "SELECT id, job_id, queue, tenant_id, reason, attempts FROM platform_job_dlq ORDER BY created_at DESC LIMIT :limit"
                ),
                {"limit": limit},
            ).fetchall()
        return [
            {
                "id": row.id,
                "job_id": row.job_id,
                "queue": row.queue,
                "tenant_id": row.tenant_id,
                "reason": row.reason,
                "attempts": row.attempts,
            }
            for row in rows
        ]

    def retry_dlq(self, job_id: str) -> bool:
        now = time.time()
        with self._engine.begin() as conn:
            updated = conn.execute(
                text(
                    """
                    UPDATE platform_jobs
                    SET status = 'queued', attempts = 0, last_error = NULL,
                        lease_owner = '', lease_until = NULL, run_after = :now, updated_at = :now
                    WHERE id = :id AND status = 'dead'
                    """
                ),
                {"now": now, "id": job_id},
            )
            if not updated.rowcount:
                return False
            conn.execute(text("DELETE FROM platform_job_dlq WHERE job_id = :id"), {"id": job_id})
        return True


def claim_outbound(engine: Engine, *, idempotency_key: str, tenant_id: str, provider: str) -> bool:
    ensure_schema(engine)
    try:
        with engine.begin() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO outbound_deliveries (
                        idempotency_key, tenant_id, provider, provider_message_id, created_at
                    ) VALUES (
                        :key, :tenant, :provider, NULL, :now
                    )
                    """
                ),
                {"key": idempotency_key, "tenant": tenant_id, "provider": provider, "now": time.time()},
            )
    except IntegrityError:
        return False
    return True


def accept_inbound(
    engine: Engine,
    *,
    provider: str,
    provider_event_id: str,
    tenant_id: str,
    payload: dict[str, Any],
) -> bool:
    """Insert the event once and enqueue webhook_process in the same transaction."""
    ensure_schema(engine)
    now = time.time()
    job_id = uuid.uuid4().hex
    body = json.dumps(payload, separators=(",", ":"), default=str)
    idem = f"{provider}:{provider_event_id}"
    with engine.begin() as conn:
        inserted = conn.execute(
            text(
                """
                INSERT INTO inbound_events (
                    provider, provider_event_id, tenant_id, payload, status, created_at
                ) VALUES (
                    :provider, :event_id, :tenant, :payload, 'received', :now
                )
                ON CONFLICT (provider, provider_event_id) DO NOTHING
                """
            ),
            {
                "provider": provider,
                "event_id": provider_event_id,
                "tenant": tenant_id,
                "payload": body,
                "now": now,
            },
        )
        if inserted.rowcount == 0:
            return False
        conn.execute(
            text(
                """
                INSERT INTO platform_jobs (
                    id, queue, job_type, tenant_id, payload, status, idempotency_key,
                    attempts, max_attempts, run_after, lease_until, lease_owner,
                    last_error, created_at, updated_at
                ) VALUES (
                    :id, 'webhook_process', 'webhook_process', :tenant, :payload, 'queued', :idem,
                    0, 5, :now, NULL, '',
                    NULL, :now, :now
                )
                """
            ),
            {"id": job_id, "tenant": tenant_id, "payload": body, "idem": idem, "now": now},
        )
    return True
