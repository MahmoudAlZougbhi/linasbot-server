"""Owner Linas AI System Copilot API (conversations + messages + profile + CM approve)."""

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
    content: str = Field(min_length=0, max_length=8000)
    confirm_tool: str | None = None
    tool_args: dict[str, Any] | None = None


class RenameBody(BaseModel):
    title: str = Field(min_length=1, max_length=120)


class ProfileUpdateBody(BaseModel):
    gender: str | None = None
    display_name: str | None = None
    preferred_language: str | None = None
    form_of_address: str | None = None
    address_prompt_asked: bool | None = None


class ProposeCmPatchBody(BaseModel):
    section: str = Field(min_length=1, max_length=64)
    patch: dict[str, Any]


class ApproveCmPatchBody(BaseModel):
    proposal_id: str = Field(min_length=8, max_length=64)
    confirmed: bool = False


@app.get("/api/owner-ai/conversations")
async def list_owner_conversations(request: Request) -> Any:
    session = require_session(request)
    items = owner_chat_store.list_conversations(tenant_id=session.tenant_id, user_id=session.user_id)
    return {"success": True, "conversations": items}


@app.post("/api/owner-ai/conversations")
async def create_owner_conversation(body: CreateConversationBody, request: Request) -> Any:
    session = require_session(request)
    from services.owner_ai_greeting import build_greeting

    greeting = build_greeting(tenant_id=session.tenant_id, user_id=session.user_id)
    # Optional one-time address prompt: mark asked after first greeting that includes it.
    if greeting.get("address_prompt_included"):
        try:
            from services.owner_ai_profile import update_owner_profile

            update_owner_profile(session.user_id, {"address_prompt_asked": True})
        except Exception:
            pass
    conv = owner_chat_store.create_conversation(
        tenant_id=session.tenant_id,
        user_id=session.user_id,
        title=(body.title or "New chat"),
        greeting_text=str(greeting["text"]),
    )
    return {
        "success": True,
        "conversation": {
            "id": conv.id,
            "title": conv.title,
            "created_at": conv.created_at,
            "updated_at": conv.updated_at,
            "messages": [m.__dict__ for m in (conv.messages or [])],
            "setup_stage": greeting.get("setup_stage"),
            "greeting_language": greeting.get("language"),
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
    content = (body.content or "").strip()
    if not content and not body.confirm_tool:
        raise HTTPException(status_code=400, detail="content or confirm_tool required")
    if content:
        owner_chat_store.append_message(
            tenant_id=session.tenant_id,
            user_id=session.user_id,
            conversation_id=conversation_id,
            role="user",
            content=content,
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
        user_text=content,
        confirm_tool=body.confirm_tool,
        messages=history,
        tool_args=body.tool_args,
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
        "proposed_patch": result.proposed_patch,
        "route": result.route,
        "context_tokens": result.context_tokens,
        "setup_stage": result.setup_stage,
        "quick_actions": result.quick_actions,
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


@app.get("/api/owner-ai/greeting")
async def owner_ai_greeting(request: Request) -> Any:
    session = require_session(request)
    from services.owner_ai_greeting import build_greeting

    return {"success": True, "greeting": build_greeting(tenant_id=session.tenant_id, user_id=session.user_id)}


@app.get("/api/owner-ai/profile")
async def get_owner_ai_profile(request: Request) -> Any:
    session = require_session(request)
    from services.owner_ai_profile import read_owner_profile

    return {"success": True, "profile": read_owner_profile(session.user_id)}


@app.patch("/api/owner-ai/profile")
async def patch_owner_ai_profile(body: ProfileUpdateBody, request: Request) -> Any:
    session = require_session(request)
    from services.owner_ai_profile import update_owner_profile

    updates = body.model_dump(exclude_none=True)
    profile = update_owner_profile(session.user_id, updates)
    return {"success": True, "profile": profile}


@app.get("/api/owner-ai/knowledge")
async def owner_ai_knowledge(request: Request, q: str = "") -> Any:
    session = require_session(request)
    del session
    from services.system_knowledge_retrieval import help_payload_for_query

    return {"success": True, **help_payload_for_query(q)}


@app.post("/api/owner-ai/cm/propose-patch")
async def owner_ai_propose_cm_patch(body: ProposeCmPatchBody, request: Request) -> Any:
    session = require_session(request)
    from services.owner_ai_tools import dispatch_tool

    result = await dispatch_tool(
        "propose_cm_patch",
        tenant_id=session.tenant_id,
        user_id=session.user_id,
        role=session.role,
        args={"section": body.section, "patch": body.patch},
    )
    if not result.ok:
        raise HTTPException(status_code=400, detail=result.error or "propose failed")
    return {
        "success": True,
        **result.data,
        "requires_confirmation": result.requires_confirmation,
        "confirmation_token": result.confirmation_token,
    }


@app.post("/api/owner-ai/cm/approve-patch")
async def owner_ai_approve_cm_patch(body: ApproveCmPatchBody, request: Request) -> Any:
    session = require_session(request)
    from services.owner_ai_tools import dispatch_tool

    result = await dispatch_tool(
        "approve_cm_patch",
        tenant_id=session.tenant_id,
        user_id=session.user_id,
        role=session.role,
        args={"proposal_id": body.proposal_id},
        confirmed=body.confirmed,
    )
    if result.requires_confirmation:
        return {
            "success": True,
            "requires_confirmation": True,
            "confirmation_token": result.confirmation_token,
            "data": result.data,
        }
    if not result.ok:
        raise HTTPException(status_code=400, detail=result.error or "approve failed")
    return {"success": True, **result.data}
