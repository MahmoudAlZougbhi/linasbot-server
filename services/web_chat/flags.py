"""Server-side rollout controls for Website Chat.

All controls default OFF. Client cannot enable them.

Full Web Chat redesign is deferred until after Meta App Review.
"""

from __future__ import annotations

import os
from typing import Any

PUBLIC_AVAILABILITY_ENV = "WEB_CHAT_PUBLIC_AVAILABILITY"


def _truthy(name: str, default: str = "false") -> bool:
    return (os.getenv(name) or default).strip().lower() in {"1", "true", "yes", "on"}


def web_chat_public_availability_enabled() -> bool:
    """Central Phase 2 public switch for visitor-facing Website Chat (default OFF)."""
    return _truthy(PUBLIC_AVAILABILITY_ENV)


def web_chat_containment_active() -> bool:
    """True when visitor Web Chat and web Smart Follow-Up must stay closed."""
    return not web_chat_public_availability_enabled()


def assert_widget_operational(widget: Any) -> None:
    """Enforce widget.enabled; missing/disabled defaults closed."""
    if widget is None or not bool(getattr(widget, "enabled", False)):
        raise ValueError("WIDGET_DISABLED")


def flags_snapshot() -> dict[str, object]:
    return {
        PUBLIC_AVAILABILITY_ENV: web_chat_public_availability_enabled(),
        "web_chat_containment_active": web_chat_containment_active(),
        "meta_app_review_note": "Full Web Chat redesign deferred until after Meta App Review.",
    }


def get_web_chat_ha_readiness() -> tuple[bool, dict[str, Any]]:
    """Fail-closed readiness when PostgreSQL is configured for Website Chat HA."""
    from sqlalchemy import inspect as sa_inspect
    from sqlalchemy import text

    from db.session import get_engine, whatsapp_db_configured
    from services.web_chat.pg_models import WEB_CHAT_HA_TABLES

    checks: dict[str, Any] = {
        "postgres_configured": whatsapp_db_configured(),
        "postgres_reachable": False,
        "schema_present": False,
        "tables_missing": [],
        "required": whatsapp_db_configured(),
    }
    if not whatsapp_db_configured():
        return True, {**checks, "ok": True}

    try:
        engine = get_engine(require=True)
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        checks["postgres_reachable"] = True
        present = set(sa_inspect(engine).get_table_names())
        missing = [table for table in WEB_CHAT_HA_TABLES if table not in present]
        checks["tables_missing"] = missing
        checks["schema_present"] = not missing
        ok = bool(checks["postgres_reachable"] and checks["schema_present"])
        return ok, {**checks, "ok": ok}
    except Exception as exc:
        return False, {**checks, "ok": False, "error": type(exc).__name__}
