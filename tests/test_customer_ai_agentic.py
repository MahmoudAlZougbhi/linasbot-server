"""Customer Brain agentic runtime: multi-round, coverage, tools, normalize, budgets."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from services.customer_ai.agent.multi_retrieve import multi_round_retrieve
from services.customer_ai.agent.normalize_query import normalize_query
from services.customer_ai.agent.rewrite import rewrite_queries
from services.customer_ai.agent.task_coverage import evaluate_task_coverage, missing_tasks
from services.customer_ai.budgets import DEFAULT_BUDGETS, TurnBudgets
from services.customer_ai.contracts.evidence import EvidenceBundle, EvidenceItem
from services.customer_ai.contracts.plan import PlannerPlan, PlannerTask, TaskSpan
from services.customer_ai.contracts.turn import CustomerTurn, HistorySnapshot
from services.customer_ai.tools.registry import execute_tool
from services.customer_ai.verify.critic import verify_answer


def _plan(*tasks: PlannerTask) -> PlannerPlan:
    return PlannerPlan(tasks=list(tasks), read_only=True)


def _task(
    task_id: str, task_type: str = "information", *, families: list[str] | None = None, span: str = ""
) -> PlannerTask:
    return PlannerTask(
        id=task_id,
        type=task_type,  # type: ignore[arg-type]
        span=TaskSpan(text=span or task_id),
        source_families=list(families or ["knowledge"]),  # type: ignore[arg-type]
    )


def _turn(tenant_id: str = "t1") -> CustomerTurn:
    return CustomerTurn(tenant_id=tenant_id, conversation_id="c1", channel="instagram_dm", history=HistorySnapshot())


def _item(eid: str, family: str = "knowledge", text: str = "Laser is available at published rates.") -> EvidenceItem:
    return EvidenceItem(
        evidence_id=eid,
        source_family=family,  # type: ignore[arg-type]
        source_id=eid.split(":", 1)[-1],
        title=eid,
        text=text,
    )


@pytest.mark.asyncio
async def test_multi_round_stops_early_when_covered() -> None:
    plan = _plan(_task("t1", "information", families=["knowledge"], span="laser"))
    turn = _turn()
    found = EvidenceBundle(items=[_item("knowledge:laser")], outcome="found")
    calls = {"n": 0}

    async def _retrieve(ctx):
        calls["n"] += 1
        return found

    with patch("services.customer_ai.agent.multi_retrieve.retrieve_published", new=AsyncMock(side_effect=_retrieve)):
        bundle, trace, _facts = await multi_round_retrieve(turn, plan, "laser price?", max_rounds=3)
    assert bundle.outcome == "found"
    assert any(row.get("reason") == "early_stop_covered" for row in trace)
    assert calls["n"] == 1


@pytest.mark.asyncio
async def test_task_coverage_missing_blocks_invent() -> None:
    plan = _plan(_task("hours1", "hours", families=["hours"], span="antelias"))
    empty = EvidenceBundle(items=[], outcome="not_found")
    coverage = evaluate_task_coverage(plan, empty, {})
    assert coverage["hours1"] == "missing"
    assert missing_tasks(plan, coverage) == ["hours1"]
    verdict = await verify_answer(
        reply_text="Antelias is open until 10pm every day.",
        plan=plan,
        bundle=empty,
        structured_facts={},
    )
    assert verdict.verdict == "FAIL"
    assert "hours1" in verdict.missing_tasks
    assert "invent" in verdict.repair_instruction.lower() or "unavailable" in verdict.repair_instruction.lower()


@pytest.mark.asyncio
async def test_tool_unknown_rejected() -> None:
    turn = _turn()
    result = await execute_tool("delete_all_customers", {"id": "x"}, turn)
    assert result["ok"] is False
    assert result["error"] == "unknown_tool"


def test_normalize_arabizi() -> None:
    out = normalize_query("se3er laser antelyas")
    assert "سعر" in out["primary"] or any("سعر" in alt for alt in out["alternates"])
    assert "antelias" in out["primary"] or any("antelias" in alt for alt in out["alternates"])


@pytest.mark.asyncio
async def test_rewrite_preserves_price_numbers() -> None:
    out = await rewrite_queries("is full body still 120 USD?", [], language="en")
    assert "120" in out["rewritten"]
    assert "USD" in out["rewritten"].upper() or "usd" in out["rewritten"].lower() or "120" in out["original"]


@pytest.mark.asyncio
async def test_budget_exhaustion() -> None:
    assert DEFAULT_BUDGETS.max_retrieval_rounds == 3
    assert DEFAULT_BUDGETS.max_agent_steps == 6
    assert DEFAULT_BUDGETS.max_tool_calls == 8
    assert DEFAULT_BUDGETS.verifier_repairs == 1
    plan = _plan(
        _task("a", "information", families=["knowledge"], span="laser"),
        _task("b", "hours", families=["hours"], span="beirut"),
    )
    turn = _turn()
    empty = EvidenceBundle(items=[], outcome="not_found")
    with patch(
        "services.customer_ai.agent.multi_retrieve.retrieve_published",
        new=AsyncMock(return_value=empty),
    ):
        bundle, trace, _facts = await multi_round_retrieve(turn, plan, "laser hours beirut?", max_rounds=2)
    assert bundle.outcome == "not_found"
    rounds = {row.get("round") for row in trace if row.get("round")}
    assert max(rounds) <= 2
    # No early_stop_covered when still missing.
    assert not any(row.get("reason") == "early_stop_covered" for row in trace)
    # Frozen budget object remains bounded.
    budgets = TurnBudgets()
    assert budgets.max_retrieval_rounds == 3
    assert budgets.extra_retrieval_rounds == 2
