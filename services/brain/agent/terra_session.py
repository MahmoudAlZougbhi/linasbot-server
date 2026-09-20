"""Execute allowlisted Terra tool_calls inside one conversation session."""

from __future__ import annotations

import json
from typing import Any

from services.brain.agent.terra_request_round import _merge_tool_extra, _persist_profile
from services.brain.agent.terra_tools import assistant_tool_message, openai_customer_tools, parse_tool_calls
from services.brain.budgets import DEFAULT_BUDGETS
from services.brain.contracts.turn import CustomerTurn
from services.brain.facts.structured import facts_from_tool_data
from services.brain.tools.registry import execute_tool

_PROFILE_TOOLS = {"start_request", "update_request_draft"}


async def _complete(
    turn: CustomerTurn,
    messages: list[dict[str, Any]],
    *,
    attempt: int,
    tool_choice: str | None,
) -> Any:
    from services.billing.membership.provider_expense import record_pending_provider
    from services.brain.billing import operation_id_for_turn
    from services.brain.llm_core_service import create_chat_completion
    from services.brain.providers.config import answer_model

    op = operation_id_for_turn(turn)
    suffix = "" if attempt == 0 else f":r{attempt}"
    record_pending_provider(
        event_id=f"llm:{op}{suffix}",
        tenant_id=turn.tenant_id,
        category="llm_generation",
        feature="followup" if turn.invocation_kind == "followup" else "customer_chat",
        provider="openai",
        model=answer_model(),
        operation_id=op,
    )
    kwargs: dict[str, Any] = {
        "model": answer_model(),
        "messages": messages,
        "max_tokens": 700,
        "tools": openai_customer_tools(),
    }
    if tool_choice is not None:
        kwargs["tool_choice"] = tool_choice
    return await create_chat_completion(**kwargs)


async def _run_one_tool(
    turn: CustomerTurn,
    *,
    name: str,
    args: dict[str, Any],
    message: str,
    extra: dict[str, Any],
    skip: set[str],
    snapshot: dict[str, Any],
) -> dict[str, Any]:
    payload = dict(args)
    payload.setdefault("customer_text", message)
    payload.setdefault("task_id", "terra")
    if name in skip:
        return {"ok": False, "error": "tool_not_allowed_this_turn", "data": None}
    if name in {"check_setup_resources", "list_resources"}:
        extra_ids = list((turn.extra or {}).get("evidence_source_ids") or extra.get("evidence_source_ids") or [])
        if extra_ids and "source_ids" not in payload:
            payload["source_ids"] = extra_ids
    result = await execute_tool(name, payload, turn)
    _merge_tool_extra(extra, result)
    if name in _PROFILE_TOOLS:
        _persist_profile(turn, payload, snapshot)
    return result


def _receipt_lines(name: str, result: dict[str, Any], task_id: str, turn: CustomerTurn) -> list[str]:
    lines: list[str] = []
    if result.get("receipt"):
        receipt = result["receipt"]
        lines.append(
            f"{receipt.get('action_type')}:{receipt.get('state')}:{receipt.get('backend_id') or receipt.get('reason')}"
        )
    elif result.get("ok") and result.get("data") is not None:
        lines.append(f"tool:{name}:ok")
        for fact in facts_from_tool_data(name, result.get("data"), tenant_id=turn.tenant_id, task_id=task_id):
            lines.append(f"fact:{fact.kind}:{fact.entity_id}:{fact.value}")
    return lines


async def run_terra_tool_loop(
    turn: CustomerTurn,
    *,
    messages: list[dict[str, Any]],
    message: str,
    extra: dict[str, Any],
    skip: set[str],
    snapshot: dict[str, Any],
    trace: list[dict[str, Any]],
    budget: int,
    max_rounds: int | None = None,
) -> tuple[str, dict[str, Any], list[str], list[dict[str, Any]], int]:
    """Loop until Terra returns final text or budgets are exhausted."""
    receipts: list[str] = []
    rows: list[dict[str, Any]] = []
    used = 0
    llm_calls = 0
    rounds = max(1, DEFAULT_BUDGETS.max_agent_steps if max_rounds is None else int(max_rounds))
    text = ""
    for _round in range(rounds):
        try:
            response = await _complete(turn, messages, attempt=llm_calls, tool_choice="auto")
        except Exception:
            break
        llm_calls += 1
        extra["terra_llm_calls"] = llm_calls
        choice = response.choices[0].message
        text = str(getattr(choice, "content", None) or "").strip()
        calls = parse_tool_calls(choice)
        if not calls:
            break
        messages.append(assistant_tool_message(text, calls))
        text = ""
        for call in calls:
            if used >= budget:
                trace.append({"step": "TOOL", "reason": "budget_exhausted", "tool_calls": used})
                break
            name = str(call.get("tool") or "")
            args = dict(call.get("args") or {})
            used += 1
            result = await _run_one_tool(
                turn, name=name, args=args, message=message, extra=extra, skip=skip, snapshot=snapshot
            )
            rows.append({"tool": name, "ok": result.get("ok"), "error": result.get("error"), "source": "terra"})
            trace.append({"step": "TOOL", "tool": name, "ok": result.get("ok"), "source": "terra"})
            receipts.extend(_receipt_lines(name, result, str(args.get("task_id") or "terra"), turn))
            payload = {k: result.get(k) for k in ("ok", "error", "data", "receipt") if k in result}
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": call["id"],
                    "content": json.dumps(payload, ensure_ascii=False, default=str)[:4000],
                }
            )
            if extra.get("awaiting_confirmation"):
                from services.brain.agent.request_snapshot import build_request_snapshot

                turn.extra = {**dict(turn.extra or {}), **extra}
                snapshot = build_request_snapshot(turn)
                extra["request_state"] = snapshot
        turn.extra = {**dict(turn.extra or {}), **extra}
    extra["terra_llm_calls"] = llm_calls
    extra["tool_calls"] = list(extra.get("tool_calls") or []) + rows
    return text, extra, receipts, rows, llm_calls


async def repair_rewrite(
    turn: CustomerTurn,
    messages: list[dict[str, Any]],
    *,
    feedback: str,
    llm_calls: int,
) -> tuple[str, int]:
    messages.append({"role": "user", "content": feedback})
    try:
        response = await _complete(turn, messages, attempt=llm_calls, tool_choice="none")
    except Exception:
        return "", llm_calls
    llm_calls += 1
    try:
        text = str(response.choices[0].message.content or "").strip()
    except Exception:
        text = ""
    return text, llm_calls
