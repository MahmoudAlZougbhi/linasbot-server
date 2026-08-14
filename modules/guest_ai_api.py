"""Public guest chat API — product-info only, rate-limited, no CM/tool writes."""

from __future__ import annotations

from typing import Any

from fastapi import Header, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from modules.api_security import _client_ip
from modules.core import app
from services.guest_ai_service import GuestAIModelError, build_guest_greeting, compose_guest_reply
from services.guest_chat_limits import (
    GUEST_MAX_INPUT_TOKENS,
    GUEST_MAX_QUESTIONS,
    GUEST_MAX_WORDS,
    count_words,
    estimate_guest_tokens,
    payload_has_guest_media,
    tokens_ok,
    words_ok,
)
from services.guest_chat_store import guest_chat_store
from services.owner_ai_profile import resolve_owner_reply_language
from services.rate_limit_service import rate_limit_service

_INPUT_TOO_LARGE_MESSAGE = {
    "en": ("What you sent is too large (over 500 tokens). Subscribe to Linas AI to continue with larger messages."),
    "ar": ("اللي بعثتو كبير زيادة (أكثر من 500 توكن). اشترك بـ Linas AI لتقدر تبعت رسائل أطول."),
    "fr": (
        "Votre message est trop volumineux (plus de 500 jetons). "
        "Abonnez-vous à Linas AI pour envoyer des messages plus longs."
    ),
}

_MEDIA_BLOCKED_MESSAGE = {
    "en": "Guests can’t send photos or files. Subscribe to Linas AI to use attachments.",
    "ar": "الضيوف ما بيقدروا يبعتوا صور أو ملفات. اشترك بـ Linas AI لاستخدام المرفقات.",
    "fr": "Les invités ne peuvent pas envoyer de photos ou de fichiers. Abonnez-vous à Linas AI.",
}


class GuestSessionBody(BaseModel):
    guest_session_id: str = Field(min_length=8, max_length=80)
    language: str | None = None


class GuestMessageBody(BaseModel):
    """Text-only guest turns. Extra media keys are allowed only so we can reject them."""

    model_config = ConfigDict(extra="allow")

    guest_session_id: str = Field(min_length=8, max_length=80)
    content: str = Field(min_length=1, max_length=16000)
    language: str | None = None


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
    """Public session shape for UI — no remaining-count meters."""
    return {
        "id": session.id,
        "limit_reached": session.questions_used >= GUEST_MAX_QUESTIONS,
        "max_input_tokens": GUEST_MAX_INPUT_TOKENS,
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


def _lang(raw: str | None) -> str:
    lang = (raw or "en").strip().lower()
    return lang if lang in {"en", "ar", "fr"} else "en"


@app.post("/api/guest-ai/session")
async def ensure_guest_session(body: GuestSessionBody, request: Request) -> Any:
    _rate_limit_guest(request, body.guest_session_id)
    lang = _lang(body.language)
    try:
        session = guest_chat_store.get_or_create(
            body.guest_session_id,
            greeting=build_guest_greeting(language=lang, session_id=body.guest_session_id),
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

    # Guests are text-only; reject photo/file payloads before any LLM work.
    raw_payload = body.model_dump(exclude_none=False)
    if body.model_extra:
        raw_payload.update(body.model_extra)
    if payload_has_guest_media(raw_payload):
        lang_media = _lang(body.language)
        raise HTTPException(
            status_code=400,
            detail={
                "error": "guest_media_blocked",
                "code": "GUEST_MEDIA_BLOCKED",
                "message": _MEDIA_BLOCKED_MESSAGE[lang_media],
                "messages": _MEDIA_BLOCKED_MESSAGE,
            },
        )

    content = (body.content or "").strip()
    if not content:
        raise HTTPException(status_code=400, detail="content required")

    lang = _lang(body.language)
    if not tokens_ok(content):
        raise HTTPException(
            status_code=400,
            detail={
                "error": "input_token_limit",
                "code": "GUEST_INPUT_TOO_LARGE",
                "message": _INPUT_TOO_LARGE_MESSAGE[lang],
                "messages": _INPUT_TOO_LARGE_MESSAGE,
                "max_input_tokens": GUEST_MAX_INPUT_TOKENS,
                "estimated_tokens": estimate_guest_tokens(content),
            },
        )

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
        lang0 = resolve_owner_reply_language(
            content,
            reply_language_override=body.language,
            preferred_language=body.language,
        )
        session = guest_chat_store.get_or_create(
            body.guest_session_id,
            greeting=build_guest_greeting(language=lang0, session_id=body.guest_session_id),
        )

    if session.questions_used >= GUEST_MAX_QUESTIONS:
        return {
            "success": False,
            "error": "guest_limit",
            "code": "GUEST_QUESTION_LIMIT",
            "session": _session_payload(session),
            "message": {
                "en": "You’ve reached the guest limit. Download the Linas AI app and subscribe to continue.",
                "ar": "وصلت إلى حد الضيف. حمّل تطبيق Linas AI واشترك للمتابعة.",
                "fr": "Limite invité atteinte. Téléchargez l’app Linas AI et abonnez-vous pour continuer.",
            },
        }

    lang = resolve_owner_reply_language(
        content,
        reply_language_override=body.language,
        preferred_language=body.language,
    )

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
