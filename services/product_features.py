"""Product surface flags: which legacy modules are disabled for ALL tenants.

Wave 1 SaaS conversion — disable/hide, do not delete legacy code.
These modules stay in the repo but must not appear in navigation or accept
normal authenticated API traffic.
"""

from __future__ import annotations

from typing import Final

# Human-readable product modules removed from the current SaaS product surface.
# Live Chat + Interaction Logs remain enabled (restored by product request).
DISABLED_PRODUCT_MODULES: Final[tuple[str, ...]] = (
    "testing_lab",
    "smart_messaging",
    "create_post",
    "clinic_calendar",
)

# API path prefixes that belong to disabled modules (all tenants, including linas).
# NOTE: "/api/test" alone does NOT match hyphenated lab routes ("/api/test-message").
# Those are listed explicitly and also matched via startswith("/api/test-") in is_disabled_api_path.
DISABLED_API_PREFIXES: Final[tuple[str, ...]] = (
    "/api/test",
    "/api/test-message",
    "/api/test-image",
    "/api/test-voice",
    "/api/test-voice-text",
    "/api/test-voice-upload",
    "/api/test-image-upload",
    "/api/switch-provider",
    "/api/debug",
    "/api/smart-messaging",
    "/api/analytics",
    "/api/meta/social-posts",
    "/api/settings/clinic",
)

DISABLED_PRODUCT_MESSAGE: Final[str] = (
    "This module is disabled in the current Linas AI product. Use AI Setup and Meta connections instead."
)

# Dashboard frontend routes that must redirect away (kept for deep-link safety).
DISABLED_FRONTEND_ROUTES: Final[tuple[str, ...]] = (
    "/testing",
    "/api-debug",
    "/smart-messaging",
    "/social-posts",
    "/analytics",
)


def _normalize_path(path: str) -> str:
    if not path:
        return "/"
    p = path if path.startswith("/") else f"/{path}"
    if len(p) > 1 and p.endswith("/"):
        return p.rstrip("/")
    return p


def is_disabled_api_path(path: str) -> bool:
    """Return True when ``path`` targets a product module that is disabled for everyone."""
    p = _normalize_path(path)
    if p == "/api/stats":
        return True
    # Hyphenated Testing Lab routes historically bypassed the "/api/test" prefix check.
    if p.startswith("/api/test-"):
        return True
    for prefix in DISABLED_API_PREFIXES:
        if p == prefix or p.startswith(f"{prefix}/"):
            return True
    return False


# Disabled booking/CRM tool names — never offered to the model when BOC booking is OFF.
LEGACY_BOOKING_TOOL_NAMES: frozenset[str] = frozenset(
    {
        "update_customer_profile",
        "submit_booking_intent",
        "create_appointment",
        "update_appointment_date",
        "update_paused_appointment",
        "edit_appointment",
        "resume_appointment",
        "sync_appointment_agreed_price",
        "send_appointment_reminders",
        "check_next_appointment",
        "get_appointment_details",
        "check_appointment_payment",
        "get_customer_sessions",
        "get_sessions_count_by_phone",
        "move_client_branch",
        "get_customer_by_phone",
        "check_customer_gender",
        "create_customer",
        "add_customer_note",
        "get_all_customers",
        "get_clients_without_today",
        "get_missed_appointments",
        "get_branches",
        "get_services",
        "get_machines",
        "get_available_slots",
        "get_body_parts",
        "get_service_data",
        "get_clinic_hours",
        "get_paused_appointments_between_dates",
        "get_pricing_details",
        "pause_appointment",
        "add_appointment_discount",
    }
)

# Single runtime gate for BOC / LinasLaser Agent booking. Default OFF — zero network when disabled.
# See docs/requests/BOC_FUTURE_INTEGRATION.md. Do not enable in production without owner approval.
BOC_BOOKING_ENABLED_ENV: Final[str] = "LINASLASER_BOC_BOOKING_ENABLED"
BOC_BOOKING_DISABLED_CODE: Final[str] = "boc_booking_disabled"


def _env_flag_true(name: str, *, default: str = "false") -> bool:
    import os

    return (os.getenv(name) or default).strip().lower() in ("1", "true", "yes", "on")


def boc_booking_enabled() -> bool:
    """True only when LINASLASER_BOC_BOOKING_ENABLED is explicitly on (default: off)."""
    return _env_flag_true(BOC_BOOKING_ENABLED_ENV, default="false")


def legacy_booking_tools_disabled() -> bool:
    """Booking/CRM tools are withheld from the model unless BOC booking is explicitly enabled."""
    return not boc_booking_enabled()


def boc_appointment_jobs_allowed() -> bool:
    """Appointment-scheduler / BOC populate jobs may start only when the gate is on."""
    return boc_booking_enabled()


def boc_disabled_response(*, operation: str = "request") -> dict:
    """Honest refusal payload — no alternate provider and no network attempt."""
    return {
        "success": False,
        "error": BOC_BOOKING_DISABLED_CODE,
        "boc_booking_enabled": False,
        "message": (
            "BOC / LinasLaser Agent booking is disabled "
            f"({BOC_BOOKING_ENABLED_ENV} is not true). "
            f"No network call was made for {operation}."
        ),
    }


def boc_job_skipped_response(*, operation: str) -> dict:
    """Explicit skip for BOC appointment jobs when the gate is OFF (not a silent no-op)."""
    out = boc_disabled_response(operation=operation)
    out["skipped"] = True
    out["job_started"] = False
    out["total_appointments"] = 0
    out["total_messages"] = 0
    return out


def boc_booking_readiness() -> dict:
    """
    Readiness fragment for GET /api/ready.

    When OFF: healthy without token, base URL, or booking IDs.
    When ON: requires configured base URL + token (values never returned).
    """
    import os

    enabled = boc_booking_enabled()
    if not enabled:
        return {
            "ok": True,
            "enabled": False,
            "token_required": False,
            "booking_ids_required": False,
            "jobs_allowed": False,
        }

    base = (
        (os.getenv("EXTERNAL_API_BASE_URL") or "").strip()
        or (os.getenv("LINASLASER_API_BASE_URL") or "").strip()
    )
    token = (
        (os.getenv("EXTERNAL_API_TOKEN") or "").strip()
        or (os.getenv("LINASLASER_API_TOKEN") or "").strip()
    )
    configured = bool(base) and bool(token)
    return {
        "ok": configured,
        "enabled": True,
        "token_required": True,
        "booking_ids_required": True,
        "jobs_allowed": True,
        "base_url_configured": bool(base),
        "token_configured": bool(token),
    }
