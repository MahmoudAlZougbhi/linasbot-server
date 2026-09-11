"""P1 Customer Brain: grounding, coverage, repair, BM25, visual clarify, localization."""

from __future__ import annotations

import pytest

from services.customer_ai.budgets import DEFAULT_BUDGETS
from services.customer_ai.contracts.evidence import EvidenceBundle, EvidenceItem
from services.customer_ai.contracts.plan import PlannerPlan, PlannerTask
from services.customer_ai.contracts.turn import CustomerTurn, MediaView
from services.customer_ai.coverage import coverage_ok
from services.customer_ai.evals.golden_pack_linas import run_golden_pack_linas
from services.customer_ai.grounding.facts import evidence_supports_text, ungrounded_amounts, ungrounded_claims
from services.customer_ai.providers.spaces import spaces_snapshot
from services.customer_ai.retrieve.cards import cards_from_sections
from services.customer_ai.retrieve.lexical import bm25_scores, search_cards, tokenize
from services.customer_ai.templates import brain_template
from services.customer_ai.test_lab import run_lab_verification_exercises
from services.customer_ai.visual import visual_retrieval_decision


def _bundle(*texts: str) -> EvidenceBundle:
    items = [
        EvidenceItem(
            evidence_id=f"services:item{index}",
            source_family="services",
            source_id=f"item{index}",
            title="Service",
            text=text,
        )
        for index, text in enumerate(texts)
    ]
    return EvidenceBundle(items=items, outcome="found")


def test_ungrounded_claims_covers_money_hours_phone_url_stock_booking() -> None:
    bundle = _bundle(
        "Hair Removal\n99.0 USD\nmonday: 10:00–18:00\nCall +961 1 234 567\nhttps://example.com/menu\nin stock"
    )
    reply = (
        "Hair is 250 USD. We open at 03:00. Call +961 9 999 999. "
        "See https://evil.example/x. Out of stock. Your appointment is confirmed."
    )
    claims = ungrounded_claims(reply, bundle)
    joined = " ".join(claims)
    assert any(item.startswith("amount:") for item in claims)
    assert "hours:" in joined
    assert any(item.startswith("phone:") for item in claims)
    assert any(item.startswith("url:") for item in claims)
    assert any(item.startswith("stock:") for item in claims)
    assert any(item.startswith("booking:") for item in claims)
    assert evidence_supports_text(reply, bundle) is False
    assert ungrounded_amounts("Hair is 250 USD", bundle) == ["250|usd"]
    ok_reply = "Hair Removal is 99.0 USD. monday 10:00. Call +961 1 234 567. https://example.com/menu in stock"
    assert evidence_supports_text(ok_reply, bundle) is True


def test_empty_evidence_fail_closed() -> None:
    empty = EvidenceBundle(items=[])
    assert ungrounded_claims("We open at 10:00", empty) == ["evidence:empty"]
    assert evidence_supports_text("We open at 10:00", empty) is False


def test_coverage_rejects_answered_without_quality_reply() -> None:
    plan = PlannerPlan(tasks=[PlannerTask(id="t1", type="information", source_families=["services"])])
    assert coverage_ok("price?", plan, {"t1": "answered"}, reply_text="99 USD", decision="reply") is True
    assert coverage_ok("price?", plan, {"t1": "answered"}, reply_text="", decision="reply") is False
    assert coverage_ok("price?", plan, {"t1": "answered"}, reply_text="x", decision="no_reply") is False
    assert coverage_ok("price?", plan, {"t1": "answered"}, reply_text="x", decision="clarify") is False


@pytest.mark.asyncio
async def test_generate_repair_then_fail_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    assert DEFAULT_BUDGETS.repair_attempts == 1
    from services.customer_ai.generate import reply as reply_mod

    calls: list[int] = []

    async def fake_ask(*, turn, prompt, attempt):
        calls.append(attempt)
        return "Laser is 999 USD"

    monkeypatch.setattr(reply_mod, "_ask_model", fake_ask)
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    turn = CustomerTurn(tenant_id="lab", conversation_id="c1", event_ids=["m1"])
    plan = PlannerPlan(tasks=[PlannerTask(id="t1", type="information", source_families=["services"])])
    bundle = _bundle("Laser\n99.0 USD")
    out = await reply_mod.generate_grounded_reply(
        turn=turn,
        message="price?",
        plan=plan,
        bundle=bundle,
        identity=None,
        destination="dm",
    )
    assert out is not None
    assert out.decision == "clarify"
    assert out.messages == []
    assert calls == [0, 1]


@pytest.mark.asyncio
async def test_generate_empty_evidence_no_model_call(monkeypatch: pytest.MonkeyPatch) -> None:
    from services.customer_ai.generate import reply as reply_mod

    async def boom(*, turn, prompt, attempt):
        raise AssertionError("model must not run without evidence")

    monkeypatch.setattr(reply_mod, "_ask_model", boom)
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    turn = CustomerTurn(tenant_id="lab", conversation_id="c1", event_ids=["m1"])
    out = await reply_mod.generate_grounded_reply(
        turn=turn,
        message="price?",
        plan=PlannerPlan(tasks=[]),
        bundle=EvidenceBundle(items=[]),
        identity=None,
        destination="dm",
    )
    assert out is not None
    assert out.decision == "clarify"
    assert out.used_evidence_ids == []


def test_bm25_ranks_relevant_card_higher() -> None:
    sections = {
        "prices": {
            "catalog": [
                {"id": "hair", "labels": {"en": "Hair Removal laser"}, "active": True},
                {"id": "botox", "labels": {"en": "Botox injection"}, "active": True},
            ]
        }
    }
    cards = cards_from_sections(sections)
    hits = search_cards(cards, "hair removal", families={"services"}, limit=2)
    assert hits
    assert hits[0].card.item_id == "services:hair"
    scores = bm25_scores(tokenize("hair removal"), [tokenize(card.search_text) for card in cards])
    assert max(scores) > 0


def test_spaces_snapshot_excludes_active_knowledge_document() -> None:
    snap = spaces_snapshot()
    assert "knowledge_document" not in snap
    assert snap.get("knowledge_reserved") == "voyage-context-4"
    assert "entity_document" in snap


@pytest.mark.asyncio
async def test_visual_disabled_image_returns_localized_clarify(monkeypatch: pytest.MonkeyPatch) -> None:
    from services.customer_ai import turn_pipeline as pipeline

    async def _no_confirm(*_args, **_kwargs):
        return None

    monkeypatch.setattr(pipeline, "try_confirm_pending", _no_confirm)
    turn = CustomerTurn(
        tenant_id="lab",
        conversation_id="c1",
        event_ids=["m1"],
        media=MediaView(image_media_id="img-1"),
        extra={"response_language": "ar"},
    )
    visual = visual_retrieval_decision(has_authorized_asset_id=False, requires_visual_reading=True)
    assert visual.reason == "disabled"
    result = await pipeline.run_dm_after_gates(turn, message="what is this?", channel="web_chat")
    assert result.envelope.decision == "clarify"
    assert result.envelope.messages
    assert result.envelope.messages[0].text == brain_template("visual_disabled", "ar")


def test_localization_handoff_and_confirm() -> None:
    assert brain_template("handoff", "en") != brain_template("handoff", "ar")
    assert "confirm" in brain_template("confirm_request", "en").lower()
    assert brain_template("faq_ambiguous", "fr")


def test_golden_pack_and_lab_exercises() -> None:
    golden = run_golden_pack_linas()
    assert golden["ok"] is True
    assert golden["live_spend"] is False
    report = run_lab_verification_exercises(tenant_id="lab")
    assert report["live_send"] is False
    assert any(item["id"] == "confirmation_copy" for item in report["exercises"])
