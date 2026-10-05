"""Platform-owner turns against one tenant's live Terra and Sol.

The conversation id is a lab thread, so the tenant's message balance is not charged.
"""

from __future__ import annotations

import uuid
from typing import Any

LAB_PREFIX = "lab:platform:"


def lab_conversation_id(*, actor_user_id: str, tenant_id: str, brain: str) -> str:
    actor = (actor_user_id or "owner").strip() or "owner"
    return f"{LAB_PREFIX}{actor}:{tenant_id}:{brain}"


def known_tenant_id(tenant_id: str) -> str:
    tid = (tenant_id or "").strip()
    if not tid or len(tid) > 80 or any(ch in tid for ch in "/\\\n\r"):
        raise ValueError("unknown_tenant")
    from services.team.user_service import user_service

    if not user_service.get_users_for_tenant(tid):
        raise ValueError("unknown_tenant")
    return tid


def prior_turns(history: list[dict[str, Any]] | None) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for item in history or []:
        if not isinstance(item, dict):
            continue
        role = str(item.get("role") or "").strip().lower()
        text = str(item.get("text") or item.get("content") or "").strip()
        if role not in {"user", "assistant"} or not text:
            continue
        rows.append({"role": role, "text": text[:4000]})
    return rows[-20:]


async def customer_lab_turn(
    *,
    actor_user_id: str,
    tenant_id: str,
    message: str,
    history: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    tid = known_tenant_id(tenant_id)
    text = (message or "").strip()
    if not text:
        raise ValueError("empty_message")
    from services.brain.reply.orchestrator import run_customer_reply_v2_dm

    prior = prior_turns(history)
    conversation_id = lab_conversation_id(actor_user_id=actor_user_id, tenant_id=tid, brain="customer")
    outcome = await run_customer_reply_v2_dm(
        tenant_id=tid,
        message=text[:4000],
        channel="instagram_dm",
        user_id=f"platform-lab:{actor_user_id or 'owner'}",
        conversation_id=conversation_id,
        message_id=f"lab-{uuid.uuid4().hex}",
        injected_history=[
            {"id": f"prior-{index}", "role": row["role"], "text": row["text"]} for index, row in enumerate(prior)
        ],
        apply_customer_usage_limits=False,
    )
    reply = str(getattr(outcome, "reply", None) or "").strip()
    reason = str(getattr(outcome, "reason", None) or "").strip()
    return {
        "tenant_id": tid,
        "brain": "customer",
        "reply": reply,
        "reason": reason,
        "stopped": bool(getattr(outcome, "stop", False) and not reply),
    }


async def copilot_lab_turn(
    *,
    actor_user_id: str,
    tenant_id: str,
    message: str,
    history: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    tid = known_tenant_id(tenant_id)
    text = (message or "").strip()
    if not text:
        raise ValueError("empty_message")
    from services.owner_copilot.brain_run import run_owner_turn_v2

    prior = prior_turns(history)
    messages = [{"role": row["role"], "content": row["text"]} for row in prior]
    messages.append({"role": "user", "content": text[:4000]})
    conversation_id = lab_conversation_id(actor_user_id=actor_user_id, tenant_id=tid, brain="copilot")
    result = await run_owner_turn_v2(
        tenant_id=tid,
        user_id=f"platform-lab:{actor_user_id or 'owner'}",
        role="owner",
        conversation_id=conversation_id,
        user_text=text[:4000],
        messages=messages,
        confirm_tool=None,
    )
    reply = str(getattr(result, "reply_text", None) or "").strip()
    route = getattr(result, "route", None)
    reason = ""
    if isinstance(route, dict):
        reason = str(route.get("reason") or route.get("code") or "").strip()
    pending = str(getattr(result, "pending_confirmation", None) or "").strip()
    return {
        "tenant_id": tid,
        "brain": "copilot",
        "reply": reply,
        "reason": reason,
        "pending_confirmation": pending,
        "stopped": not reply and bool(reason),
    }
