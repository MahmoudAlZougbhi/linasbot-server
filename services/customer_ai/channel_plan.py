"""Live channel plan gates for Brain turns. Same SoT as Meta / WhatsApp / web."""

from __future__ import annotations

_DENIED = frozenset(
    {
        "WHATSAPP_PLAN_DENIED",
        "WEB_PLAN_DENIED",
        "TIKTOK_PLAN_DENIED",
        "COMMENT_AUTOMATION_DENIED",
    }
)


def denied_code(exc: BaseException) -> str | None:
    code = str(getattr(exc, "code", "") or "")
    return code if code in _DENIED else None


def assert_channel_plan_allowed(tenant_id: str, channel: str) -> None:
    name = (channel or "").strip().lower()
    if "whatsapp" in name:
        from services.membership.whatsapp_gate import assert_whatsapp_plan_allowed

        assert_whatsapp_plan_allowed(tenant_id)
        return
    if name.startswith("web") or name in {"website", "widget"}:
        from services.membership.web_gate import assert_web_plan_allowed

        assert_web_plan_allowed(tenant_id)
        return
    if "tiktok" in name:
        from services.tiktok_business.entitlement import assert_tiktok_plan_allowed

        assert_tiktok_plan_allowed(tenant_id)
