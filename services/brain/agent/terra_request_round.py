"""Terra tool-calling round for requests. Same answer model; no separate planner call."""

from __future__ import annotations

import json
from typing import Any

from services.brain.agent.request_snapshot import build_request_snapshot
from services.brain.contracts.turn import CustomerTurn
from services.brain.generate.reply import openai_configured
from services.brain.profile.store import remember_profile
from services.brain.tools.registry import execute_tool

REQUEST_TOOLS = (
    "get_request_state",
    "start_request",
    "update_request_draft",
    "submit_request",
    "cancel_request",
    "escalate_to_human",
    "no_request_action",
)

_ACTION_TOOLS = frozenset(REQUEST_TOOLS) - {"get_request_state"}


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
            "Start a new ORDER or APPOINTMENT draft. Do not use for HUMAN.",
            {
                "request_type": {"type": "string", "enum": ["ORDER", "APPOINTMENT", "OTHER"]},
                "title": {"type": "string"},
            },
        ),
        _schema(
            "update_request_draft",
            "Correct or fill collected_fields on the active draft.",
            {"fields": {"type": "object"}, "draft_id": {"type": "string"}},
        ),
        _schema("submit_request", "Submit the active ORDER/APPOINTMENT after the customer confirms."),
        _schema("cancel_request", "Cancel the active draft."),
        _schema(
            "escalate_to_human",
            "Live Chat handoff after you may speak the owner HUMAN hint. Never a Requests board card.",
        ),
        _schema(
            "no_request_action",
            "Call when this inbound is not a new/resume ORDER, APPOINTMENT, or HUMAN handoff.",
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


async def _llm_round(turn: CustomerTurn, message: str, snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    from services.brain.llm_core_service import create_chat_completion
    from services.brain.providers.config import answer_model

    payload = {
        "inbound": message,
        "request_state": {
            k: snapshot.get(k)
            for k in (
                "active_kind",
                "pending_confirmation",
                "active_drafts",
                "past_requests",
                "required_fields",
                "profile_confirm",
                "distinction",
                "nag_policy",
            )
        },
        "published_rules": snapshot.get("published_rules_block") or "",
    }
    response = await create_chat_completion(
        model=answer_model(),
        messages=[
            {
                "role": "system",
                "content": (
                    "You are the tenant customer assistant deciding request tools only. "
                    "Call start_request / update_request_draft / submit_request / cancel_request / "
                    "escalate_to_human, or no_request_action. Do not write the customer reply here."
                ),
            },
            {"role": "user", "content": json.dumps(payload, ensure_ascii=False)[:6000]},
        ],
        max_tokens=400,
        tools=openai_request_tools(),
        tool_choice="required",
    )
    choice = response.choices[0].message
    calls: list[dict[str, Any]] = []
    for item in list(getattr(choice, "tool_calls", None) or []):
        fn = getattr(item, "function", None)
        name = str(getattr(fn, "name", "") or "")
        raw = str(getattr(fn, "arguments", "") or "{}")
        try:
            args = json.loads(raw) if raw else {}
        except Exception:
            args = {}
        if not isinstance(args, dict):
            args = {}
        if name in REQUEST_TOOLS:
            calls.append({"tool": name, "args": args})
    return calls


async def run_terra_request_round(
    turn: CustomerTurn,
    message: str,
    *,
    budget: int,
    trace: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[str], int, dict[str, Any]]:
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
    rows: list[dict[str, Any]] = [{"tool": "get_request_state", "ok": True, "source": "system"}]
    receipts = [f"request_state:{snapshot.get('active_kind') or 'none'}"]
    if not snapshot.get("module_enabled"):
        return rows, receipts, 0, extra
    proposals: list[dict[str, Any]] = []
    if openai_configured():
        try:
            proposals = await _llm_round(turn, message, snapshot)
        except Exception:
            proposals = []
        if not any(item.get("tool") in _ACTION_TOOLS for item in proposals):
            try:
                proposals = await _llm_round(turn, message, snapshot)
            except Exception:
                proposals = [{"tool": "no_request_action", "args": {}}]
        if not any(item.get("tool") in _ACTION_TOOLS for item in proposals):
            proposals = [{"tool": "no_request_action", "args": {}}]
    used = 0
    for proposal in proposals:
        if used >= budget:
            trace.append({"step": "TOOL", "reason": "budget_exhausted", "tool_calls": used})
            break
        name = str(proposal.get("tool") or "")
        args = dict(proposal.get("args") or {})
        args.setdefault("customer_text", message)
        args.setdefault("task_id", "terra")
        used += 1
        result = await execute_tool(name, args, turn)
        rows.append({"tool": name, "ok": result.get("ok"), "error": result.get("error"), "source": "terra"})
        trace.append({"step": "TOOL", "tool": name, "ok": result.get("ok"), "source": "terra"})
        _merge_tool_extra(extra, result)
        if name in {"start_request", "update_request_draft"}:
            _persist_profile(turn, args, snapshot)
        if result.get("receipt"):
            receipt = result["receipt"]
            receipts.append(
                f"{receipt.get('action_type')}:{receipt.get('state')}:{receipt.get('backend_id') or receipt.get('reason')}"
            )
        elif result.get("ok"):
            receipts.append(f"tool:{name}:ok")
        if extra.get("awaiting_confirmation"):
            turn.extra = {**dict(turn.extra or {}), **extra}
            snapshot = build_request_snapshot(turn)
            extra["request_state"] = snapshot
    turn.extra = {**dict(turn.extra or {}), **extra}
    return rows, receipts, used, extra
