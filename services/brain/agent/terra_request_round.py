"""Terra tool-calling round for requests. Same answer model; no separate planner call."""

from __future__ import annotations

from typing import Any

from services.brain.agent.request_snapshot import build_request_snapshot
from services.brain.contracts.turn import CustomerTurn
from services.brain.profile.store import remember_profile

REQUEST_TOOLS = (
    "get_request_state",
    "start_request",
    "update_request_draft",
    "submit_request",
    "cancel_request",
    "escalate_to_human",
    "no_request_action",
)


def _schema(name: str, description: str, extra_props: dict[str, Any] | None = None) -> dict[str, Any]:
    props = {
        "task_id": {"type": "string"},
        "customer_text": {"type": "string"},
        **(extra_props or {}),
    }
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {"type": "object", "properties": props, "additionalProperties": True},
        },
    }


def openai_request_tools() -> list[dict[str, Any]]:
    return [
        _schema("get_request_state", "Refresh collected vs remaining vs active/expired request state."),
        _schema(
            "start_request",
            "Start a new ORDER or APPOINTMENT only when no pending/active draft of that type exists. "
            "If one exists, call update_request_draft. Do not use for HUMAN.",
            {
                "request_type": {"type": "string", "enum": ["ORDER", "APPOINTMENT", "OTHER"]},
                "title": {"type": "string"},
            },
        ),
        _schema(
            "update_request_draft",
            "Fill or correct collected_fields on the same pending draft. Never start a second draft.",
            {"fields": {"type": "object"}, "draft_id": {"type": "string"}},
        ),
        _schema("submit_request", "Submit the active ORDER/APPOINTMENT after the customer confirms."),
        _schema("cancel_request", "Cancel the active draft."),
        _schema(
            "escalate_to_human",
            "Runtime Live Chat handoff after you author customer wording from owner HUMAN hints. "
            "Do not paste the hint as a canned script. Never a Requests board card.",
        ),
        _schema(
            "no_request_action",
            "Call when this inbound is another topic. Keep the pending draft. Do not chase missing fields.",
        ),
    ]


def _persist_profile(turn: CustomerTurn, args: dict[str, Any], snapshot: dict[str, Any]) -> None:
    raw_fields = args.get("fields")
    fields = dict(raw_fields) if isinstance(raw_fields, dict) else {}
    raw_collected = fields.get("collected_fields")
    collected = dict(raw_collected) if isinstance(raw_collected, dict) else {}
    for key in ("name", "customer_name", "gender", "age", "phone"):
        if key in args and key not in collected:
            collected[key] = args[key]
    required = {str(item) for item in (snapshot.get("required_fields") or []) if str(item).strip()}
    request_type = str(args.get("request_type") or fields.get("request_type") or snapshot.get("active_kind") or "")
    if request_type and not required:
        from services.brain.agent.request_snapshot import required_fields_for_type

        required = set(
            required_fields_for_type(turn.tenant_id, request_type, list(snapshot.get("published_rules") or []))
        )
    remember_profile(
        turn.tenant_id,
        turn.customer_id or "",
        collected,
        required=required,
        conversation_id=turn.conversation_id,
    )


def _merge_tool_extra(extra: dict[str, Any], result: dict[str, Any]) -> None:
    raw_data = result.get("data")
    data = raw_data if isinstance(raw_data, dict) else {}
    if data.get("awaiting_confirmation"):
        extra["awaiting_confirmation"] = True
        extra["pending_actions"] = list(data.get("pending_actions") or extra.get("pending_actions") or [])
    if result.get("receipt"):
        extra["receipts"] = list(extra.get("receipts") or []) + [result["receipt"]]


def hydrate_request_snapshot(turn: CustomerTurn) -> dict[str, Any]:
    """Load pending drafts + request_state into turn.extra. No LLM."""
    try:
        from services.brain.conversation_store import load_conversation

        stored = load_conversation(turn.tenant_id, turn.conversation_id) or {}
        pending = list(stored.get("pending") or [])
        if pending:
            turn.extra = {**dict(turn.extra or {}), "pending_actions": pending}
    except Exception:
        pass
    snapshot = build_request_snapshot(turn)
    extra = {"request_state": snapshot}
    turn.extra = {**dict(turn.extra or {}), **extra}
    return extra


async def run_terra_request_round(*_a: Any, **_k: Any) -> tuple[list[dict[str, Any]], list[str], int, dict[str, Any]]:
    raise RuntimeError("dead path: customer inbound uses run_terra_turn")
