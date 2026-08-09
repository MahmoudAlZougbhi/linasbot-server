"""Backend-authoritative in-chat cards for Owner Copilot V2."""

from __future__ import annotations

import time
import uuid
from typing import Any

from services.owner_copilot_v2.models import ChatCard


def _id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def proposal_card(
    *,
    title: str,
    body: str,
    proposal_id: str,
    preview: dict[str, Any] | None = None,
    confirmation_token: str | None = None,
) -> ChatCard:
    return ChatCard(
        id=_id("card"),
        kind="proposal",
        title=title,
        body=body,
        status="pending_approval",
        data={
            "proposal_id": proposal_id,
            "preview": preview or {},
            "confirmation_token": confirmation_token,
            "created_at": time.time(),
        },
    )


def diagnosis_card(*, title: str, body: str, diagnosis: dict[str, Any]) -> ChatCard:
    return ChatCard(
        id=_id("card"),
        kind="diagnosis",
        title=title,
        body=body,
        status="ready",
        data={"diagnosis": diagnosis, "created_at": time.time()},
    )


def progress_card(*, title: str, body: str = "", step: str = "") -> ChatCard:
    return ChatCard(
        id=_id("card"),
        kind="progress",
        title=title,
        body=body,
        status="running",
        data={"step": step, "created_at": time.time()},
    )


def success_card(*, title: str, body: str, data: dict[str, Any] | None = None) -> ChatCard:
    return ChatCard(
        id=_id("card"),
        kind="success",
        title=title,
        body=body,
        status="done",
        data={**(data or {}), "created_at": time.time()},
    )


def failure_card(*, title: str, body: str, error: str) -> ChatCard:
    return ChatCard(
        id=_id("card"),
        kind="failure",
        title=title,
        body=body,
        status="failed",
        data={"error": error, "created_at": time.time()},
    )


def price_list_import_card(*, extraction: dict[str, Any], attachment_id: str) -> ChatCard:
    return ChatCard(
        id=_id("card"),
        kind="price_list_import",
        title="Price list import",
        body=str(extraction.get("summary") or "Review extracted prices before saving as Draft."),
        status="pending_review",
        data={
            "attachment_id": attachment_id,
            "extraction": extraction,
            "created_at": time.time(),
        },
    )


def setup_card(*, stage: str, section: str, body: str) -> ChatCard:
    return ChatCard(
        id=_id("card"),
        kind="setup",
        title="Setup",
        body=body,
        status="active",
        data={"stage": stage, "section": section, "created_at": time.time()},
    )


def card_from_tool(name: str, data: dict[str, Any], *, ok: bool) -> ChatCard | None:
    if name == "propose_cm_patch" and isinstance(data, dict) and data.get("proposal_id"):
        preview = data.get("preview") if isinstance(data.get("preview"), dict) else {}
        return proposal_card(
            title="Content Management change",
            body="Review the proposed change, then approve to save.",
            proposal_id=str(data["proposal_id"]),
            preview=preview,
            confirmation_token=str(data.get("confirmation_token") or "") or None,
        )
    if name == "diagnose_meta_health" and ok:
        return diagnosis_card(
            title="Instagram / Facebook health",
            body=str((data or {}).get("summary") or "Diagnosis ready."),
            diagnosis=data or {},
        )
    if name == "extract_price_list" and ok:
        return price_list_import_card(
            extraction=data or {},
            attachment_id=str((data or {}).get("attachment_id") or ""),
        )
    if name == "setup_next_step" and ok:
        return setup_card(
            stage=str((data or {}).get("setup_stage") or ""),
            section=str((data or {}).get("section") or ""),
            body=str((data or {}).get("prompt") or "Continue setup in this chat."),
        )
    if not ok:
        return failure_card(
            title=f"Tool failed: {name}", body="No changes were applied.", error=str(data.get("error") or name)
        )
    return None
