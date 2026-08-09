"""Owner Linas AI chat API (conversations + messages)."""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException, Request
from pydantic import BaseModel, Field

from modules.api_security import require_session
from modules.core import app
from services.owner_ai_orchestrator import run_owner_turn
from services.owner_chat_store import owner_chat_store


class CreateConversationBody(BaseModel):
    title: str | None = None


class SendMessageBody(BaseModel):
    content: str = Field(min_length=1, max_length=8000)
    confirm_tool: str | None = None


class RenameBody(BaseModel):
    title: str = Field(min_length=1, max_length=120)


@app.get("/api/owner-ai/conversations")
async def list_owner_conversations(request: Request) -> Any:
    session = require_session(request)
    items = owner_chat_store.list_conversations(tenant_id=session.tenant_id, user_id=session.user_id)
    return {"success": True, "conversations": items}


@app.post("/api/owner-ai/conversations")
async def create_owner_conversation(body: CreateConversationBody, request: Request) -> Any:
    session = require_session(request)
    conv = owner_chat_store.create_conversation(
        tenant_id=session.tenant_id,
        user_id=session.user_id,
        title=(body.title or "New chat"),
    )
    return {
        "success": True,
        "conversation": {
            "id": conv.id,
            "title": conv.title,
            "created_at": conv.created_at,
            "updated_at": conv.updated_at,
            "messages": [m.__dict__ for m in (conv.messages or [])],
        },
    }


@app.get("/api/owner-ai/conversations/{conversation_id}")
async def get_owner_conversation(conversation_id: str, request: Request) -> Any:
    session = require_session(request)
    conv = owner_chat_store.get_conversation(
        tenant_id=session.tenant_id,
        user_id=session.user_id,
        conversation_id=conversation_id,
    )
    if conv is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return {
        "success": True,
        "conversation": {
            "id": conv.id,
            "title": conv.title,
            "created_at": conv.created_at,
            "updated_at": conv.updated_at,
            "messages": [m.__dict__ for m in (conv.messages or [])],
        },
    }


@app.post("/api/owner-ai/conversations/{conversation_id}/messages")
async def send_owner_message(conversation_id: str, body: SendMessageBody, request: Request) -> Any:
    session = require_session(request)
    conv = owner_chat_store.get_conversation(
        tenant_id=session.tenant_id,
        user_id=session.user_id,
        conversation_id=conversation_id,
    )
    if conv is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    owner_chat_store.append_message(
        tenant_id=session.tenant_id,
        user_id=session.user_id,
        conversation_id=conversation_id,
        role="user",
        content=body.content.strip(),
    )
    result = await run_owner_turn(
        tenant_id=session.tenant_id,
        user_id=session.user_id,
        role=session.role,
        conversation_id=conversation_id,
        user_text=body.content.strip(),
        confirm_tool=body.confirm_tool,
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
        "pending_confirmation": result.pending_confirmation,
    }


@app.patch("/api/owner-ai/conversations/{conversation_id}")
async def rename_owner_conversation(conversation_id: str, body: RenameBody, request: Request) -> Any:
    session = require_session(request)
    ok = owner_chat_store.rename(
        tenant_id=session.tenant_id,
        user_id=session.user_id,
        conversation_id=conversation_id,
        title=body.title,
    )
    if not ok:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return {"success": True}


@app.delete("/api/owner-ai/conversations/{conversation_id}")
async def delete_owner_conversation(conversation_id: str, request: Request) -> Any:
    session = require_session(request)
    ok = owner_chat_store.soft_delete(
        tenant_id=session.tenant_id,
        user_id=session.user_id,
        conversation_id=conversation_id,
    )
    if not ok:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return {"success": True}
