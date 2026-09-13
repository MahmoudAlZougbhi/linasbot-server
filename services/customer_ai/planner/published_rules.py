"""Load published Requests rules for the live Customer Brain (tenant-scoped)."""

from __future__ import annotations

from typing import Any

from services.cm.request_rules import format_request_rules_for_ai, sanitize_requests_appointments_payload
from services.cm.version_store import PublishedVersionError, load_published_content

_TYPE_TO_TASK = {
    "APPOINTMENT": "service_request",
    "ORDER": "product_request",
    "HUMAN": "human_request",
}


def _payload(tenant_id: str) -> dict[str, Any]:
    tid = (tenant_id or "").strip()
    if not tid:
        return {}
    try:
        _pointer, sections = load_published_content(tid)
    except PublishedVersionError:
        return {}
    raw = sections.get("requests_appointments") if isinstance(sections, dict) else None
    if not isinstance(raw, dict):
        return {}
    cleaned = sanitize_requests_appointments_payload(raw)
    return cleaned if isinstance(cleaned, dict) else {}


def enabled_request_types(tenant_id: str) -> set[str]:
    payload = _payload(tenant_id)
    raw_types = payload.get("enabled_types")
    types = raw_types if isinstance(raw_types, list) else []
    return {str(item).strip().upper() for item in types if str(item).strip()}


def request_rules_prompt_block(tenant_id: str) -> str:
    payload = _payload(tenant_id)
    if not payload:
        return ""
    return format_request_rules_for_ai(payload)


def request_rule_notes(tenant_id: str) -> list[str]:
    block = request_rules_prompt_block(tenant_id)
    return [block] if block else []


def task_types_for_enabled_rules(tenant_id: str) -> set[str]:
    return {_TYPE_TO_TASK[code] for code in enabled_request_types(tenant_id) if code in _TYPE_TO_TASK}


def allowed_action_task_types(tenant_id: str) -> set[str] | None:
    """None = no published Requests module, so do not invent a filter.

    A published module is authoritative: only enabled APPOINTMENT/ORDER/HUMAN
    tasks may start. Empty enabled_types means no request actions.
    """
    payload = _payload(tenant_id)
    if not payload:
        return None
    if payload.get("module_enabled") is False:
        return set()
    return task_types_for_enabled_rules(tenant_id)
