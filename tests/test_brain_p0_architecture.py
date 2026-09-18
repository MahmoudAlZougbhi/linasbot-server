"""P0 architecture: greeting route, entity identity, grounding, tenant-generic context."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from services.brain.catalog_intent import is_catalog_list
from services.brain.contracts.evidence import EvidenceBundle, EvidenceItem
from services.brain.contracts.plan import PlannerPlan, PlannerTask, TaskSpan
from services.brain.contracts.reply import FinalReplyEnvelope, OutboundMessage, TurnResult
from services.brain.contracts.turn import CustomerTurn
from services.brain.conversation_resolve import resolve_followup_query
from services.brain.entity_identity import prefer_standalone, score_label
from services.brain.greeting import is_greeting_only
from services.brain.grounding.facts import ungrounded_claims
from services.brain.planner.heuristic import plan_message
from services.brain.retrieve.conflict import apply_authority
from services.brain.tools.price_match import rank_price_rows


def _item(**kwargs) -> EvidenceItem:
    payload = {
        "evidence_id": "services:underarms",
        "source_family": "services",
        "source_id": "underarms",
        "title": "Underarms",
        "text": "Underarms 15 USD",
        "extra": {"entity_id": "underarms", "amount": 15, "bundle": False},
    }
    payload.update(kwargs)
    return EvidenceItem(**payload)


def test_greeting_only_phrases() -> None:
    for text in ("Hello", "Hi", "مرحبا", "Bonjour"):
        assert is_greeting_only(text)
        plan = plan_message(text)
        assert [task.type for task in plan.tasks] == ["acknowledgement"]


def test_greeting_only_does_not_plan_price_retrieve() -> None:
    plan = plan_message("Hello")
    assert all(task.type != "information" for task in plan.tasks)
    assert not any("prices" in (task.source_families or []) for task in plan.tasks)


@pytest.mark.asyncio
async def test_greeting_route_skips_faq_and_agentic(monkeypatch: pytest.MonkeyPatch) -> None:
    from services.brain.turn_pipeline import run_dm_after_gates

    async def greet(*_a, **k):
        return TurnResult(
            stop_reason="ok",
            envelope=FinalReplyEnvelope(
                decision="reply",
                messages=[OutboundMessage(destination="instagram_dm", text="Hi there")],
            ),
            ai_called=True,
            extra={"path": "greeting_only", "retrieval_skipped": True},
        )

    monkeypatch.setattr("services.brain.agent.greeting_turn.identity_greeting_result", greet)
    monkeypatch.setattr(
        "services.brain.agent.loop.run_agentic_dm_path",
        AsyncMock(side_effect=AssertionError("no agentic")),
    )
    turn = CustomerTurn(tenant_id="t1", conversation_id="c1", extra={"response_language": "en"})
    for text in ("Hello", "Hi", "مرحبا", "Bonjour"):
        out = await run_dm_after_gates(turn, message=text, channel="instagram_dm")
        assert out.envelope.messages[0].text == "Hi there"
        assert (out.extra or {}).get("retrieval_skipped") is True


def test_standalone_beats_overlapping_bundle() -> None:
    rows = [
        {"id": "underarms", "title": "Underarms", "aliases": ["underarm"]},
        {"id": "underarms_bikini", "title": "Underarms + Bikini"},
        {"id": "haircut", "title": "Haircut"},
        {"id": "haircut_beard", "title": "Haircut + Beard"},
    ]
    winner = prefer_standalone("How much is underarm laser hair removal?", rows)
    assert winner is not None
    assert winner["id"] == "underarms"
    assert score_label("How much is underarm laser hair removal?", "Underarms + Bikini") < score_label(
        "How much is underarm laser hair removal?", "Underarms"
    )


def test_authority_keeps_distinct_entities() -> None:
    bundle = EvidenceBundle(
        items=[
            _item(),
            _item(
                evidence_id="services:underarms_bikini",
                source_id="underarms_bikini",
                title="Underarms + Bikini",
                text="Underarms + Bikini 200 USD",
                extra={"entity_id": "underarms_bikini", "amount": 200, "bundle": True},
            ),
        ],
        outcome="found",
    )
    resolved, meta = apply_authority(bundle, query="How much is underarm laser hair removal?")
    ids = {item.source_id for item in resolved.items}
    assert "underarms" in ids
    assert not any(
        row.get("reason") == "lower_authority_amount_conflict" and row.get("entity_id") == "underarms"
        for row in meta.get("decisions") or []
    )


def test_price_match_rejects_generic_tokens() -> None:
    rows = [
        {"id": "underarms", "title": "Underarms"},
        {"id": "face", "title": "Face"},
        {"id": "full_body", "title": "Full Body"},
        {"id": "underarms_bikini", "title": "Underarms + Bikini"},
    ]
    ranked = rank_price_rows("how much is laser", rows)
    assert ranked == []
    ranked = rank_price_rows("how much is underarm laser hair removal?", rows)
    assert ranked
    assert ranked[0][1]["id"] == "underarms"


def test_price_grounding_entity_plus_amount() -> None:
    bundle = EvidenceBundle(
        items=[
            _item(),
            _item(
                evidence_id="services:underarms_bikini",
                source_id="underarms_bikini",
                title="Underarms + Bikini",
                text="200 USD",
                extra={"entity_id": "underarms_bikini", "amount": 200, "bundle": True},
            ),
        ]
    )
    plan = PlannerPlan(
        tasks=[PlannerTask(id="t1", type="information", span=TaskSpan(text="price"), source_families=["prices"])],
        read_only=True,
    )
    q = "How much is underarm laser hair removal?"
    assert not ungrounded_claims("Underarm laser hair removal is 15 USD.", bundle, message=q, plan=plan)
    assert not ungrounded_claims("It is 15.", bundle, message=q, plan=plan)
    bad = ungrounded_claims("It is 200.", bundle, message=q, plan=plan)
    assert any(item.startswith("amount:") for item in bad)


def test_hours_critic_ignores_conversational_mention() -> None:
    empty = EvidenceBundle(items=[_item(title="Antelias", text="Branch in Antelias", extra={"entity_id": "antelias"})])
    assert "hours:no_hours_evidence" not in ungrounded_claims(
        "I don't have confirmed opening hours for that branch.", empty
    )
    assert "hours:no_hours_evidence" not in ungrounded_claims(
        "Which branch would you like the opening hours for?", empty
    )
    claimed = ungrounded_claims("We are open from 11 to 7.", empty)
    assert any(item.startswith("hours:") for item in claimed)


def test_catalog_list_intent_is_generic() -> None:
    assert is_catalog_list("What services do you offer?")
    assert is_catalog_list("شو خدمات الليزر اللي عندكن؟")
    assert is_catalog_list("What products do you sell?")
    plan = plan_message("What services do you offer?")
    assert any("catalog_list" in task.entity_mentions for task in plan.tasks)
    assert "laser" not in str(plan.model_dump())


def test_restaurant_followup_does_not_inherit_clinic_hardcodes() -> None:
    resolved = resolve_followup_query(
        "What vegan mains do you have?",
        [{"role": "user", "text": "What are your opening hours in Antelias?"}],
        tenant_id="bistro",
    )
    blob = f"{resolved.rewritten_query} {resolved.carry}".lower()
    assert "laser" not in blob
    assert "antelias" not in blob
    assert "hamra" not in blob


def test_faq_archived_never_matches() -> None:
    from services.ai_setup.schemas import FaqRecord, FaqSection, FaqVariant
    from services.brain.faq_exact import find_exact_faq

    section = FaqSection(
        items=[
            FaqRecord(
                qa_group_id="hours_old",
                status="archived",
                variants=[FaqVariant(language="en", question="Antelias hours?", answer="10AM-6PM")],
            )
        ]
    )
    assert find_exact_faq(section, "Antelias hours?") is None
