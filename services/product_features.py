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
DISABLED_API_PREFIXES: Final[tuple[str, ...]] = (
    "/api/test",
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
    for prefix in DISABLED_API_PREFIXES:
        if p == prefix or p.startswith(f"{prefix}/"):
            return True
    return False


# Disabled booking/CRM tool names — never offered to the model (all tenants / channels).
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
    }
)


def legacy_booking_tools_disabled() -> bool:
    """Booking/CRM tools are disabled for the current SaaS product (all tenants)."""
    return True
