"""Web Chat AI eligibility and inbound message processing."""

from __future__ import annotations

import hashlib
import uuid
from typing import Any

from services.web_chat.constants import CHANNEL_ID, SOURCE_CHANNEL_WEB_CHAT, USER_ID_PREFIX
from services.web_chat.credit_fsm import CreditFsmState, WebChatCreditHandle, tenant_scoped_user_data
from services.web_chat.operation import (
    advance_operation,
    begin_operation,
    build_turn_payload,
    ensure_operation_credit_reserved,
    reconcile_billing_pending,
    refresh_operation_runtime,
)
from services.web_chat.operation_fence import fenced_failure_release
from services.web_chat.operation_fsm import OperationFsmError, OperationState, stable_operation_key
from services.web_chat.persistence import PersistFailure, PersistOutcome, persist_web_chat_message
from services.web_chat.session_authority import verified_session_snapshot
from services.web_chat.store import WebChatStoreBackend, WebChatVisitorSession, WebChatWidgetConfig, web_chat_store


class WebChatError(Exception):
    def __init__(self, code: str, message: str, *, status_code: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


async def _generate_reply_text(**kwargs: Any) -> str:
    from services.web_chat.processor_v2_reply import generate_web_chat_reply_text

    return await generate_web_chat_reply_text(**kwargs)


def compose_web_user_id(visitor_session_id: str) -> str:
    sid = (visitor_session_id or "").strip()
    return f"{USER_ID_PREFIX}{sid}"


def _derive_turn_client_key(*, session_id: str, content: str, idempotency_key: str | None) -> str:
    explicit = str(idempotency_key or "").strip()
    if explicit:
        return explicit
    # Never derive from session+content — identical text must be separate turns unless keyed.
    return f"anon:{uuid.uuid4().hex}"


def _ensure_turn_appended(
    store: WebChatStoreBackend,
    visitor_id: str,
    *,
    user_text: str,
    assistant_text: str,
    turn_key: str | None = None,
) -> None:
    visitor = store.get_visitor(visitor_id)
    if visitor is None:
        return
    key = str(turn_key or "").strip()
    if key:
        user_id = f"{key}:user"
        assistant_id = f"{key}:assistant"
        has_user = any(m.id == user_id for m in visitor.messages)
        has_assistant = any(m.id == assistant_id for m in visitor.messages)
        if has_user and has_assistant:
            return
    else:
        has_user = any(m.role == "user" and m.content == user_text for m in visitor.messages)
        has_assistant = any(m.role == "assistant" and m.content == assistant_text for m in visitor.messages)
        if has_user and has_assistant:
            return
    store.append_turn(visitor_id, user_text=user_text, assistant_text=assistant_text, turn_key=turn_key)


def _replay_if_operation_visible(
    *,
    runtime: Any,
    credit: WebChatCreditHandle,
    tid: str,
    operation_key: str,
    reply_text: str,
) -> str | None:
    refresh_operation_runtime(runtime)
    record = runtime.record
    if record is None:
        return None
    if record.state not in {
        OperationState.DURABLE_VISIBLE,
        OperationState.CAPTURED,
        OperationState.COMPLETE,
        OperationState.BILLING_PENDING,
    }:
        return None
    if record.state == OperationState.BILLING_PENDING:
        reconcile_billing_pending(tenant_id=tid, operation_key=operation_key, credit=credit)
        refresh_operation_runtime(runtime)
        record = runtime.record
    return (record.canonical_reply() if record else None) or reply_text


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
    store: WebChatStoreBackend | None = None,
    idempotency_key: str | None = None,
    attachments: list[Any] | None = None,
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
    inbound_media: dict[str, Any] | None = None
    attachment_types: list[str] | None = None
    if attachments:
        from services.customer_reply_v2.inbound_media import ingest_inbound_attachments, luna_inbound_view

        inbound = await ingest_inbound_attachments(
            tenant_id=tid,
            attachments=attachments,
            caption=text,
        )
        inbound_media = luna_inbound_view(inbound)
        if inbound.safety_image_urls:
            inbound_media["safety_image_urls"] = list(inbound.safety_image_urls)
        attachment_types = list(inbound.attachment_types)
        text = inbound.pipeline_text or text
    if not text:
        raise WebChatError("empty_message", "Message cannot be empty.")

    visitor_id = visitor_session.id
    user_id = compose_web_user_id(visitor_id)
    conversation_id = f"web:{tid}:{visitor_id}"
    client_key = _derive_turn_client_key(session_id=visitor_id, content=text, idempotency_key=idempotency_key)
    operation_key = stable_operation_key(session_id=visitor_id, client_key=client_key)
    snapshot = verified_session_snapshot(
        widget=widget,
        session_id=visitor_id,
        authority_hash=str(getattr(visitor_session, "authority_hash", "") or ""),
    )
    payload = build_turn_payload(session_id=visitor_id, content=text)

    try:
        runtime = begin_operation(
            tenant_id=tid,
            operation_key=operation_key,
            payload=payload,
            snapshot=snapshot,
        )
    except OperationFsmError as exc:
        raise WebChatError(exc.code, exc.message, status_code=409) from exc

    attempt = runtime.record.attempt if runtime.record else 1
    from services.web_chat.operation_credit_reconcile import reconcile_credit_before_side_effects
    from services.web_chat.operation_fsm import web_chat_credit_request_id

    request_id = web_chat_credit_request_id(
        session_id=visitor_id,
        operation_key=operation_key,
        attempt=attempt,
    )
    credit = WebChatCreditHandle(
        tenant_id=tid,
        reservation_id=runtime.record.reservation_id if runtime.record else None,
        request_id=request_id,
        operation_state=runtime.record.state if runtime.record else OperationState.CLAIMED,
    )
    try:
        reconcile_credit_before_side_effects(runtime, credit)
    except OperationFsmError as exc:
        raise WebChatError(exc.code, exc.message, status_code=409) from exc
    refresh_operation_runtime(runtime)
    attempt = runtime.record.attempt if runtime.record else attempt
    request_id = web_chat_credit_request_id(
        session_id=visitor_id,
        operation_key=operation_key,
        attempt=attempt,
    )
    credit.request_id = request_id
    credit.reservation_id = runtime.record.reservation_id if runtime.record else credit.reservation_id
    if runtime.record:
        credit.operation_state = runtime.record.state
        credit.hydrate_from_operation_context()

    if runtime.record is not None and runtime.record.state == OperationState.COMPLETE:
        replay = runtime.record.canonical_reply()
        if replay:
            active_store = store or web_chat_store
            _ensure_turn_appended(
                active_store,
                visitor_id,
                user_text=text,
                assistant_text=replay,
                turn_key=operation_key,
            )
            return replay

    if runtime.record is not None and runtime.record.state == OperationState.CAPTURED:
        replay = runtime.record.canonical_reply()
        if replay:
            turn_result = dict(runtime.record.result or {})
            turn_result.setdefault("reply_text", replay)
            turn_result.setdefault("conversation_id", conversation_id)
            turn_result.setdefault("operation_key", operation_key)
            credit = WebChatCreditHandle(
                tenant_id=tid,
                reservation_id=runtime.record.reservation_id,
                request_id=request_id,
                operation_state=OperationState.CAPTURED,
            )
            from services.web_chat.processor_completion import complete_web_chat_turn

            return await complete_web_chat_turn(
                runtime=runtime,
                credit=credit,
                tid=tid,
                operation_key=operation_key,
                visitor_id=visitor_id,
                user_id=user_id,
                conversation_id=conversation_id,
                text=text,
                reply_text=replay,
                turn_result=turn_result,
                widget=widget,
                active_store=store or web_chat_store,
                past_reply_ready=True,
            )

    resuming_past_ai = runtime.record is not None and runtime.record.state in {
        OperationState.REPLY_READY,
        OperationState.DURABLE_VISIBLE,
        OperationState.BILLING_PENDING,
        OperationState.CAPTURED,
    }

    from services.ai_limits_enforcement import (
        apply_inbound_word_limit,
        customer_reply_limit_message,
        enforce_text_reply_quota,
    )

    limit_user: dict[str, Any] = tenant_scoped_user_data(tenant_id=tid, user_id=user_id, visitor_id=visitor_id)
    text, word_notice = apply_inbound_word_limit(user_id=user_id, user_data=limit_user, text=text)
    reply_precheck = enforce_text_reply_quota(user_id=user_id, user_data=limit_user, consume=False)
    if not reply_precheck.allowed:
        raise WebChatError("ai_reply_limit", customer_reply_limit_message(reply_precheck), status_code=429)

    credit.operation_state = runtime.record.state if runtime.record else OperationState.CLAIMED
    credit.hydrate_from_operation_context()
    if runtime.record and runtime.record.state == OperationState.BILLING_PENDING:
        reconciled = reconcile_billing_pending(tenant_id=tid, operation_key=operation_key, credit=credit)
        refresh_operation_runtime(runtime)
        replay = (reconciled or runtime.record).canonical_reply() if reconciled or runtime.record else None
        if credit.state.name == "CAPTURED" and replay:
            active_store = store or web_chat_store
            _ensure_turn_appended(
                active_store,
                visitor_id,
                user_text=text,
                assistant_text=replay,
                turn_key=operation_key,
            )
            if runtime.record and runtime.record.state != OperationState.COMPLETE:
                advance_operation(runtime, OperationState.COMPLETE, result=runtime.record.result)
            return replay

    try:
        if runtime.record is None or runtime.record.state == OperationState.CLAIMED:
            ensure_operation_credit_reserved(runtime, credit)
            credit.operation_state = OperationState.RESERVED
        elif runtime.record.state in {
            OperationState.RESERVED,
            OperationState.REPLY_READY,
            OperationState.DURABLE_VISIBLE,
            OperationState.BILLING_PENDING,
            OperationState.CAPTURED,
        }:
            credit.operation_state = runtime.record.state
            if runtime.record.reservation_id:
                credit.reservation_id = runtime.record.reservation_id
                credit.state = CreditFsmState.RESERVED
    except PermissionError as exc:
        if runtime.record and (runtime.record.reservation_id or credit.reservation_id):
            fenced_failure_release(runtime, credit)
        raise WebChatError(
            "insufficient_credits", "AI replies are paused until credits are available.", status_code=402
        ) from exc

    if resuming_past_ai and runtime.record and runtime.record.canonical_reply():
        reply_text = runtime.record.canonical_reply() or ""
    else:
        reply_text = await _generate_reply_text(
            tid=tid,
            text=text,
            conversation_id=conversation_id,
            widget=widget,
            visitor_id=visitor_id,
            user_id=user_id,
            word_notice=word_notice,
            reply_precheck=reply_precheck,
            credit=credit,
            runtime=runtime,
            inbound_media=inbound_media,
            attachment_types=attachment_types,
        )

    turn_result = {"reply_text": reply_text, "conversation_id": conversation_id, "operation_key": operation_key}
    past_reply_ready = bool(
        runtime.record
        and runtime.record.state
        in {
            OperationState.DURABLE_VISIBLE,
            OperationState.CAPTURED,
            OperationState.BILLING_PENDING,
            OperationState.COMPLETE,
        }
    )
    if not (runtime.record and (runtime.record.state == OperationState.REPLY_READY or past_reply_ready)):
        advance_operation(runtime, OperationState.REPLY_READY, result=turn_result)
    if not past_reply_ready:
        credit.operation_state = OperationState.REPLY_READY

    from services.web_chat.processor_completion import complete_web_chat_turn

    return await complete_web_chat_turn(
        runtime=runtime,
        credit=credit,
        tid=tid,
        operation_key=operation_key,
        visitor_id=visitor_id,
        user_id=user_id,
        conversation_id=conversation_id,
        text=text,
        reply_text=reply_text,
        turn_result=turn_result,
        widget=widget,
        active_store=store or web_chat_store,
        past_reply_ready=past_reply_ready,
    )


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
    user_data = tenant_scoped_user_data(tenant_id=tenant_id, user_id=user_id, visitor_id=visitor_id)

    try:
        user_result = await persist_web_chat_message(
            user_id=user_id,
            role="user",
            text=user_text,
            conversation_id=conversation_id,
            metadata={
                "channel": CHANNEL_ID,
                "source": SOURCE_CHANNEL_WEB_CHAT,
                "widget_key": widget.widget_key,
                "tenant_id": tenant_id,
                "source_message_id": f"user:{conversation_id}:{hashlib.sha256(user_text.encode()).hexdigest()[:16]}",
            },
        )
        if user_result.outcome not in {PersistOutcome.CREATED, PersistOutcome.DUPLICATE}:
            raise PersistFailure("firestore_unavailable", "User message projection did not commit.")
        ai_result = await persist_web_chat_message(
            user_id=user_id,
            role="ai",
            text=reply_text,
            conversation_id=conversation_id,
            metadata={
                "channel": CHANNEL_ID,
                "source": SOURCE_CHANNEL_WEB_CHAT,
                "widget_key": widget.widget_key,
                "handled_by": "ai",
                "tenant_id": tenant_id,
                "source_message_id": f"ai:{conversation_id}:{hashlib.sha256(reply_text.encode()).hexdigest()[:16]}",
            },
        )
        if ai_result.outcome not in {PersistOutcome.CREATED, PersistOutcome.DUPLICATE}:
            raise PersistFailure("firestore_unavailable", "Assistant message projection did not commit.")
    except PersistFailure as exc:
        raise WebChatError("persist_failed", exc.message, status_code=503) from exc

    try:
        from services.interaction_flow_logger import is_flow_logging_enabled, log_interaction

        if is_flow_logging_enabled():
            log_interaction(
                user_id=user_id,
                user_data=user_data,
                user_message=user_text,
                bot_to_user=reply_text,
                source="web_chat",
                channel=CHANNEL_ID,
                conversation_id=conversation_id,
                handler_path="web_chat",
                outcome="ok",
                cm_diagnostics={"tenant_id": tenant_id},
            )
    except Exception:
        pass
