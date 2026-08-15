"""Web Chat AI eligibility and inbound message processing."""

from __future__ import annotations

import asyncio
from typing import Any

from services.web_chat.constants import CHANNEL_ID, CUSTOMER_REPLY_CHANNEL, SOURCE_CHANNEL_WEB_CHAT, USER_ID_PREFIX
from services.web_chat.store import WebChatStore, WebChatVisitorSession, WebChatWidgetConfig, web_chat_store


class WebChatError(Exception):
    def __init__(self, code: str, message: str, *, status_code: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


def compose_web_user_id(visitor_session_id: str) -> str:
    sid = (visitor_session_id or "").strip()
    return f"{USER_ID_PREFIX}{sid}"


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
        from services.credit_ai_gate import ai_generation_blocked

        if ai_generation_blocked(tenant_id):
            return False, "insufficient_credits"
    except Exception:
        return False, "credits_unavailable"
    return True, None


def default_greeting(language: str | None = None, widget: WebChatWidgetConfig | None = None) -> str:
    if widget is not None:
        identity = widget.appearance.get("identity") if isinstance(widget.appearance, dict) else {}
        custom = str((identity or {}).get("welcome_message") or "").strip()
        if custom:
            return custom
    lang = (language or "en").strip().lower()[:2]
    messages = {
        "ar": "مرحباً! كيف بقدر ساعدك اليوم؟",
        "fr": "Bonjour ! Comment puis-je vous aider aujourd'hui ?",
        "en": "Hi! How can I help you today?",
    }
    return messages.get(lang, messages["en"])


async def process_web_chat_message(
    *,
    widget: WebChatWidgetConfig,
    visitor_session: WebChatVisitorSession,
    user_text: str,
    store: WebChatStore | None = None,
) -> str:
    """Run Customer Reply V2 for a website visitor turn; persist to Firestore + live chat index."""
    tid = widget.tenant_id
    eligible, reason = evaluate_web_ai_eligibility(tid, widget)
    if not eligible:
        blocked = {
            "web_plan_denied": "Web Chat is not included on your plan. Upgrade to enable website chat.",
            "insufficient_credits": "AI replies are paused until credits are available.",
            "published_cm_missing": "Publish your AI setup before enabling website chat.",
            "widget_disabled": "Website chat is turned off.",
            "site_url_missing": "Add your website URL in Integrations first.",
        }
        raise WebChatError(
            reason or "not_eligible",
            blocked.get(reason or "", "Website chat is not available right now."),
            status_code=403 if reason in {"web_plan_denied", "widget_disabled"} else 409,
        )

    text = (user_text or "").strip()
    if not text:
        raise WebChatError("empty_message", "Message cannot be empty.")

    visitor_id = visitor_session.id
    user_id = compose_web_user_id(visitor_id)
    conversation_id = f"web:{tid}:{visitor_id}"

    from services.ai_limits_enforcement import (
        apply_inbound_word_limit,
        customer_reply_limit_message,
        enforce_text_reply_quota,
    )

    limit_user: dict[str, Any] = {
        "tenant_id": tid,
        "channel": CHANNEL_ID,
        "user_preferred_lang": "",
        "phone_number": f"room:{user_id}",
    }
    text, word_notice = apply_inbound_word_limit(user_id=user_id, user_data=limit_user, text=text)
    reply_precheck = enforce_text_reply_quota(user_id=user_id, user_data=limit_user, consume=False)
    if not reply_precheck.allowed:
        raise WebChatError("ai_reply_limit", customer_reply_limit_message(reply_precheck), status_code=429)

    reservation_id: str | None = None
    try:
        from services.credit_ledger_service import credit_ledger_service

        reservation_id = credit_ledger_service.reserve(
            tenant_id=tid,
            user_id=None,
            credits=1,
            operation_type="web_customer_reply",
            request_id=f"web:{visitor_id}:{int(asyncio.get_event_loop().time() * 1000)}",
        )
    except PermissionError as exc:
        raise WebChatError(
            "insufficient_credits", "AI replies are paused until credits are available.", status_code=402
        ) from exc

    reply_text = ""
    try:
        from services.cm.language_policy import detect_and_resolve_customer_languages
        from services.customer_reply_v2.orchestrator import run_customer_reply_v2_dm

        _lang = detect_and_resolve_customer_languages(
            tenant_id=tid,
            message=text,
            conversation_id=conversation_id,
        )
        outcome = await run_customer_reply_v2_dm(
            tenant_id=tid,
            message=text,
            detected_language=_lang["detected_language"],
            response_language=_lang["response_language"],
            channel=CUSTOMER_REPLY_CHANNEL,
            asset_id=widget.widget_key,
            provider_sender_id=visitor_id,
            provider_display_name="Website visitor",
            user_id=user_id,
            conversation_id=conversation_id,
        )
        reply_text = str(
            getattr(outcome, "reply", None) or getattr(outcome, "answer", None) or getattr(outcome, "text", None) or ""
        ).strip()
        if not reply_text and isinstance(outcome, dict):
            reply_text = str(outcome.get("reply") or outcome.get("answer") or outcome.get("text") or "").strip()
        reason = str(getattr(outcome, "reason", "") or "")
        if reason.endswith("_limit") or reason == "ai_reply_limit":
            if reservation_id:
                _release_reservation(tid, reservation_id)
                reservation_id = None
            raise WebChatError("ai_reply_limit", customer_reply_limit_message(reply_precheck), status_code=429)
        if word_notice and reply_text:
            reply_text = f"{word_notice}\n\n{reply_text}"
    except WebChatError:
        if reservation_id:
            _release_reservation(tid, reservation_id)
        raise
    except Exception as exc:
        if reservation_id:
            _release_reservation(tid, reservation_id)
        raise WebChatError("ai_failed", "Could not generate a reply right now.", status_code=503) from exc

    if not reply_text:
        if reservation_id:
            _release_reservation(tid, reservation_id)
        raise WebChatError("empty_reply", "Could not generate a reply right now.", status_code=503)

    if reservation_id:
        try:
            from services.credit_ledger_service import credit_ledger_service

            credit_ledger_service.capture(
                tenant_id=tid,
                reservation_id=reservation_id,
                provider_cost_usd=None,
                model_provider=None,
            )
        except Exception:
            _release_reservation(tid, reservation_id)

    await _persist_web_turn(
        tenant_id=tid,
        user_id=user_id,
        conversation_id=conversation_id,
        visitor_id=visitor_id,
        user_text=text,
        reply_text=reply_text,
        widget=widget,
    )

    active_store = store or web_chat_store
    active_store.append_turn(visitor_id, user_text=text, assistant_text=reply_text)

    try:
        import time

        from services.web_chat.followup import maybe_schedule_web_followup_after_ai_reply

        maybe_schedule_web_followup_after_ai_reply(
            tenant_id=tid,
            user_id=user_id,
            visitor_session_id=visitor_id,
            conversation_id=conversation_id,
            widget_key=widget.widget_key,
            trigger_ref=f"web:{visitor_id}:{int(time.time())}",
        )
    except Exception:
        pass

    return reply_text


def _release_reservation(tenant_id: str, reservation_id: str | None) -> None:
    if not reservation_id:
        return
    try:
        from services.credit_ledger_service import credit_ledger_service

        credit_ledger_service.release(tenant_id=tenant_id, reservation_id=reservation_id)
    except Exception:
        pass


async def _persist_web_turn(
    *,
    tenant_id: str,
    user_id: str,
    conversation_id: str,
    visitor_id: str,
    user_text: str,
    reply_text: str,
    widget: WebChatWidgetConfig,
) -> None:

    import config
    from utils.utils import save_conversation_message_to_firestore

    if user_id not in config.user_data_whatsapp:
        config.user_data_whatsapp[user_id] = {
            "tenant_id": tenant_id,
            "channel": CHANNEL_ID,
            "social_sender_id": visitor_id,
            "phone_number": f"room:{user_id}",
            "user_preferred_lang": "",
        }
    user_data = config.user_data_whatsapp[user_id]
    user_data["tenant_id"] = tenant_id
    user_data["channel"] = CHANNEL_ID

    await save_conversation_message_to_firestore(
        user_id,
        "user",
        user_text,
        conversation_id=conversation_id,
        metadata={"channel": CHANNEL_ID, "source": SOURCE_CHANNEL_WEB_CHAT, "widget_key": widget.widget_key},
    )
    await save_conversation_message_to_firestore(
        user_id,
        "assistant",
        reply_text,
        conversation_id=conversation_id,
        metadata={
            "channel": CHANNEL_ID,
            "source": SOURCE_CHANNEL_WEB_CHAT,
            "widget_key": widget.widget_key,
            "handled_by": "ai",
        },
    )

    try:
        from services.interaction_flow_logger import is_flow_logging_enabled, log_interaction

        if is_flow_logging_enabled():
            log_interaction(
                user_id=user_id,
                user_message=user_text,
                bot_to_user=reply_text,
                source="web_chat",
                conversation_id=conversation_id,
            )
    except Exception:
        pass

    try:
        from services.whatsapp_cloud.observability import record_analytics_channel_usage

        record_analytics_channel_usage(
            tenant_id=tenant_id,
            connection_id=f"web:{widget.widget_key}",
            conversation_id=conversation_id,
            provider_message_id="web_chat",
            source="web_chat",
        )
    except Exception:
        pass
