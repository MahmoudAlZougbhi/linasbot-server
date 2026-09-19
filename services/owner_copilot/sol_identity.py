"""Load published Sol identity from portal CM. No hardcoded SYSTEM_* fallback."""

from __future__ import annotations

from typing import Any

from services.owner_copilot.sol_runtime_stub import SOL_RUNTIME_STUB

_IDENTITY_KEYS = (
    "assistant_name",
    "ai_role",
    "tone",
    "reply_style",
    "identity_summary",
    "advanced_instructions",
)


def _published_sol_basics(tenant_id: str) -> dict[str, Any]:
    tid = (tenant_id or "").strip()
    if not tid:
        return {}
    try:
        from services.ai_setup.version_store import load_published_content

        _pointer, sections = load_published_content(tid)
    except Exception:
        return {}
    raw = sections.get("sol_basics")
    return dict(raw) if isinstance(raw, dict) else {}


def sol_basics_configured(payload: dict[str, Any] | None) -> bool:
    if not isinstance(payload, dict):
        return False
    for key in ("assistant_name", "advanced_instructions", "identity_summary", "ai_role"):
        if str(payload.get(key) or "").strip():
            return True
    return False


def load_sol_identity(tenant_id: str) -> dict[str, Any]:
    payload = _published_sol_basics(tenant_id)
    return {"configured": sol_basics_configured(payload), "payload": payload}


def format_sol_identity_block(payload: dict[str, Any]) -> str:
    lines = ["IDENTITY/STYLE (published portal CM — sol_basics):"]
    name = str(payload.get("assistant_name") or "").strip()
    role = str(payload.get("ai_role") or "").strip()
    if name:
        lines.append(f"Name: {name}")
    if role:
        lines.append(f"Role: {role}")
    for key in ("tone", "identity_summary", "reply_style", "advanced_instructions"):
        value = str(payload.get(key) or "").strip()
        if value:
            label = key.replace("_", " ").title()
            lines.append(f"{label}:\n{value}")
    do_list = [str(x).strip() for x in (payload.get("do_list") or []) if str(x).strip()]
    dont_list = [str(x).strip() for x in (payload.get("dont_list") or []) if str(x).strip()]
    if do_list:
        lines.append("Do:\n- " + "\n- ".join(do_list[:16]))
    if dont_list:
        lines.append("Don't:\n- " + "\n- ".join(dont_list[:16]))
    return "\n\n".join(lines).strip()


def compose_sol_system(payload: dict[str, Any]) -> str:
    """Exactly one persona block: stub + published identity. Dual hardcoded novels are gone."""
    identity = format_sol_identity_block(payload)
    return f"{SOL_RUNTIME_STUB}\n\n{identity}".strip()


def identity_field_count(payload: dict[str, Any]) -> int:
    return sum(1 for key in _IDENTITY_KEYS if str(payload.get(key) or "").strip())
