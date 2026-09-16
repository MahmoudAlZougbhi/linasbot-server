"""Web Chat V2 reply generation (split from processor for file-size cap)."""

from __future__ import annotations

from typing import Any

from services.brain.history_ids import web_inbound_message_id
from services.integrations.web_chat.constants import CUSTOMER_REPLY_CHANNEL
from services.integrations.web_chat.credit_fsm import WebChatCreditHandle
from services.integrations.web_chat.operation_fence import fenced_failure_release
from services.integrations.web_chat.store import WebChatWidgetConfig


def _fence(runtime: Any, credit: WebChatCreditHandle, conversation_id: str, text: str) -> bool:
    return fenced_failure_release(runtime, credit, conversation_id=conversation_id, user_text=text)


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
    from services.ai_setup.ai_limits_enforcement import customer_reply_limit_message
    from services.ai_setup.language_policy import detect_and_resolve_customer_languages
    from services.brain.reply.orchestrator import run_customer_reply_v2_dm
    from services.integrations.web_chat.operation_heartbeat import OperationLeaseHeartbeat
    from services.integrations.web_chat.processor import WebChatError
    from services.integrations.web_chat.takeover_gate import maybe_silence_web_chat_for_takeover

    if await maybe_silence_web_chat_for_takeover(
        tenant_id=tid,
        user_id=user_id,
        conversation_id=conversation_id,
        visitor_id=visitor_id,
        inbound_text=text,
        widget=widget,
    ):
        return ""

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
            message_id=web_inbound_message_id(conversation_id, text),
        )
        if heartbeat.lost_lease:
            _fence(runtime, credit, conversation_id, text)
            raise WebChatError("operation_in_progress", "Operation lease lost during AI.", status_code=409)
        reply_text = str(
            getattr(outcome, "reply", None) or getattr(outcome, "answer", None) or getattr(outcome, "text", None) or ""
        ).strip()
        if not reply_text and isinstance(outcome, dict):
            reply_text = str(outcome.get("reply") or outcome.get("answer") or outcome.get("text") or "").strip()
        from services.brain.outbound_safety import looks_like_instruction_text

        if reply_text and looks_like_instruction_text(reply_text):
            from services.brain.greeting import is_greeting_only, safe_greeting_text
            from services.brain.templates import brain_template

            if is_greeting_only(text):
                reply_text = safe_greeting_text(
                    tenant_id=tid,
                    message=text,
                    language=str(_lang.get("response_language") or ""),
                )
            else:
                reply_text = brain_template("no_evidence", str(_lang.get("response_language") or ""))
        reason = str(getattr(outcome, "reason", "") or "")
        if reason.endswith("_limit") or reason == "ai_reply_limit":
            _fence(runtime, credit, conversation_id, text)
            raise WebChatError("ai_reply_limit", customer_reply_limit_message(reply_precheck), status_code=429)
        if reason == "insufficient_messages":
            _fence(runtime, credit, conversation_id, text)
            raise WebChatError(
                "insufficient_messages",
                "AI replies are paused until messages are available.",
                status_code=402,
            )
        if word_notice and reply_text:
            reply_text = f"{word_notice}\n\n{reply_text}"
        if reason == "engine_removed":
            _fence(runtime, credit, conversation_id, text)
            return ""
    except WebChatError:
        _fence(runtime, credit, conversation_id, text)
        raise
    except Exception as exc:
        _fence(runtime, credit, conversation_id, text)
        raise WebChatError("ai_failed", "Could not generate a reply right now.", status_code=503) from exc
    finally:
        await heartbeat.stop()

    if not reply_text:
        _fence(runtime, credit, conversation_id, text)
        return ""
    return reply_text
