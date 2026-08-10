"""Owner Copilot V2 streaming + attachment + choice API routes."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Any

from fastapi import File, Form, HTTPException, Request, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from modules.api_security import require_session
from modules.core import app
from services.owner_chat_store import owner_chat_store
from services.owner_copilot_v2.stream_protocol import encode_sse, encode_sse_done


class StreamMessageBody(BaseModel):
    content: str = Field(default="", max_length=16000)
    confirm_tool: str | None = None
    tool_args: dict[str, Any] | None = None
    choice_id: str | None = None
    choice_set_id: str | None = None
    attachment_ids: list[str] | None = None


class ChoiceBody(BaseModel):
    choice_set_id: str = Field(min_length=4, max_length=64)
    choice_id: str = Field(min_length=1, max_length=64)
    label: str | None = None


@app.get("/api/owner-ai/v2/flags")
async def owner_ai_v2_flags(request: Request) -> Any:
    require_session(request)
    from services.owner_copilot_v2.flags import flags_snapshot

    return {"success": True, "flags": flags_snapshot()}


@app.get("/api/owner-ai/v2/attachment-types")
async def owner_ai_attachment_types(request: Request) -> Any:
    require_session(request)
    from services.owner_copilot_v2.attachments import supported_attachment_types

    return {"success": True, "types": supported_attachment_types()}


@app.post("/api/owner-ai/v2/attachments")
async def owner_ai_upload_attachment(
    request: Request,
    file: UploadFile = File(...),
) -> Any:
    session = require_session(request)
    from services.owner_copilot_v2.attachments import store_attachment

    raw = await file.read()
    result = store_attachment(
        tenant_id=session.tenant_id,
        user_id=session.user_id,
        filename=file.filename or "upload.bin",
        content=raw,
        content_type=file.content_type,
    )
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=result.get("error") or "upload_failed")
    # Never return a permanent public URL
    return {
        "success": True,
        "attachment_id": result["attachment_id"],
        "filename": result["filename"],
        "mime": result["mime"],
        "size": result["size"],
    }


@app.post("/api/owner-ai/conversations/{conversation_id}/messages/stream")
async def stream_owner_message(
    conversation_id: str,
    body: StreamMessageBody,
    request: Request,
) -> StreamingResponse:
    session = require_session(request)
    conv = owner_chat_store.get_conversation(
        tenant_id=session.tenant_id,
        user_id=session.user_id,
        conversation_id=conversation_id,
    )
    if conv is None:
        raise HTTPException(status_code=404, detail="Conversation not found")

    content = (body.content or "").strip()
    if not content and not body.confirm_tool and not body.choice_id and not (body.attachment_ids or []):
        raise HTTPException(status_code=400, detail="content, confirm_tool, choice, or attachment required")

    conversation_title: str | None = conv.title if conv else None
    if content or body.choice_id:
        label = content or (body.label if hasattr(body, "label") else None) or body.choice_id or ""
        owner_chat_store.append_message(
            tenant_id=session.tenant_id,
            user_id=session.user_id,
            conversation_id=conversation_id,
            role="user",
            content=str(label),
        )
        conv = owner_chat_store.get_conversation(
            tenant_id=session.tenant_id,
            user_id=session.user_id,
            conversation_id=conversation_id,
        )
        conversation_title = conv.title if conv else conversation_title

    history = [{"role": m.role, "content": m.content} for m in ((conv.messages if conv else None) or [])]
    cancel_flag = {"cancelled": False}

    async def event_gen() -> AsyncIterator[str]:
        from services.owner_copilot_v2.brain import iter_owner_turn_v2_events
        from services.owner_copilot_v2.models import StreamEvent

        # Client disconnect → cancel
        async def watch_disconnect() -> None:
            while True:
                if await request.is_disconnected():
                    cancel_flag["cancelled"] = True
                    return
                await asyncio.sleep(0.25)

        watcher = asyncio.create_task(watch_disconnect())
        reply_parts: list[str] = []
        done_payload: dict[str, Any] | None = None
        try:
            if conversation_title:
                yield encode_sse(StreamEvent(type="title_updated", payload={"title": conversation_title}))
            async for ev in iter_owner_turn_v2_events(
                tenant_id=session.tenant_id,
                user_id=session.user_id,
                role=session.role,
                conversation_id=conversation_id,
                user_text=content,
                confirm_tool=body.confirm_tool,
                messages=history,
                tool_args=body.tool_args,
                choice_id=body.choice_id,
                choice_set_id=body.choice_set_id,
                attachment_ids=body.attachment_ids,
                is_cancelled=lambda: cancel_flag["cancelled"],
            ):
                if ev.type == "delta":
                    reply_parts.append(str(ev.payload.get("text") or ""))
                if ev.type == "done":
                    done_payload = {
                        **ev.payload,
                        "conversation_title": conversation_title,
                    }
                    yield encode_sse(StreamEvent(type="done", payload=done_payload))
                    continue
                yield encode_sse(ev)
            yield encode_sse_done()
        finally:
            watcher.cancel()
            final_text = str((done_payload or {}).get("reply_text") or "".join(reply_parts)).strip()
            incomplete = cancel_flag["cancelled"] or done_payload is None
            if final_text:
                owner_chat_store.append_message(
                    tenant_id=session.tenant_id,
                    user_id=session.user_id,
                    conversation_id=conversation_id,
                    role="assistant",
                    content=final_text if not incomplete else final_text + "\n\n[incomplete]",
                    tool_calls=(done_payload or {}).get("tool_calls"),
                )

    return StreamingResponse(
        event_gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "Connection": "keep-alive",
            # Disable nginx proxy buffering so mobile XHR onprogress sees deltas live.
            "X-Accel-Buffering": "no",
        },
    )


@app.post("/api/owner-ai/conversations/{conversation_id}/choices")
async def submit_owner_choice(conversation_id: str, body: ChoiceBody, request: Request) -> Any:
    """Structured choice submission — reuses stream/non-stream turn path."""
    session = require_session(request)
    from services.owner_ai_orchestrator import run_owner_turn

    conv = owner_chat_store.get_conversation(
        tenant_id=session.tenant_id,
        user_id=session.user_id,
        conversation_id=conversation_id,
    )
    if conv is None:
        raise HTTPException(status_code=404, detail="Conversation not found")

    label = (body.label or body.choice_id).strip()
    owner_chat_store.append_message(
        tenant_id=session.tenant_id,
        user_id=session.user_id,
        conversation_id=conversation_id,
        role="user",
        content=label,
    )
    conv = owner_chat_store.get_conversation(
        tenant_id=session.tenant_id,
        user_id=session.user_id,
        conversation_id=conversation_id,
    )
    history = [{"role": m.role, "content": m.content} for m in ((conv.messages if conv else None) or [])]
    result = await run_owner_turn(
        tenant_id=session.tenant_id,
        user_id=session.user_id,
        role=session.role,
        conversation_id=conversation_id,
        user_text=label,
        messages=history,
        choice_id=body.choice_id,
        choice_set_id=body.choice_set_id,
    )
    assistant = owner_chat_store.append_message(
        tenant_id=session.tenant_id,
        user_id=session.user_id,
        conversation_id=conversation_id,
        role="assistant",
        content=result.reply_text,
        tool_calls=result.tool_calls,
    )
    return {
        "success": True,
        "message": assistant.__dict__ if assistant else None,
        "cards": getattr(result, "cards", []),
        "choices": getattr(result, "choices", []),
        "pending_confirmation": result.pending_confirmation,
        "proposed_patch": result.proposed_patch,
        "setup_stage": result.setup_stage,
        "quick_actions": result.quick_actions,
        "model": getattr(result, "model", None),
    }


# Silence unused Form import if tree-shakers complain in some linters
_ = Form
