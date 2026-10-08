"""Shared retry queue for owner embeds. Postgres is the source of truth."""

from __future__ import annotations

import json
import logging
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import text

logger = logging.getLogger(__name__)

_MEMORY: list[dict[str, Any]] = []


def reset_jobs_for_tests() -> None:
    _MEMORY.clear()


def _ensure(session: Any) -> None:
    session.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS owner_portal_embed_jobs (
                id TEXT PRIMARY KEY,
                kind TEXT NOT NULL,
                ref_id TEXT NOT NULL,
                payload TEXT NOT NULL DEFAULT '{}',
                attempts INTEGER NOT NULL DEFAULT 0,
                next_at TEXT NOT NULL DEFAULT ''
            )
            """
        )
    )


def enqueue_embed(*, kind: str, ref_id: str, payload: dict[str, Any]) -> str:
    job_id = uuid.uuid4().hex
    row = {
        "id": job_id,
        "kind": kind,
        "ref_id": ref_id,
        "payload": dict(payload),
        "attempts": 0,
        "next_at": datetime.now(UTC).isoformat(),
    }
    try:
        from db.session import whatsapp_session

        with whatsapp_session(require=False) as session:
            if session is None:
                raise RuntimeError("no session")
            _ensure(session)
            session.execute(
                text(
                    """
                    INSERT INTO owner_portal_embed_jobs (id, kind, ref_id, payload, attempts, next_at)
                    VALUES (:id, :kind, :ref_id, :payload, 0, :next_at)
                    """
                ),
                {
                    "id": job_id,
                    "kind": kind,
                    "ref_id": ref_id,
                    "payload": json.dumps(payload, default=str),
                    "next_at": row["next_at"],
                },
            )
            session.commit()
            return job_id
    except Exception:
        logger.debug("embed job stored in memory", exc_info=True)
    _MEMORY.append(row)
    return job_id


def _due(limit: int) -> list[dict[str, Any]]:
    now = datetime.now(UTC).isoformat()
    try:
        from db.session import whatsapp_session

        with whatsapp_session(require=False) as session:
            if session is not None:
                _ensure(session)
                found = session.execute(
                    text(
                        """
                        SELECT id, kind, ref_id, payload, attempts, next_at
                        FROM owner_portal_embed_jobs
                        WHERE next_at <= :now
                        ORDER BY next_at
                        LIMIT :limit
                        """
                    ),
                    {"now": now, "limit": limit},
                ).all()
                return [
                    {
                        "id": str(row[0]),
                        "kind": str(row[1]),
                        "ref_id": str(row[2]),
                        "payload": json.loads(row[3] or "{}"),
                        "attempts": int(row[4] or 0),
                        "next_at": str(row[5] or ""),
                    }
                    for row in found
                ]
    except Exception:
        logger.debug("embed jobs read from memory", exc_info=True)
    return [dict(row) for row in _MEMORY if str(row.get("next_at") or "") <= now][:limit]


def _finish(job_id: str, *, failed: bool, attempts: int) -> None:
    if not failed:
        _MEMORY[:] = [row for row in _MEMORY if row.get("id") != job_id]
    else:
        later = (datetime.now(UTC) + timedelta(seconds=min(300, 15 * (attempts + 1)))).isoformat()
        for row in _MEMORY:
            if row.get("id") == job_id:
                row["attempts"] = attempts + 1
                row["next_at"] = later
    try:
        from db.session import whatsapp_session

        with whatsapp_session(require=False) as session:
            if session is None:
                return
            if not failed:
                session.execute(text("DELETE FROM owner_portal_embed_jobs WHERE id = :id"), {"id": job_id})
            else:
                later = (datetime.now(UTC) + timedelta(seconds=min(300, 15 * (attempts + 1)))).isoformat()
                session.execute(
                    text(
                        """
                        UPDATE owner_portal_embed_jobs
                        SET attempts = :attempts, next_at = :next_at
                        WHERE id = :id
                        """
                    ),
                    {"id": job_id, "attempts": attempts + 1, "next_at": later},
                )
            session.commit()
    except Exception:
        logger.debug("embed job update stayed in memory", exc_info=True)


def _run(job: dict[str, Any]) -> bool:
    kind = str(job.get("kind") or "")
    raw_payload = job.get("payload")
    payload: dict[str, Any] = raw_payload if isinstance(raw_payload, dict) else {}
    if kind == "qa":
        from services.owner_portal.owner_qa import _index

        return _index(str(job.get("ref_id") or ""), list(payload.get("rows") or []), enqueue=False)
    if kind == "kb":
        from services.owner_portal.owner_kb_store import _reindex

        return _reindex(
            str(job.get("ref_id") or ""),
            str(payload.get("title") or ""),
            str(payload.get("body") or ""),
            enqueue=False,
        )
    return False


def drain_embed_jobs(limit: int = 20) -> int:
    done = 0
    for job in _due(limit):
        try:
            ok = _run(job)
        except Exception:
            logger.exception("embed job %s failed", job.get("id"))
            ok = False
        if ok:
            _finish(str(job["id"]), failed=False, attempts=int(job.get("attempts") or 0))
            done += 1
        else:
            _finish(str(job["id"]), failed=True, attempts=int(job.get("attempts") or 0))
    return done
