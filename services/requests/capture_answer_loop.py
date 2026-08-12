"""Optional Answer-side create_customer_request tool round (Customer Reply V2)."""

from __future__ import annotations

import json
from typing import Any

from services.requests.ai_tool import (
    CREATE_CUSTOMER_REQUEST_TOOL_NAME,
    AiToolContext,
    execute_create_customer_request,
)
from services.requests.capture_tools_wire import customer_reply_capture_tools


def capture_tools_allowed(tools: list[dict[str, Any]] | None) -> bool:
    """True when tools are only Requests capture tools (never retrieval)."""
    if not tools:
        return True
    for tool in tools:
        name = str((tool.get("function") or {}).get("name") or "").strip()
        if name != CREATE_CUSTOMER_REQUEST_TOOL_NAME:
            return False
    return True


def build_answer_capture_context(
    *,
    tenant_id: str,
    channel: str,
    conversation_id: str | None,
    customer_profile: dict[str, Any] | None,
    response_language: str,
    asset_id: str | None = None,
    provider_sender_id: str | None = None,
    originating_comment_id: str | None = None,
) -> AiToolContext | None:
    from services.requests.capture import is_public_comment_channel, normalize_source_channel

    if is_public_comment_channel(channel):
        return AiToolContext(
            tenant_id=tenant_id,
            source_channel="instagram_dm",
            conversation_id=conversation_id,
            public_comment=True,
            response_language=response_language,
        )
    source = normalize_source_channel(channel)
    if not source:
        return None
    profile = customer_profile or {}
    return AiToolContext(
        tenant_id=tenant_id,
        source_channel=source,
        conversation_id=conversation_id,
        source_account_id=asset_id,
        external_customer_id=provider_sender_id or str(profile.get("provider_sender_id") or "") or None,
        customer_display_name=str(profile.get("effective_name") or profile.get("display_name") or "") or None,
        originating_comment_id=originating_comment_id,
        response_language=response_language,
        public_comment=False,
    )


async def maybe_run_capture_tool_round(
    *,
    tenant_id: str,
    messages: list[dict[str, Any]],
    response: Any,
    ctx: AiToolContext | None,
    llm_fn: Any,
    channel: str,
) -> Any:
    """If the model called create_customer_request, execute once and continue the answer call."""
    tools = customer_reply_capture_tools(tenant_id)
    if not tools or ctx is None:
        return response
    choice = response.choices[0].message if getattr(response, "choices", None) else None
    tool_calls = getattr(choice, "tool_calls", None) if choice is not None else None
    if not tool_calls:
        return response

    if choice is None:
        return response
    if hasattr(choice, "model_dump"):
        messages.append(choice.model_dump(exclude_none=True))
    else:
        messages.append({"role": "assistant"})
    try:
        from db.session import WhatsAppDatabaseUnavailable, whatsapp_session
    except Exception:
        return response

    for call in tool_calls:
        fn = getattr(call, "function", None)
        name = str(getattr(fn, "name", "") or "")
        raw_args = getattr(fn, "arguments", None) or "{}"
        try:
            args = json.loads(raw_args) if isinstance(raw_args, str) else dict(raw_args or {})
        except json.JSONDecodeError:
            args = {}
        try:
            with whatsapp_session() as session:
                if name == CREATE_CUSTOMER_REQUEST_TOOL_NAME:
                    out = execute_create_customer_request(args, ctx, session=session)
                else:
                    out = {"ok": False, "error": "unknown_tool"}
        except WhatsAppDatabaseUnavailable as exc:
            out = {"ok": False, "error": "REQUESTS_DB_UNAVAILABLE", "message": str(exc)}
        messages.append(
            {
                "tool_call_id": getattr(call, "id", None),
                "role": "tool",
                "name": name,
                "content": json.dumps(out, default=str),
            }
        )

    return await llm_fn(messages=messages, tools=tools)
