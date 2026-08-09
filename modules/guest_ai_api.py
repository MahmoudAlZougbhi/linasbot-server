"""Public guest chat API — sales-only, rate-limited, no CM/tool writes."""

from __future__ import annotations

from typing import Any

from fastapi import Header, HTTPException, Request
from pydantic import BaseModel, Field

from modules.core import app
from services.guest_ai_service import GuestAIModelError, build_guest_greeting, compose_guest_reply
from services.guest_chat_limits import (
    GUEST_MAX_QUESTIONS,
    GUEST_MAX_WORDS,
    count_words,
    words_ok,
)
from services.guest_chat_store import guest_chat_store
from services.rate_limit_service import rate_limit_service
from services.system_knowledge_retrieval import detect_message_language


class GuestSessionBody(BaseModel):
    guest_session_id: str = Field(min_length=8, max_length=80)
    language: str | None = None


class GuestMessageBody(BaseModel):
    guest_session_id: str = Field(min_length=8, max_length=80)
    content: str = Field(min_length=1, max_length=2000)
    language: str | None = None


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for") or ""
    if forwarded:
        return forwarded.split(",")[0].strip() or "unknown"
    if request.client:
        return request.client.host or "unknown"
    return "unknown"


def _rate_limit_guest(request: Request, session_id: str) -> None:
    ip = _client_ip(request)
    for key, limit, window in (
        (f"guest-ai:ip:{ip}", 40, 300),
        (f"guest-ai:sid:{session_id}", 20, 300),
    ):
        allowed, retry = rate_limit_service.hit(key, limit=limit, window_seconds=window)
        if not allowed:
            raise HTTPException(
                status_code=429,
                detail={"error": "Rate limit exceeded", "retry_after": retry},
                headers={"Retry-After": str(retry)},
            )


def _session_payload(session: Any) -> dict[str, Any]:
    return {
        "id": session.id,
        "questions_used": session.questions_used,
        "questions_remaining": session.remaining(),
        "max_questions": GUEST_MAX_QUESTIONS,
        "max_words": GUEST_MAX_WORDS,
        "messages": [
            {
                "id": m.id,
                "role": m.role,
                "content": m.content,
                "created_at": m.created_at,
            }
            for m in session.messages
        ],
    }


def _history_payload(session: Any) -> list[dict[str, Any]]:
    return [{"role": m.role, "content": m.content} for m in session.messages]


@app.post("/api/guest-ai/session")
async def ensure_guest_session(body: GuestSessionBody, request: Request) -> Any:
    _rate_limit_guest(request, body.guest_session_id)
    lang = (body.language or "en").strip().lower()
    if lang not in {"en", "ar", "fr"}:
        lang = "en"
    try:
        session = guest_chat_store.get_or_create(
            body.guest_session_id,
            greeting=build_guest_greeting(language=lang),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"success": True, "session": _session_payload(session)}


@app.get("/api/guest-ai/session")
async def get_guest_session(
    request: Request,
    x_guest_session_id: str | None = Header(default=None, alias="X-Guest-Session-Id"),
) -> Any:
    sid = (x_guest_session_id or "").strip()
    if len(sid) < 8:
        raise HTTPException(status_code=400, detail="X-Guest-Session-Id required")
    _rate_limit_guest(request, sid)
    session = guest_chat_store.get(sid)
    if session is None:
        raise HTTPException(status_code=404, detail="Guest session not found")
    return {"success": True, "session": _session_payload(session)}


@app.post("/api/guest-ai/session/messages")
async def send_guest_message(body: GuestMessageBody, request: Request) -> Any:
    _rate_limit_guest(request, body.guest_session_id)
    content = (body.content or "").strip()
    if not content:
        raise HTTPException(status_code=400, detail="content required")
    if not words_ok(content):
        raise HTTPException(
            status_code=400,
            detail={
                "error": "word_limit",
                "message": f"Guest questions are limited to {GUEST_MAX_WORDS} words.",
                "max_words": GUEST_MAX_WORDS,
                "word_count": count_words(content),
            },
        )

    session = guest_chat_store.get(body.guest_session_id)
    if session is None:
        lang0 = (body.language or detect_message_language(content)).strip().lower()
        if lang0 not in {"en", "ar", "fr"}:
            lang0 = "en"
        session = guest_chat_store.get_or_create(
            body.guest_session_id,
            greeting=build_guest_greeting(language=lang0),
        )

    if session.questions_used >= GUEST_MAX_QUESTIONS:
        return {
            "success": False,
            "error": "guest_limit",
            "code": "GUEST_QUESTION_LIMIT",
            "session": _session_payload(session),
            "message": {
                "en": "You’ve reached the guest limit (10 questions). Log in or create an account to continue.",
                "ar": "وصلت إلى حد الضيف (10 أسئلة). سجّل الدخول أو أنشئ حساباً للمتابعة.",
                "fr": "Limite invité atteinte (10 questions). Connectez-vous ou créez un compte.",
            },
        }

    lang = (body.language or detect_message_language(content)).strip().lower()
    if lang not in {"en", "ar", "fr"}:
        lang = "en"

    history = _history_payload(session)
    try:
        composed = await compose_guest_reply(content, language=lang, history=history)
    except GuestAIModelError as exc:
        # Honest failure — do not append a canned sales blurb or consume a question.
        raise HTTPException(
            status_code=503,
            detail={
                "error": "guest_model_unavailable",
                "message": "Linas AI is temporarily unavailable. Please try again in a moment.",
                "reason": str(exc),
            },
        ) from exc

    # Hard guarantee: no tool execution path exists on guest chat.
    assert composed.get("tools_used") == []
    updated = guest_chat_store.append_turn(
        body.guest_session_id,
        user_text=content,
        assistant_text=str(composed["reply_text"]),
    )
    assistant = updated.messages[-1]
    return {
        "success": True,
        "message": {
            "id": assistant.id,
            "role": assistant.role,
            "content": assistant.content,
            "created_at": assistant.created_at,
        },
        "session": _session_payload(updated),
        "meta": {
            "tools_used": [],
            "capabilities": composed.get("capabilities") or [],
            "language": composed.get("language"),
            "model": composed.get("model"),
        },
    }
