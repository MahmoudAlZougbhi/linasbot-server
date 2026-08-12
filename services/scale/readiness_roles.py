"""Role-based readiness builders (API / webhook / AI worker / outbound / requests)."""

from __future__ import annotations

import os
from typing import Any

from services.scale.shutdown import shutdown_coordinator


def _env_role() -> str:
    return (os.getenv("LINAS_SERVICE_ROLE") or "api").strip().lower() or "api"


def readiness_for_role(role: str | None = None) -> dict[str, Any]:
    """
    Build readiness payload for a logical service role.

    BOC is never a readiness dependency (product lock: BOC OFF).
    """
    role_name = (role or _env_role()).strip().lower()
    checks: dict[str, Any] = {"service_role": role_name}
    overall = True

    drain = shutdown_coordinator.snapshot()
    checks["drain"] = {"ok": not drain["draining"], **drain}
    if drain["draining"]:
        overall = False

    if role_name in {"api", "webhook_ingress", "all"}:
        db_ok, db_detail = _postgres_check(required=False)
        checks["postgres"] = db_detail
        # API can serve many routes without WA PG; only hard-fail when URL set but broken.
        if db_detail.get("configured") and not db_ok:
            overall = False

        redis_ok, redis_detail = _redis_check(required=_redis_required_for_live())
        checks["redis"] = redis_detail
        if _redis_required_for_live() and not redis_ok:
            overall = False

        fs_ok, fs_detail = _firestore_check()
        checks["firestore"] = fs_detail
        if role_name in {"api", "all"} and not fs_ok:
            overall = False

    if role_name in {"webhook_ingress", "all"}:
        # Webhook ingress needs durable claim/queue ability when Redis required.
        q_ok, q_detail = _queue_persist_check()
        checks["queue_persist"] = q_detail
        if _redis_required_for_live() and not q_ok:
            overall = False

    if role_name in {"ai_worker", "outbound_worker", "request_worker", "all"}:
        redis_ok, redis_detail = _redis_check(required=True)
        checks["redis"] = redis_detail
        if not redis_ok:
            overall = False
        db_ok, db_detail = _postgres_check(required=False)
        checks["postgres"] = db_detail
        if role_name == "ai_worker":
            openai = bool((os.getenv("OPENAI_API_KEY") or "").strip())
            checks["openai_api_key"] = {"ok": openai, "configured": openai}
            if not openai:
                overall = False

    if role_name == "outbound_worker":
        checks["channel_config"] = {"ok": True, "note": "channel credentials checked per-job"}

    # Explicit: BOC never gates readiness.
    checks["boc_booking"] = {"ok": True, "enabled": False, "readiness_dependency": False}

    return {"ok": overall, "role": "readiness", "service_role": role_name, "checks": checks}


def _redis_required_for_live() -> bool:
    from services.queues.config import redis_required

    return redis_required()


def _redis_check(*, required: bool) -> tuple[bool, dict[str, Any]]:
    from services.queues.config import redis_url

    configured = bool(redis_url())
    if not configured:
        detail = {"ok": not required, "configured": False, "required": required}
        return (not required), detail
    try:
        from services.job_queue import job_queue

        health = job_queue.health()
        ok = bool(health.get("ok"))
        return ok, {
            "ok": ok if required else True,
            "configured": True,
            "reachable": ok,
            "required": required,
            "backend": health.get("backend"),
            "error": health.get("error"),
        }
    except Exception as exc:
        return (not required), {
            "ok": not required,
            "configured": True,
            "reachable": False,
            "required": required,
            "error": type(exc).__name__,
        }


def _queue_persist_check() -> tuple[bool, dict[str, Any]]:
    try:
        from services.scale.queue_protocol import try_get_durable_queue

        q = try_get_durable_queue()
        if q is None:
            return False, {"ok": False, "backend": None}
        return True, {"ok": True, "backend": q.backend_name}
    except Exception as exc:
        return False, {"ok": False, "error": type(exc).__name__}


def _postgres_check(*, required: bool) -> tuple[bool, dict[str, Any]]:
    from db.session import database_url, whatsapp_db_configured

    configured = whatsapp_db_configured()
    if not configured:
        return (not required), {"ok": not required, "configured": False, "required": required}
    try:
        from sqlalchemy import text

        from db.session import get_engine

        with get_engine(require=True).connect() as conn:
            conn.execute(text("SELECT 1"))
        return True, {"ok": True, "configured": True, "url_scheme": (database_url() or "").split(":", 1)[0]}
    except Exception as exc:
        return False, {"ok": False, "configured": True, "error": type(exc).__name__, "required": required}


def _firestore_check() -> tuple[bool, dict[str, Any]]:
    try:
        from utils.utils import get_firestore_db

        ok = get_firestore_db() is not None
        return ok, {"ok": ok}
    except Exception as exc:
        return False, {"ok": False, "error": type(exc).__name__}
