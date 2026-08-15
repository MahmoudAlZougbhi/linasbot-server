"""Helpers to enforce per-end-user AI quotas at pipeline edges."""

from __future__ import annotations

from typing import Any

from services.ai_limits_messages import (
    customer_photos_truncated_message,
    customer_voice_truncated_message,
    customer_words_truncated_message,
)
from services.ai_usage_limits import (
    CUSTOMER_IMAGE_LIMIT_MESSAGE,
    CUSTOMER_REPLY_LIMIT_MESSAGE,
    CUSTOMER_VOICE_LIMIT_MESSAGE,
    QuotaDecision,
    ai_usage_limits_service,
    count_non_empty_lines,
    count_words,
    minutes_from_seconds,
    truncate_text_to_words,
)
from services.token_metering import resolve_tenant_id


def _end_user_id(user_id: str, user_data: dict[str, Any] | None = None) -> str:
    if user_data:
        sid = user_data.get("social_sender_id") or user_data.get("phone_number")
        if sid:
            return str(sid)
    return str(user_id or "unknown")


def _lang(user_data: dict[str, Any] | None) -> str | None:
    if not user_data:
        return None
    return str(user_data.get("user_preferred_lang") or user_data.get("response_language") or "") or None


def _tenant_or_block(user_data: dict[str, Any] | None, *, end_user: str, kind: str) -> str | None:
    try:
        return resolve_tenant_id(user_data)
    except ValueError:
        print(
            f"[ai_limits] {kind}_blocked tenant=missing user={end_user[-8:]} reason=tenant_required",
            flush=True,
        )
        return None


def enforce_image_analysis_quota(
    *,
    user_id: str,
    user_data: dict[str, Any] | None = None,
    amount: int = 1,
    consume: bool = True,
) -> QuotaDecision:
    """Check (and optionally consume) photo-analysis quota for one end-user."""
    end_user = _end_user_id(user_id, user_data)
    tenant_id = _tenant_or_block(user_data, end_user=end_user, kind="image")
    lang = _lang(user_data)
    if tenant_id is None:
        return QuotaDecision(
            allowed=False,
            reason="tenant_required",
            allowed_amount=0,
            customer_message=CUSTOMER_IMAGE_LIMIT_MESSAGE,
        )
    requested = max(0, int(amount))
    settings = ai_usage_limits_service.get_settings(tenant_id)
    per_msg = int(settings.photos_per_message)
    capped = min(requested, per_msg)
    if consume:
        decision = ai_usage_limits_service.consume_images(tenant_id, end_user, amount=capped, lang=lang)
    else:
        decision = ai_usage_limits_service.check_image_quota(tenant_id, end_user, amount=capped, lang=lang)
    if requested > per_msg and decision.allowed:
        decision.truncated = True
        notice = customer_photos_truncated_message(photo_limit=per_msg, lang=lang)
        decision.customer_message = notice
        decision.reason = "photos_per_message_truncated"
    if not decision.allowed:
        print(
            f"[ai_limits] image_quota_blocked tenant={tenant_id} user={end_user[-8:]} "
            f"reason={decision.reason} used={decision.used} limit={decision.limit} period={decision.period}",
            flush=True,
        )
    return decision


def enforce_text_reply_quota(
    *,
    user_id: str,
    user_data: dict[str, Any] | None = None,
    consume: bool = True,
) -> QuotaDecision:
    """One AI reply toward this customer's day/week/month reply cap."""
    end_user = _end_user_id(user_id, user_data)
    tenant_id = _tenant_or_block(user_data, end_user=end_user, kind="reply")
    lang = _lang(user_data)
    if tenant_id is None:
        return QuotaDecision(
            allowed=False,
            reason="tenant_required",
            allowed_amount=0,
            customer_message=CUSTOMER_REPLY_LIMIT_MESSAGE,
        )
    if consume:
        decision = ai_usage_limits_service.consume_replies(tenant_id, end_user, amount=1, lang=lang)
    else:
        decision = ai_usage_limits_service.check_reply_quota(tenant_id, end_user, amount=1, lang=lang)
    if not decision.allowed:
        print(
            f"[ai_limits] reply_quota_blocked tenant={tenant_id} user={end_user[-8:]} "
            f"reason={decision.reason} used={decision.used} limit={decision.limit} period={decision.period}",
            flush=True,
        )
    return decision


def apply_inbound_word_limit(
    *,
    user_id: str,
    user_data: dict[str, Any] | None = None,
    text: str,
) -> tuple[str, str | None]:
    """Read only the first N words of this inbound message. Returns (text, notice)."""
    end_user = _end_user_id(user_id, user_data)
    try:
        tenant_id = resolve_tenant_id(user_data)
    except ValueError:
        return str(text or ""), None
    settings = ai_usage_limits_service.get_settings(tenant_id)
    limit = int(settings.text_words_per_message)
    words = count_words(text)
    if words <= limit:
        return str(text or ""), None
    clipped = truncate_text_to_words(str(text or ""), limit)
    notice = customer_words_truncated_message(word_limit=limit, lang=_lang(user_data))
    print(
        f"[ai_limits] words_truncated tenant={tenant_id} user={end_user[-8:]} requested={words} allowed={limit}",
        flush=True,
    )
    return clipped, notice


def enforce_voice_minutes_quota(
    *,
    user_id: str,
    user_data: dict[str, Any] | None = None,
    duration_seconds: float,
    consume: bool = True,
) -> QuotaDecision:
    """Cap voice minutes per message and per customer day/week/month."""
    end_user = _end_user_id(user_id, user_data)
    tenant_id = _tenant_or_block(user_data, end_user=end_user, kind="voice")
    lang = _lang(user_data)
    if tenant_id is None:
        return QuotaDecision(
            allowed=False,
            reason="tenant_required",
            allowed_amount=0,
            customer_message=CUSTOMER_VOICE_LIMIT_MESSAGE,
        )
    requested = minutes_from_seconds(duration_seconds)
    settings = ai_usage_limits_service.get_settings(tenant_id)
    per_msg = int(settings.voice_minutes_per_message)
    if consume:
        decision = ai_usage_limits_service.consume_voice_minutes(tenant_id, end_user, amount=requested, lang=lang)
    else:
        decision = ai_usage_limits_service.check_voice_quota(tenant_id, end_user, amount=requested, lang=lang)
    if requested > per_msg and decision.allowed:
        decision.truncated = True
        notice = customer_voice_truncated_message(minute_limit=decision.allowed_amount, lang=lang)
        decision.customer_message = notice
        decision.reason = "voice_per_message_truncated"
    if not decision.allowed:
        print(
            f"[ai_limits] voice_quota_blocked tenant={tenant_id} user={end_user[-8:]} "
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
    """Kept for existing callers/tests. Text replies now use reply + word caps."""
    end_user = _end_user_id(user_id, user_data)
    tenant_id = _tenant_or_block(user_data, end_user=end_user, kind="context_lines")
    if tenant_id is None:
        return "", QuotaDecision(allowed=False, reason="tenant_required", allowed_amount=0)
    lines = count_non_empty_lines(text)
    decision = ai_usage_limits_service.check_context_line_quota(tenant_id, end_user, amount=lines)
    allowed = int(decision.allowed_amount or 0)
    if allowed < lines:
        text = ai_usage_limits_service.truncate_text_to_line_budget(text, allowed)
    if consume and allowed > 0:
        ai_usage_limits_service.consume_context_lines(tenant_id, end_user, amount=allowed)
    return text, decision


def customer_image_limit_message(decision: QuotaDecision | None = None) -> str:
    if decision and decision.customer_message:
        return decision.customer_message
    return CUSTOMER_IMAGE_LIMIT_MESSAGE


def customer_reply_limit_message(decision: QuotaDecision | None = None) -> str:
    if decision and decision.customer_message:
        return decision.customer_message
    return CUSTOMER_REPLY_LIMIT_MESSAGE


def customer_voice_limit_message(decision: QuotaDecision | None = None) -> str:
    if decision and decision.customer_message:
        return decision.customer_message
    return CUSTOMER_VOICE_LIMIT_MESSAGE
