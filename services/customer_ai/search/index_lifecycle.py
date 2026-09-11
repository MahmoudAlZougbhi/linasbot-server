"""Durable per-tenant index lifecycle. Owner-visible; never stores secrets."""

from __future__ import annotations

from typing import Any, Literal

from services.customer_ai.search.index_status import reset_index_status_for_tests, set_index_status

IndexLifecycle = Literal["NO_INDEX", "BUILDING", "READY", "ACTIVE", "STALE", "FAILED"]

_MEMORY: dict[str, dict[str, Any]] = {}
_OWNER_KEYS = (
    "tenant_id",
    "status",
    "content_revision",
    "active_version",
    "candidate_version",
    "rollback_version",
    "embedding_model",
    "contextual_model",
    "contextualization_version",
    "chunker_version",
    "compiler_version",
    "failure_reason",
    "retry_count",
    "last_indexed_at",
    "updated_at",
    "manual_index_required",
)


def reset_lifecycle_for_tests() -> None:
    _MEMORY.clear()
    reset_index_status_for_tests()


def _blank(tenant_id: str) -> dict[str, Any]:
    return {
        "tenant_id": tenant_id,
        "status": "NO_INDEX",
        "content_revision": "",
        "active_version": "",
        "candidate_version": "",
        "rollback_version": "",
        "embedding_model": "",
        "contextual_model": "",
        "contextualization_version": "",
        "chunker_version": "",
        "compiler_version": "",
        "failure_reason": "",
        "retry_count": 0,
        "last_indexed_at": None,
        "updated_at": None,
        "manual_index_required": False,
    }


def owner_status(tenant_id: str) -> dict[str, Any]:
    row = get_lifecycle(tenant_id)
    return {key: row.get(key) for key in _OWNER_KEYS}


def get_lifecycle(tenant_id: str) -> dict[str, Any]:
    tid = (tenant_id or "").strip()
    if not tid:
        return {**_blank(""), "failure_reason": "missing_tenant"}
    mem = _MEMORY.get(tid)
    if mem:
        return dict(mem)
    loaded = _load_sql(tid)
    if loaded:
        _MEMORY[tid] = loaded
        return dict(loaded)
    return _blank(tid)


def upsert_lifecycle(tenant_id: str, **fields: Any) -> dict[str, Any]:
    tid = (tenant_id or "").strip()
    if not tid:
        return _blank("")
    current = get_lifecycle(tid)
    row = {**current, **fields, "tenant_id": tid, "manual_index_required": False}
    reason = str(row.get("failure_reason") or "")[:240]
    row["failure_reason"] = reason
    try:
        row["retry_count"] = int(row.get("retry_count") or 0)
    except (TypeError, ValueError):
        row["retry_count"] = 0
    _MEMORY[tid] = row
    status = str(row.get("status") or "NO_INDEX")
    set_index_status(
        tid,
        status=status,  # type: ignore[arg-type]
        content_version=str(row.get("content_revision") or ""),
        index_version=str(row.get("active_version") or row.get("candidate_version") or ""),
        reason=reason,
    )
    _save_sql(row)
    return dict(row)


def mark_building(tenant_id: str, *, revision: str, reason: str) -> dict[str, Any]:
    prev = get_lifecycle(tenant_id)
    return upsert_lifecycle(
        tenant_id,
        status="BUILDING",
        content_revision=revision or str(prev.get("content_revision") or ""),
        candidate_version=revision or str(prev.get("candidate_version") or ""),
        failure_reason=reason,
    )


def mark_stale_durable(tenant_id: str, *, revision: str = "", reason: str = "content_changed") -> dict[str, Any]:
    prev = get_lifecycle(tenant_id)
    return upsert_lifecycle(
        tenant_id,
        status="STALE",
        content_revision=revision or str(prev.get("content_revision") or ""),
        failure_reason=reason,
    )


def mark_failed(tenant_id: str, *, revision: str, reason: str) -> dict[str, Any]:
    prev = get_lifecycle(tenant_id)
    return upsert_lifecycle(
        tenant_id,
        status="FAILED",
        content_revision=revision or str(prev.get("content_revision") or ""),
        failure_reason=reason,
        retry_count=int(prev.get("retry_count") or 0) + 1,
    )


def mark_candidate_ready(tenant_id: str, **fields: Any) -> dict[str, Any]:
    return upsert_lifecycle(tenant_id, status="READY", failure_reason="", **fields)


def mark_active(tenant_id: str, **fields: Any) -> dict[str, Any]:
    from datetime import UTC, datetime

    prev = get_lifecycle(tenant_id)
    rollback = str(fields.pop("rollback_version", None) or prev.get("active_version") or "")
    return upsert_lifecycle(
        tenant_id,
        status="ACTIVE",
        failure_reason="",
        retry_count=0,
        last_indexed_at=datetime.now(UTC).isoformat(),
        rollback_version=rollback,
        **fields,
    )


def _load_sql(tenant_id: str) -> dict[str, Any] | None:
    try:
        from sqlalchemy import text

        from db.session import whatsapp_session

        with whatsapp_session(require=True) as session:
            row = (
                session.execute(
                    text(
                        """
                    SELECT tenant_id, status, content_revision, active_version, candidate_version,
                           rollback_version, embedding_model, contextual_model,
                           contextualization_version, chunker_version, compiler_version,
                           failure_reason, retry_count, last_indexed_at, updated_at
                    FROM customer_ai_tenant_index
                    WHERE tenant_id = :tenant_id
                    """
                    ),
                    {"tenant_id": tenant_id},
                )
                .mappings()
                .first()
            )
        if not row:
            return None
        data = dict(row)
        data["last_indexed_at"] = _ts(data.get("last_indexed_at"))
        data["updated_at"] = _ts(data.get("updated_at"))
        data["manual_index_required"] = False
        return data
    except Exception:
        return None


def _save_sql(row: dict[str, Any]) -> None:
    try:
        from sqlalchemy import text

        from db.session import whatsapp_session

        with whatsapp_session(require=True) as session:
            session.execute(
                text(
                    """
                    INSERT INTO customer_ai_tenant_index (
                        tenant_id, status, content_revision, active_version, candidate_version,
                        rollback_version, embedding_model, contextual_model,
                        contextualization_version, chunker_version, compiler_version,
                        failure_reason, retry_count, last_indexed_at, updated_at
                    ) VALUES (
                        :tenant_id, :status, :content_revision, :active_version, :candidate_version,
                        :rollback_version, :embedding_model, :contextual_model,
                        :contextualization_version, :chunker_version, :compiler_version,
                        :failure_reason, :retry_count,
                        CAST(:last_indexed_at AS timestamptz), now()
                    )
                    ON CONFLICT (tenant_id) DO UPDATE SET
                        status = EXCLUDED.status,
                        content_revision = EXCLUDED.content_revision,
                        active_version = EXCLUDED.active_version,
                        candidate_version = EXCLUDED.candidate_version,
                        rollback_version = EXCLUDED.rollback_version,
                        embedding_model = EXCLUDED.embedding_model,
                        contextual_model = EXCLUDED.contextual_model,
                        contextualization_version = EXCLUDED.contextualization_version,
                        chunker_version = EXCLUDED.chunker_version,
                        compiler_version = EXCLUDED.compiler_version,
                        failure_reason = EXCLUDED.failure_reason,
                        retry_count = EXCLUDED.retry_count,
                        last_indexed_at = COALESCE(EXCLUDED.last_indexed_at, customer_ai_tenant_index.last_indexed_at),
                        updated_at = now()
                    """
                ),
                {
                    "tenant_id": row["tenant_id"],
                    "status": str(row.get("status") or "NO_INDEX")[:32],
                    "content_revision": str(row.get("content_revision") or "")[:128],
                    "active_version": str(row.get("active_version") or "")[:128],
                    "candidate_version": str(row.get("candidate_version") or "")[:128],
                    "rollback_version": str(row.get("rollback_version") or "")[:128],
                    "embedding_model": str(row.get("embedding_model") or "")[:64],
                    "contextual_model": str(row.get("contextual_model") or "")[:64],
                    "contextualization_version": str(row.get("contextualization_version") or "")[:64],
                    "chunker_version": str(row.get("chunker_version") or "")[:64],
                    "compiler_version": str(row.get("compiler_version") or "")[:64],
                    "failure_reason": str(row.get("failure_reason") or "")[:240],
                    "retry_count": int(row.get("retry_count") or 0),
                    "last_indexed_at": row.get("last_indexed_at"),
                },
            )
    except Exception:
        return


def _ts(value: Any) -> str | None:
    if value is None:
        return None
    iso = getattr(value, "isoformat", None)
    return iso() if callable(iso) else str(value)
