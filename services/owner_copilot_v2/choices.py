"""Context-aware clickable choices (max 3) for Owner Copilot V2."""

from __future__ import annotations

import time
import uuid
from typing import Any

from services.owner_copilot_v2.models import ChatChoice

# In-memory choice sessions (tenant-scoped keys). Durable enough for active turns.
_CHOICE_STORE: dict[str, dict[str, Any]] = {}


def _key(tenant_id: str, conversation_id: str, choice_set_id: str) -> str:
    return f"{tenant_id}:{conversation_id}:{choice_set_id}"


def make_choice_set(
    *,
    tenant_id: str,
    conversation_id: str,
    choices: list[ChatChoice],
    ttl_seconds: int = 3600,
) -> dict[str, Any]:
    if len(choices) > 3:
        choices = choices[:3]
    choice_set_id = f"chs_{uuid.uuid4().hex[:12]}"
    payload = {
        "choice_set_id": choice_set_id,
        "choices": [c.to_dict() for c in choices],
        "expires_at": time.time() + ttl_seconds,
        "consumed": False,
    }
    _CHOICE_STORE[_key(tenant_id, conversation_id, choice_set_id)] = payload
    return payload


def resolve_choice(
    *,
    tenant_id: str,
    conversation_id: str,
    choice_set_id: str,
    choice_id: str,
) -> dict[str, Any]:
    row = _CHOICE_STORE.get(_key(tenant_id, conversation_id, choice_set_id))
    if not row:
        return {"ok": False, "error": "choice_not_found_or_expired"}
    if row.get("consumed"):
        return {"ok": False, "error": "choice_already_used"}
    if float(row.get("expires_at") or 0) < time.time():
        return {"ok": False, "error": "choice_expired"}
    match = None
    for c in row.get("choices") or []:
        if str(c.get("id")) == choice_id:
            match = c
            break
    if match is None:
        return {"ok": False, "error": "invalid_choice_id"}
    row["consumed"] = True
    return {"ok": True, "choice": match, "choice_set_id": choice_set_id}


def setup_tone_choices() -> list[ChatChoice]:
    return [
        ChatChoice(id="tone_warm", label="Warm and friendly", action="setup_set_tone", payload={"tone": "warm"}),
        ChatChoice(id="tone_pro", label="Professional", action="setup_set_tone", payload={"tone": "professional"}),
        ChatChoice(id="tone_short", label="Short and direct", action="setup_set_tone", payload={"tone": "short"}),
    ]


def price_import_choices(*, extraction_id: str) -> list[ChatChoice]:
    return [
        ChatChoice(
            id="import_all",
            label="Add all as draft",
            action="price_import_apply",
            payload={"mode": "all", "extraction_id": extraction_id},
        ),
        ChatChoice(
            id="import_review",
            label="Review and edit",
            action="price_import_review",
            payload={"mode": "review", "extraction_id": extraction_id},
        ),
        ChatChoice(
            id="import_skip",
            label="Do not add",
            action="price_import_skip",
            payload={"mode": "skip", "extraction_id": extraction_id},
        ),
    ]


def setup_continue_choices(*, section: str) -> list[ChatChoice]:
    return [
        ChatChoice(id="setup_continue", label="Continue", action="setup_continue", payload={"section": section}),
        ChatChoice(id="setup_skip", label="Skip for now", action="setup_skip", payload={"section": section}),
        ChatChoice(id="setup_open_cm", label="Open AI Setup", action="open_route", payload={"route": "cm"}),
    ]


def choices_from_tool_result(name: str, data: dict[str, Any]) -> list[ChatChoice]:
    if name == "setup_next_step":
        section = str((data or {}).get("section") or "basics")
        if (data or {}).get("ask_tone"):
            return setup_tone_choices()
        return setup_continue_choices(section=section)
    if name == "extract_price_list":
        eid = str((data or {}).get("extraction_id") or (data or {}).get("attachment_id") or "unknown")
        return price_import_choices(extraction_id=eid)
    return []
