"""Web Chat V2 reply generation (split from processor for file-size cap)."""

from __future__ import annotations

from typing import Any

from services.web_chat.constants import CUSTOMER_REPLY_CHANNEL
from services.web_chat.credit_fsm import WebChatCreditHandle
from services.web_chat.operation_fence import fenced_failure_release
from services.web_chat.store import WebChatWidgetConfig


async def generate_web_chat_reply_text(
    *,
    tid: str,
    text: str,
    conversation_id: str,
    widget: WebChatWidgetConfig,
    visitor_id: str,
    user_id: str,
    word_notice: str | None,
    reply_precheck: Any,
    credit: WebChatCreditHandle,
    runtime: Any,
    inbound_media: dict[str, Any] | None = None,
    attachment_types: list[str] | None = None,
) -> str:
    from services.ai_limits_enforcement import customer_reply_limit_message
    from services.cm.language_policy import detect_and_resolve_customer_languages
    from services.customer_reply_v2.orchestrator import run_customer_reply_v2_dm
    from services.web_chat.operation_heartbeat import OperationLeaseHeartbeat
    from services.web_chat.processor import WebChatError

    reply_text = ""
    heartbeat = OperationLeaseHeartbeat(runtime)
    await heartbeat.start()
    try:
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
            inbound_media=inbound_media,
            attachment_types=attachment_types,
        )
        if heartbeat.lost_lease:
            fenced_failure_release(runtime, credit)
            raise WebChatError("operation_in_progress", "Operation lease lost during AI.", status_code=409)
        reply_text = str(
            getattr(outcome, "reply", None) or getattr(outcome, "answer", None) or getattr(outcome, "text", None) or ""
        ).strip()
        if not reply_text and isinstance(outcome, dict):
            reply_text = str(outcome.get("reply") or outcome.get("answer") or outcome.get("text") or "").strip()
        reason = str(getattr(outcome, "reason", "") or "")
        if reason.endswith("_limit") or reason == "ai_reply_limit":
            fenced_failure_release(runtime, credit)
            raise WebChatError("ai_reply_limit", customer_reply_limit_message(reply_precheck), status_code=429)
        if word_notice and reply_text:
            reply_text = f"{word_notice}\n\n{reply_text}"
    except WebChatError:
        fenced_failure_release(runtime, credit)
        raise
    except Exception as exc:
        fenced_failure_release(runtime, credit)
        raise WebChatError("ai_failed", "Could not generate a reply right now.", status_code=503) from exc
    finally:
        await heartbeat.stop()

    if not reply_text:
        fenced_failure_release(runtime, credit)
        raise WebChatError("empty_reply", "Could not generate a reply right now.", status_code=503)
    return reply_text
