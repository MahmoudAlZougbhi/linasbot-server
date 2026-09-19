"""HUMAN owner hint reaches Terra context; runtime handoff; no false transfer claim."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from services.brain.actions.handoff import escalate_to_human
from services.brain.agent.request_policy import request_policy_notes
from services.brain.agent.request_snapshot import build_request_snapshot
from services.brain.agent.terra_request_round import openai_request_tools
from services.brain.compose.blocks import RULES_BLOCK, compose_evidence_context
from services.brain.contracts.actions import ActionProposal
from services.brain.contracts.evidence import EvidenceBundle, EvidenceItem
from services.brain.contracts.plan import PlannerPlan
from services.brain.contracts.reply import FinalReplyEnvelope, OutboundMessage, TurnResult
from services.brain.contracts.turn import CustomerTurn
from services.brain.conversation_store import reset_conversation_store_for_tests
from services.brain.generate.reply import generate_grounded_reply
from services.brain.grounding.facts import ungrounded_claims
from services.brain.grounding.handoff_claims import ungrounded_handoff_claims
from services.brain.tools.registry import execute_tool
from services.brain.turn_pipeline import run_dm_after_gates
from tests.plan_builders import explicit_plan

_OWNER_HINT = "إذا كان العميل غاضبًا، قول له راوق يا باشا وبعدها حوّله للموظف."
_PUBLISHED = {
    "module_enabled": True,
    "rules": [
        {
            "id": "h1",
            "type": "HUMAN",
            "name": "Angry customer",
            "enabled": True,
            "notes": _OWNER_HINT,
            "required_fields": [],
        }
    ],
}


@pytest.fixture(autouse=True)
def _graph(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LINAS_MESSAGE_STORE", "memory")
    reset_conversation_store_for_tests()
    monkeypatch.setattr("services.requests.config_loader.requests_capture_active", lambda *_a, **_k: True)
    monkeypatch.setattr("services.brain.agent.request_snapshot.requests_capture_active", lambda *_a, **_k: True)
    monkeypatch.setattr(
        "services.requests.config_loader.load_published_requests_config",
        lambda *_a, **_k: dict(_PUBLISHED),
    )
    yield
    reset_conversation_store_for_tests()


def _turn(cid: str = "c-human") -> CustomerTurn:
    return CustomerTurn(tenant_id="t-human", conversation_id=cid, customer_id="u-human", event_ids=["m1"])


def _bundle() -> EvidenceBundle:
    return EvidenceBundle(
        outcome="found",
        items=[
            EvidenceItem(
                evidence_id="k1",
                source_family="knowledge",
                source_id="k1",
                title="Shop",
                text="We help customers in the salon.",
            )
        ],
    )


def test_human_hint_reaches_snapshot_and_policy() -> None:
    snap = build_request_snapshot(_turn())
    assert snap["human_hints"]
    assert snap["human_hints"][0]["hint"] == _OWNER_HINT
    assert _OWNER_HINT in (snap.get("published_rules_block") or "")
    blob = "\n".join(request_policy_notes({**snap, "module_enabled": True}))
    assert "HUMAN_OWNER_HINTS" in blob
    assert _OWNER_HINT in blob
    assert "not a script to paste" in blob.lower() or "not a canned system reply" in blob.lower()
    context = compose_evidence_context(
        identity=None,
        plan=PlannerPlan(tasks=[], read_only=True),
        bundle=_bundle(),
        policy_notes=request_policy_notes({**snap, "module_enabled": True}),
        receipts=[],
    )
    assert "POLICY" in context
    assert _OWNER_HINT in context
    assert "escalate_to_human success" in RULES_BLOCK


def test_human_policy_has_no_anger_keyword_gate() -> None:
    roots = [
        Path("services/brain/agent/request_policy.py"),
        Path("services/brain/agent/request_snapshot.py"),
        Path("services/brain/agent/terra_turn.py"),
        Path("services/brain/agent/terra_request_round.py"),
        Path("services/brain/actions/handoff.py"),
        Path("services/brain/grounding/handoff_claims.py"),
    ]
    for path in roots:
        text = path.read_text(encoding="utf-8")
        assert "anger_detected" not in text
        assert "offensive_language" not in text


@pytest.mark.asyncio
async def test_terra_round_sees_hint_then_escalates(monkeypatch: pytest.MonkeyPatch) -> None:
    from types import SimpleNamespace

    from services.brain.agent.terra_turn import run_terra_turn

    seen: dict[str, Any] = {}
    calls = {"n": 0}

    async def fake_llm(*, messages, **_k: Any):
        calls["n"] += 1
        blob = str(messages)
        if _OWNER_HINT in blob:
            seen["hints"] = [{"hint": _OWNER_HINT}]
        if calls["n"] == 1:
            return SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        message=SimpleNamespace(
                            content=None,
                            tool_calls=[
                                SimpleNamespace(
                                    id="call_1",
                                    function=SimpleNamespace(
                                        name="escalate_to_human",
                                        arguments='{"task_id":"human"}',
                                    ),
                                )
                            ],
                        )
                    )
                ]
            )
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="راوق يا باشا، دقيقة.", tool_calls=None))]
        )

    async def fake_takeover(*_a: Any, **_k: Any) -> dict[str, Any]:
        seen["takeover"] = True
        return {"ok": True, "status": "waiting_human"}

    async def pass_verify(**_k: Any):
        return SimpleNamespace(verdict="PASS", unsupported_claims=[], missing_tasks=[], repair_instruction="")

    monkeypatch.setattr("services.brain.agent.terra_turn.openai_configured", lambda: True)
    monkeypatch.setattr("services.brain.llm_core_service.create_chat_completion", fake_llm)
    monkeypatch.setattr("services.billing.membership.provider_expense.record_pending_provider", lambda **_k: None)
    monkeypatch.setattr("services.brain.providers.config.answer_model", lambda: "gpt-test")
    monkeypatch.setattr("services.brain.billing.operation_id_for_turn", lambda _t: "op-h")
    monkeypatch.setattr("services.brain.identity.load_identity_bundle", lambda _tid: None)
    monkeypatch.setattr("services.brain.agent.terra_turn.verify_answer", pass_verify)
    monkeypatch.setattr("services.brain.agent.generate_path.coverage_ok", lambda *_a, **_k: True)
    monkeypatch.setattr("utils.utils_takeover.set_human_takeover_status", fake_takeover)
    turn = _turn()
    result = await run_terra_turn(
        turn,
        message="زعلان كتير من الخدمة",
        channel="whatsapp",
        dest="dm",
        plan=PlannerPlan(tasks=[], read_only=True),
        bundle=_bundle(),
        structured_facts={},
        visual_reason="",
        extra={},
        evidence=[],
        agent_trace=[],
    )
    assert seen["hints"][0]["hint"] == _OWNER_HINT
    assert any(
        row.get("tool") == "escalate_to_human" and row.get("ok") for row in (result.extra or {}).get("tool_calls") or []
    )
    assert any(
        item and item.get("action_type") == "escalate_to_human" and item.get("state") == "success"
        for item in (result.extra or {}).get("receipts") or []
    )
    assert seen.get("takeover") is True
    assert result.envelope.decision == "reply"


@pytest.mark.asyncio
async def test_escalate_failure_does_not_claim_transfer() -> None:
    receipt = await escalate_to_human(
        proposal=ActionProposal(task_id="h", action_type="escalate_to_human"),
        user_id="",
        conversation_id="",
    )
    assert receipt.state == "failure"
    lines = [f"{receipt.action_type}:{receipt.state}:{receipt.reason}"]
    lie = "I'll connect you to our staff now."
    assert ungrounded_handoff_claims(lie, lines)
    calm = "راوق يا باشا، خليني شوف شو فيني ساعدك."
    assert ungrounded_handoff_claims(calm, lines) == []


@pytest.mark.asyncio
async def test_failed_handoff_generate_does_not_send_lie(monkeypatch: pytest.MonkeyPatch) -> None:
    turn = _turn("c-fail")
    turn.extra = {
        "request_state": {**build_request_snapshot(turn), "module_enabled": True},
    }
    monkeypatch.setattr("services.brain.generate.reply.openai_configured", lambda: True)

    async def fake_ask(**_k: Any) -> str:
        return "I'll connect you to our staff now."

    monkeypatch.setattr("services.brain.generate.reply._ask_model", fake_ask)
    envelope = await generate_grounded_reply(
        turn=turn,
        message="بدي موظف",
        plan=explicit_plan("بدي موظف", ("information", ["knowledge"])),
        bundle=_bundle(),
        identity=None,
        destination="dm",
        receipts=["escalate_to_human:failure:handoff_persist_failed"],
    )
    assert envelope is not None
    assert envelope.decision == "clarify"
    assert envelope.messages == []


@pytest.mark.asyncio
async def test_success_handoff_allows_terra_wording(monkeypatch: pytest.MonkeyPatch) -> None:
    turn = _turn("c-ok")
    turn.extra = {"request_state": {**build_request_snapshot(turn), "module_enabled": True}}
    monkeypatch.setattr("services.brain.generate.reply.openai_configured", lambda: True)

    async def fake_ask(**_k: Any) -> str:
        return "راوق يا باشا — I'll connect you to our staff now."

    monkeypatch.setattr("services.brain.generate.reply._ask_model", fake_ask)
    envelope = await generate_grounded_reply(
        turn=turn,
        message="زعلان",
        plan=explicit_plan("زعلان", ("information", ["knowledge"])),
        bundle=_bundle(),
        identity=None,
        destination="dm",
        receipts=["escalate_to_human:success:c-ok"],
    )
    assert envelope is not None
    assert envelope.decision == "reply"
    text = envelope.messages[0].text if envelope.messages else ""
    assert "راوق يا باشا" in text
    assert "connect you" in text.lower()
    assert ungrounded_claims(text, _bundle(), ["escalate_to_human:success:c-ok"]) == []


@pytest.mark.asyncio
async def test_human_without_hint_still_escalates(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "services.requests.config_loader.load_published_requests_config",
        lambda *_a, **_k: {"module_enabled": True, "rules": []},
    )
    called = {"takeover": False}

    async def fake_takeover(*_a: Any, **_k: Any) -> dict[str, Any]:
        called["takeover"] = True
        return {"ok": True}

    monkeypatch.setattr("utils.utils_takeover.set_human_takeover_status", fake_takeover)
    result = await execute_tool("escalate_to_human", {"task_id": "human"}, _turn("c-bare"))
    assert result.get("ok") is True
    assert (result.get("receipt") or {}).get("state") == "success"
    assert called["takeover"] is True
    snap = build_request_snapshot(_turn("c-bare"))
    assert snap.get("human_hints") == []


@pytest.mark.asyncio
async def test_dm_path_terra_authors_then_runtime_handoff(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}

    async def fake_retrieve(*_a: Any, **_k: Any):
        return _bundle(), [], {}

    async def fake_terra(turn: CustomerTurn, **kwargs: Any) -> TurnResult:
        extra = dict(kwargs.get("extra") or turn.extra or {})
        result = await execute_tool(
            "escalate_to_human", {"task_id": "human", "customer_text": kwargs.get("message") or ""}, turn
        )
        extra["request_state"] = {**build_request_snapshot(turn), "module_enabled": True}
        extra["receipts"] = [result.get("receipt")] if result.get("receipt") else []
        turn.extra = {**dict(turn.extra or {}), **extra}
        captured["hints"] = extra["request_state"].get("human_hints")
        hints = extra["request_state"].get("human_hints") or []
        text = "راوق يا باشا، دقيقة وبحوّلك." if hints else "One moment."
        captured["terra_text"] = text
        extra.update(dict(turn.extra or {}))
        return TurnResult(
            stop_reason="ok",
            envelope=FinalReplyEnvelope(
                decision="reply",
                messages=[OutboundMessage(destination="dm", text=text)],
            ),
            extra=extra,
        )

    async def fake_takeover(*_a: Any, **_k: Any) -> dict[str, Any]:
        captured["live_chat"] = "waiting_human"
        return {"waiting_human": True}

    async def no_confirm(*_a: Any, **_k: Any):
        return None

    monkeypatch.setattr("services.brain.turn_pipeline.try_confirm_pending", no_confirm)
    monkeypatch.setattr("services.brain.turn_pipeline._exact_faq_result", lambda *_a, **_k: None)

    async def no_sem(*_a: Any, **_k: Any):
        return None

    monkeypatch.setattr("services.brain.turn_pipeline._semantic_faq_result", no_sem)
    monkeypatch.setattr("services.brain.agent.loop.reserve_generative", lambda *_a, **_k: None)
    monkeypatch.setattr("services.brain.agent.loop.multi_round_retrieve", fake_retrieve)
    monkeypatch.setattr("services.brain.agent.loop.run_terra_turn", fake_terra)
    monkeypatch.setattr("utils.utils_takeover.set_human_takeover_status", fake_takeover)
    result = await run_dm_after_gates(
        _turn("c-live"),
        message="زعلان كتير",
        channel="whatsapp",
    )
    assert captured["hints"][0]["hint"] == _OWNER_HINT
    assert "راوق يا باشا" in captured["terra_text"]
    assert result.envelope.decision == "reply"
    assert result.envelope.messages[0].text == captured["terra_text"]
    receipts = list(result.extra.get("receipts") or [])
    assert any(
        item and item.get("action_type") == "escalate_to_human" and item.get("state") == "success" for item in receipts
    )
    assert captured.get("live_chat") == "waiting_human"
    assert "I'll connect you" not in (result.envelope.reply_text or "")


def test_escalate_tool_schema_is_not_canned_copy() -> None:
    blob = str(openai_request_tools())
    assert "escalate_to_human" in blob
    assert "I'll connect you" not in blob
    assert "رح حوّلك عند واحد من موظفينا" not in blob
