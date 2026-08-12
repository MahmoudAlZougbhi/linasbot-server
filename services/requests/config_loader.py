"""Load published Requests & Appointments CM configuration."""

from __future__ import annotations

from typing import Any

from services.requests.constants import CM_SECTION_REQUESTS_APPOINTMENTS


def load_published_requests_config(tenant_id: str | None) -> dict[str, Any] | None:
    """Return published section payload, or None if missing.

    Does not invent defaults that activate capture. Safe default: inactive.
    """
    if not tenant_id or not str(tenant_id).strip():
        return None
    try:
        from services.cm.version_store import PublishedVersionError, load_published_content
    except Exception:
        return None
    try:
        _pointer, sections = load_published_content(tenant_id)
    except PublishedVersionError:
        return None
    except Exception:
        return None
    payload = sections.get(CM_SECTION_REQUESTS_APPOINTMENTS)
    if not isinstance(payload, dict):
        return None
    return payload


def requests_capture_active(tenant_id: str | None) -> bool:
    """True only when published config explicitly enables the module + at least one type."""
    cfg = load_published_requests_config(tenant_id)
    if not cfg:
        return False
    if not bool(cfg.get("module_enabled")):
        return False
    enabled = cfg.get("enabled_types") or []
    if not isinstance(enabled, list) or not enabled:
        return False
    return True


def published_configuration_version(tenant_id: str | None) -> str | None:
    try:
        from services.cm.version_store import read_published_pointer
    except Exception:
        return None
    pointer = read_published_pointer(tenant_id)
    if pointer is None:
        return None
    vid = getattr(pointer, "content_version_id", None)
    return str(vid) if vid else None
