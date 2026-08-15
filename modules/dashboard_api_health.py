"""Dashboard liveness/readiness endpoints (LOC split)."""

from __future__ import annotations

import contextvars
from pathlib import Path
from typing import Any

from modules.core import app

PERSISTENT_MAINTENANCE_DRAIN_FILE = "/var/lib/linasbot/meta-ha/maintenance"
_HA_INTERNAL_READINESS = contextvars.ContextVar("linas_ha_internal_readiness", default=False)


def _maintenance_entry_exists(path: Path) -> bool:
    try:
        path.lstat()
    except FileNotFoundError:
        return False
    except OSError:
        # An unreadable maintenance path is fail-closed, not permission to
        # return this node to the load balancer.
        return True
    return True


@app.get("/")
async def root() -> Any:
    return {"message": "Lina's Laser AI Bot is running!"}


@app.get("/api/health")
async def health() -> Any:
    """Lightweight liveness check - no dependency probes, returns immediately."""
    return {"ok": True, "role": "liveness"}


@app.get("/api/ready")
async def ready() -> Any:
    """
    Public readiness probe: required dependencies without exposing secret values.
    Returns boolean ok flags only (never secret contents).

    When LINAS_SERVICE_ROLE is set to a worker/ingress role, use role-specific checks.
    """
    import os

    from modules.api_security import is_production_env
    from services.scale.shutdown import shutdown_coordinator

    maintenance_paths = (
        Path((os.getenv("LINAS_MAINTENANCE_DRAIN_FILE") or "/run/linasbot-maintenance").strip()),
        Path(PERSISTENT_MAINTENANCE_DRAIN_FILE),
    )
    if not _HA_INTERNAL_READINESS.get() and any(_maintenance_entry_exists(path) for path in maintenance_paths):
        from fastapi.responses import JSONResponse

        return JSONResponse(
            status_code=503,
            content={"ok": False, "role": "readiness", "checks": {"maintenance": {"ok": False}}},
        )

    role = (os.getenv("LINAS_SERVICE_ROLE") or "api").strip().lower()
    if role not in {"", "api", "all"}:
        from fastapi.responses import JSONResponse

        from services.scale.readiness_roles import readiness_for_role

        payload = readiness_for_role(role)
        return JSONResponse(status_code=200 if payload.get("ok") else 503, content=payload)

    if shutdown_coordinator.draining:
        from fastapi.responses import JSONResponse

        return JSONResponse(
            status_code=503,
            content={"ok": False, "role": "readiness", "checks": {"drain": shutdown_coordinator.snapshot()}},
        )

    checks: dict[str, Any] = {}
    overall_ok = True

    # Auth signing secret: required in production (and ENVIRONMENT=test); never echo value
    try:
        from services.dashboard_session_service import get_auth_secret

        if is_production_env() or (os.getenv("ENVIRONMENT") or "").strip().lower() == "test":
            get_auth_secret()
            checks["dashboard_auth_secret"] = {"ok": True, "configured": True}
        else:
            configured = bool((os.getenv("DASHBOARD_AUTH_SECRET") or os.getenv("AUTH_SESSION_SECRET") or "").strip())
            checks["dashboard_auth_secret"] = {"ok": True, "configured": configured}
    except Exception as e:
        checks["dashboard_auth_secret"] = {"ok": False, "error": type(e).__name__}
        overall_ok = False

    openai_ok = bool((os.getenv("OPENAI_API_KEY") or "").strip())
    checks["openai_api_key"] = {"ok": openai_ok}
    if not openai_ok:
        overall_ok = False

    from services.meta_app_registry import get_meta_registry_readiness, meta_multi_app_registry_enabled
    from services.meta_messaging import get_meta_messaging_readiness, get_meta_messaging_settings

    meta_settings = get_meta_messaging_settings()
    if meta_multi_app_registry_enabled():
        meta_ok, meta_checks = get_meta_registry_readiness()
    else:
        meta_ok, meta_checks = get_meta_messaging_readiness(meta_settings)
    checks["meta_social_messaging"] = {
        "ok": meta_ok if meta_settings.enabled else True,
        "enabled": meta_settings.enabled,
        **meta_checks,
    }
    if meta_settings.enabled and not meta_ok:
        overall_ok = False

    # Product invariant: WhatsApp is never an inbound AI channel for this Meta
    # social integration. This readiness signal is intentionally configuration-free.
    checks["whatsapp_inbound_ai"] = {"ok": True, "enabled": False}

    # BOC / LinasLaser Agent booking — default OFF; healthy without token or booking IDs.
    from services.product_features import boc_booking_readiness

    boc_check = boc_booking_readiness()
    checks["boc_booking"] = boc_check
    if not boc_check.get("ok"):
        overall_ok = False

    # Meta Cloud credentials required when WhatsApp is enabled in production (Cloud-only).
    provider = (os.getenv("WHATSAPP_PROVIDER") or "meta").strip().lower() or "meta"
    if provider in ("cloud",):
        provider = "meta"
    wa_disabled = (os.getenv("WHATSAPP_DISABLED") or "").strip().lower() in ("1", "true", "yes", "on")
    token_ok = bool((os.getenv("WHATSAPP_API_TOKEN") or "").strip())
    pnid_ok = bool((os.getenv("WHATSAPP_PHONE_NUMBER_ID") or "").strip())
    cloud_ok = token_ok and pnid_ok
    if is_production_env() and not wa_disabled and provider in ("meta", "cloud"):
        checks["whatsapp_cloud_credentials"] = {
            "ok": cloud_ok,
            "configured": cloud_ok,
            "token_configured": token_ok,
            "phone_number_id_configured": pnid_ok,
            "provider": "meta",
        }
        if not cloud_ok:
            overall_ok = False
    else:
        checks["whatsapp_cloud_credentials"] = {
            "ok": True,
            "configured": cloud_ok,
            "required": False,
            "provider": provider,
            "whatsapp_disabled": wa_disabled,
        }

    try:
        from utils.utils import get_firestore_db

        db = get_firestore_db()
        fs_ok = db is not None
        checks["firestore"] = {"ok": fs_ok}
        if not fs_ok:
            overall_ok = False
    except Exception as e:
        checks["firestore"] = {"ok": False, "error": type(e).__name__}
        overall_ok = False

    try:
        from storage.persistent_storage import SETTINGS_DIR, ensure_dirs

        ensure_dirs()
        writable = os.access(str(SETTINGS_DIR), os.W_OK)
        checks["data_root_writable"] = {"ok": writable}
        if not writable:
            overall_ok = False
    except Exception as e:
        checks["data_root_writable"] = {"ok": False, "error": type(e).__name__}
        overall_ok = False

    # Queue / Redis readiness — hard-fail only when LINAS_REQUIRE_REDIS (or durable queues) is on.
    try:
        from services.job_queue import job_queue
        from services.queues.config import redis_required, redis_url

        required = redis_required()
        configured = bool(redis_url())
        health = job_queue.health()
        if required:
            queue_ok = configured and bool(health.get("ok")) and bool(health.get("production_ready"))
        else:
            # Opt-in Redis: unreachable REDIS_URL must not block API deploys / mobile login.
            queue_ok = True
        checks["job_queue"] = {
            "ok": queue_ok,
            "backend": health.get("backend"),
            "production_ready": bool(health.get("production_ready")),
            "redis_required": required,
            "redis_configured": configured,
            "redis_reachable": bool(health.get("ok")) if configured else None,
            "error": health.get("error"),
        }
        if not queue_ok:
            overall_ok = False
    except Exception as e:
        from services.queues.config import redis_required as _redis_required

        if _redis_required():
            checks["job_queue"] = {"ok": False, "error": type(e).__name__}
            overall_ok = False
        else:
            checks["job_queue"] = {
                "ok": True,
                "redis_required": False,
                "error": type(e).__name__,
                "note": "Redis optional; connection error ignored for readiness",
            }

    status = 200 if overall_ok else 503
    from fastapi.responses import JSONResponse

    return JSONResponse(
        status_code=status,
        content={"ok": overall_ok, "role": "readiness", "checks": checks},
    )


async def readiness_for_ha_verification() -> Any:
    """Run the real dependency readiness path only inside the one-shot verifier.

    This is intentionally not an HTTP route.  The ContextVar cannot be supplied
    by a request or proxy header, and the exact process flag is checked again in
    the isolated target helper before this function is called.
    """
    import os

    if os.getenv("LINAS_HA_VERIFY_ONLY") != "true":
        raise RuntimeError("HA internal readiness requires exact verification-only mode")
    token = _HA_INTERNAL_READINESS.set(True)
    try:
        return await ready()
    finally:
        _HA_INTERNAL_READINESS.reset(token)
