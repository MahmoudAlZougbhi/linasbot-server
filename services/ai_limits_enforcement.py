"""Helpers to enforce per-end-user AI image / context quotas at pipeline edges."""

from __future__ import annotations

from typing import Any

from services.ai_usage_limits import (
    CUSTOMER_IMAGE_LIMIT_MESSAGE,
    QuotaDecision,
    ai_usage_limits_service,
    count_non_empty_lines,
)
from services.token_metering import resolve_tenant_id


def _end_user_id(user_id: str, user_data: dict[str, Any] | None = None) -> str:
    if user_data:
        sid = user_data.get("social_sender_id") or user_data.get("phone_number")
        if sid:
            return str(sid)
    return str(user_id or "unknown")


def enforce_image_analysis_quota(
    *,
    user_id: str,
    user_data: dict[str, Any] | None = None,
    amount: int = 1,
    consume: bool = True,
) -> QuotaDecision:
    """
    Check (and optionally consume) image-analysis quota for one end-user.

    Logs an honest operator line when blocked. Does not raise.
    """
    tenant_id = resolve_tenant_id(user_data)
    end_user = _end_user_id(user_id, user_data)
    if consume:
        decision = ai_usage_limits_service.consume_images(tenant_id, end_user, amount=amount)
    else:
        decision = ai_usage_limits_service.check_image_quota(tenant_id, end_user, amount=amount)
    if not decision.allowed:
        print(
            f"[ai_limits] image_quota_blocked tenant={tenant_id} user={end_user[-8:]} "
            f"reason={decision.reason} used={decision.used} limit={decision.limit} period={decision.period}",
            flush=True,
        )
    return decision


def enforce_context_line_budget(
    *,
    user_id: str,
    user_data: dict[str, Any] | None = None,
    text: str,
    consume: bool = True,
) -> tuple[str, QuotaDecision]:
    """
    Truncate assembled knowledge/context text to the remaining line budget.

    Returns (possibly truncated text, decision). When remaining is 0, text is empty.
    """
    tenant_id = resolve_tenant_id(user_data)
    end_user = _end_user_id(user_id, user_data)
    lines = count_non_empty_lines(text)
    decision = ai_usage_limits_service.check_context_line_quota(tenant_id, end_user, amount=lines)
    allowed = int(decision.allowed_amount or 0)
    if allowed < lines:
        text = ai_usage_limits_service.truncate_text_to_line_budget(text, allowed)
        print(
            f"[ai_limits] context_lines_truncated tenant={tenant_id} user={end_user[-8:]} "
            f"requested={lines} allowed={allowed} reason={decision.reason}",
            flush=True,
        )
    if consume and allowed > 0:
        ai_usage_limits_service.consume_context_lines(tenant_id, end_user, amount=allowed)
    elif not decision.allowed:
        print(
            f"[ai_limits] context_lines_blocked tenant={tenant_id} user={end_user[-8:]} "
            f"reason={decision.reason} used={decision.used} limit={decision.limit}",
            flush=True,
        )
    return text, decision


def customer_image_limit_message(decision: QuotaDecision | None = None) -> str:
    if decision and decision.customer_message:
        return decision.customer_message
    return CUSTOMER_IMAGE_LIMIT_MESSAGE
