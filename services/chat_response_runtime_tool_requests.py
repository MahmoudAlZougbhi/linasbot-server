"""Handle create_customer_request inside get_bot_chat_response tool loop."""

from __future__ import annotations

from services.chat_response_runtime_common import (
    LOOP_CONTINUE,
    Any,
    _record_tool_round_trip,
    config,
    json,
)
from services.requests.ai_tool import (
    CREATE_CUSTOMER_REQUEST_TOOL_NAME,
    build_context_from_user_data,
    execute_create_customer_request,
)


async def handle_create_customer_request_tool(ns: Any) -> Any:
    if ns.function_name != CREATE_CUSTOMER_REQUEST_TOOL_NAME:
        return None

    ud = config.user_data_whatsapp.get(ns.user_id) or {}
    lang = str(getattr(ns, "response_language", None) or getattr(ns, "current_preferred_lang", None) or "en")
    ctx = build_context_from_user_data(ud, response_language=lang)
    if ctx is None:
        tool_output = {
            "ok": False,
            "error": "TENANT_OR_CHANNEL_BINDING_REQUIRED",
            "message": "Server could not bind tenant/channel for request create",
        }
        tool_content = json.dumps(tool_output, default=str)
        ns.tool_round_trips.append(_record_tool_round_trip(ns.function_name, ns.function_args, tool_content, None))
        ns.messages.append(
            {
                "tool_call_id": ns.tool_call.id,
                "role": "tool",
                "name": ns.function_name,
                "content": tool_content,
            }
        )
        return LOOP_CONTINUE

    try:
        from db.session import WhatsAppDatabaseUnavailable, whatsapp_session

        with whatsapp_session() as session:
            tool_output = execute_create_customer_request(ns.function_args, ctx, session=session)
    except WhatsAppDatabaseUnavailable as exc:
        tool_output = {
            "ok": False,
            "error": "REQUESTS_DB_UNAVAILABLE",
            "message": str(exc),
        }
    except Exception as exc:
        tool_output = {
            "ok": False,
            "error": "REQUESTS_TOOL_FAILED",
            "message": str(exc),
        }

    tool_content = json.dumps(tool_output, default=str)
    ns.tool_round_trips.append(_record_tool_round_trip(ns.function_name, ns.function_args, tool_content, None))
    ns.messages.append(
        {
            "tool_call_id": ns.tool_call.id,
            "role": "tool",
            "name": ns.function_name,
            "content": tool_content,
        }
    )
    if isinstance(tool_output, dict) and tool_output.get("ok"):
        ns.extra_tool_names.append(CREATE_CUSTOMER_REQUEST_TOOL_NAME)
        if tool_output.get("pending_confirmation"):
            flow_meta = getattr(ns, "parsed_response", None)
            if not isinstance(flow_meta, dict):
                ns._requests_pending_confirmation = True
            else:
                ns._requests_pending_confirmation = True
    return LOOP_CONTINUE
