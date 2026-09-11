"""Web Chat AI eligibility. Processor stays under the file-size cap."""

from __future__ import annotations

from services.web_chat.store import WebChatWidgetConfig


def evaluate_web_ai_eligibility(tenant_id: str, widget: WebChatWidgetConfig) -> tuple[bool, str | None]:
    if not widget.enabled:
        return False, "widget_disabled"
    if not widget.site_url.strip():
        return False, "site_url_missing"
    try:
        from services.membership.web_gate import WebPlanDenied, assert_web_plan_allowed

        assert_web_plan_allowed(tenant_id)
    except WebPlanDenied:
        return False, "web_plan_denied"
    except Exception:
        return False, "plan_check_failed"
    try:
        from services.cm.version_store import load_published_content

        pointer, _sections = load_published_content(tenant_id)
        if not pointer or not getattr(pointer, "content_version_id", None):
            return False, "published_cm_missing"
    except Exception:
        return False, "published_cm_unavailable"
    try:
        from services.membership.generative_gate import generative_block_reason

        reason = generative_block_reason(tenant_id)
        if reason:
            return False, reason
    except Exception:
        return False, "credits_unavailable"
    return True, None
