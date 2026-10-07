"""Platform-owner turns against one tenant's live Terra and Sol.

The conversation id is a lab thread, so the tenant's message balance is not charged.
"""

from __future__ import annotations

import uuid
from typing import Any

LAB_PREFIX = "lab:platform:"

_HINTS = {
    "failed_closed": ("The live brain refused to answer (fail-closed). Check the tenant setup or turn on Test draft."),
    "unpublished": "This tenant is not published. Turn on Test draft to try the saved draft.",
    "no_draft": "Save a draft in the tenant app before testing it here.",
    "draft_model_unavailable": "The draft is saved, but the model did not answer. Publish the tenant or retry.",
}


def hint_for(reason: str, *, has_reply: bool) -> str:
    if has_reply:
        return ""
    key = (reason or "").strip() or "no_reply"
    return _HINTS.get(key) or f"The brain stopped ({key.replace('_', ' ')})."


def observe_lab_turn(*, tenant_id: str, brain: str, message: str, result: dict[str, Any]) -> None:
    """Record the lab turn. The lab must not enqueue a customer outbox send."""
    from services.owner_copilot.interaction_flow_logger import log_interaction
    from services.owner_portal.owner_traces import write_trace

    trace_brain = "owner_copilot" if brain == "copilot" else "customer"
    reply = str(result.get("reply") or "")
    reason = str(result.get("reason") or "")
    model = str(result.get("model") or "")
    write_trace(
        {
            "tenant_id": tenant_id,
            "brain": trace_brain,
            "channel": "brains_test",
            "user_message": message[:4000],
            "reply": reply,
            "model": model,
            "tokens_in": int(result.get("tokens_in") or 0),
            "tokens_out": int(result.get("tokens_out") or 0),
            "error": reason if result.get("stopped") else "",
            "steps": [{"name": "lab", "reason": reason}],
        }
    )
    log_interaction(
        f"platform-lab:{tenant_id}",
        message[:4000],
        reply,
        "brains_test",
        channel="brains_test",
        message_type="text",
        model=model or None,
        tokens=0,
        ai_called=False,
        outcome=reason or "lab",
        user_data={"tenant_id": tenant_id},
    )


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


async def _draft_reply(tenant_id: str, message: str) -> dict[str, Any]:
    from services.ai_setup.storage import get_draft

    sections = []
    for name in ("ai_basics", "knowledge", "faq"):
        try:
            envelope = get_draft(name, tenant_id=tenant_id, create_default=False)
        except Exception:
            continue
        payload = getattr(envelope, "payload", None)
        if payload:
            sections.append(f"{name}: {str(payload)[:1500]}")
    if not sections:
        return {
            "tenant_id": tenant_id,
            "brain": "customer",
            "reply": "",
            "reason": "no_draft",
            "hint": hint_for("no_draft", has_reply=False),
            "stopped": True,
        }
    draft_text = "\n".join(sections)[:5000]
    try:
        from services.brain.llm_core_service import create_chat_completion
        from services.owner_copilot.flags import owner_model_name

        response = await create_chat_completion(
            model=owner_model_name(),
            messages=[
                {"role": "system", "content": "Answer only from this unpublished draft.\n" + draft_text},
                {"role": "user", "content": message[:4000]},
            ],
            max_tokens=400,
            reasoning_effort="low",
        )
        reply = str(response.choices[0].message.content or "").strip()
    except Exception:
        reply = ""
    return {
        "tenant_id": tenant_id,
        "brain": "customer",
        "reply": reply,
        "reason": "draft_sandbox" if reply else "draft_model_unavailable",
        "hint": hint_for("draft_sandbox" if reply else "draft_model_unavailable", has_reply=bool(reply)),
        "stopped": not bool(reply),
    }


async def customer_lab_turn(
    *,
    actor_user_id: str,
    tenant_id: str,
    message: str,
    history: list[dict[str, Any]] | None = None,
    mode: str = "live",
) -> dict[str, Any]:
    tid = known_tenant_id(tenant_id)
    text = (message or "").strip()
    if not text:
        raise ValueError("empty_message")
    if mode == "draft":
        drafted = await _draft_reply(tid, text)
        observe_lab_turn(tenant_id=tid, brain="customer", message=text, result=drafted)
        return drafted
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
    stopped = bool(getattr(outcome, "stop", False) and not reply)
    result = {
        "tenant_id": tid,
        "brain": "customer",
        "reply": reply,
        "reason": reason,
        "model": str(getattr(outcome, "model", None) or ""),
        "stopped": stopped,
        "hint": hint_for(reason, has_reply=bool(reply)),
    }
    observe_lab_turn(tenant_id=tid, brain="customer", message=text, result=result)
    return result


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
    stopped = not reply and bool(reason)
    payload = {
        "tenant_id": tid,
        "brain": "copilot",
        "reply": reply,
        "reason": reason,
        "model": str(getattr(result, "model", None) or ""),
        "pending_confirmation": pending,
        "stopped": stopped,
        "hint": hint_for(reason, has_reply=bool(reply)),
    }
    observe_lab_turn(tenant_id=tid, brain="copilot", message=text, result=payload)
    return payload
