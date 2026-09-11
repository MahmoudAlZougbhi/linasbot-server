"""Remaining Customer Brain contract slices: gates, store, actions, comments, follow-up."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from services.cm.schemas import CommentRule, CommentsSection, RestrictedPolicy, RestrictedTopic
from services.customer_ai.actions.confirm import confirmation_valid, material_fields_changed
from services.customer_ai.actions.drafts import apply_draft_update
from services.customer_ai.actions.resources import resolve_authorized_resource, send_resource
from services.customer_ai.comments.pipeline import deterministic_comment_result, winning_comment_mode
from services.customer_ai.contracts.actions import ActionProposal, ActionProposalSet
from services.customer_ai.contracts.reply import FinalReplyEnvelope, OutboundMessage
from services.customer_ai.contracts.turn import ConversationState, CustomerTurn, MediaView
from services.customer_ai.faq_freshness import faq_static_allowed, looks_like_dynamic_fact
from services.customer_ai.followup.revalidate import revalidate_followup_send
from services.customer_ai.gates import evaluate_gates
from services.customer_ai.turn_pipeline import inbound_task_text
from services.customer_ai.outbox_test import reset_saved_outbox, save_envelope_for_test, saved_outbox
from services.customer_ai.policies.privacy import public_comment_safe
from services.customer_ai.search.invalidate import mark_products_stale
from services.customer_ai.search.store import query_similar, reset_memory_store, write_documents
from services.customer_ai.visual import visual_retrieval_decision


def test_restricted_gate_runs_before_faq(monkeypatch: pytest.MonkeyPatch) -> None:
    topic = RestrictedTopic(id="tattoo_removal", keywords=["tattoo"], active=True)
    monkeypatch.setattr(
        "services.customer_ai.policies.restricted.load_restricted_policy",
        lambda _tid: RestrictedPolicy(topics=[topic]),
    )
    monkeypatch.setattr(
        "services.customer_ai.gates.read_published_pointer",
        lambda _tid: SimpleNamespace(revision="1"),
    )
    monkeypatch.setattr("services.membership.generative_gate.generative_block_reason", lambda *_a, **_k: None)
    turn = CustomerTurn(tenant_id="t1", customer_id="u1")
    blocked = evaluate_gates(turn, apply_credits=False, message="do you do tattoo removal?")
    assert blocked.allow is False
    assert blocked.reason == "restricted"
    assert blocked.detail == "tattoo_removal"
    assert "isn't one of the services" in blocked.reply_text.lower()


def test_restricted_refuse_template_wins(monkeypatch: pytest.MonkeyPatch) -> None:
    topic = RestrictedTopic(
        id="tattoo_removal",
        keywords=["tattoo"],
        active=True,
        refuse_template="We do not offer tattoo removal.",
    )
    monkeypatch.setattr(
        "services.customer_ai.policies.restricted.load_restricted_policy",
        lambda _tid: RestrictedPolicy(topics=[topic]),
    )
    monkeypatch.setattr(
        "services.customer_ai.gates.read_published_pointer",
        lambda _tid: SimpleNamespace(revision="1"),
    )
    monkeypatch.setattr("services.membership.generative_gate.generative_block_reason", lambda *_a, **_k: None)
    blocked = evaluate_gates(
        CustomerTurn(tenant_id="t1", customer_id="u1"),
        apply_credits=False,
        message="do you do tattoo removal?",
    )
    assert blocked.reply_text == "We do not offer tattoo removal."


def test_safety_blocked_inbound_media_stops_turn(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "services.customer_ai.gates.read_published_pointer",
        lambda _tid: SimpleNamespace(revision="1"),
    )
    turn = CustomerTurn(tenant_id="t1", customer_id="u1", media=MediaView(safety_blocked=True))
    gate = evaluate_gates(turn, apply_credits=False, message="photo?")
    assert gate.allow is False
    assert gate.reason == "policy_suppressed"
    assert gate.detail == "inbound_media_blocked"


def test_conversation_store_isolates_same_conversation_id() -> None:
    from services.customer_ai.conversation_store import (
        load_conversation,
        reset_conversation_store_for_tests,
        save_conversation,
    )

    reset_conversation_store_for_tests()
    save_conversation("alpha", "shared", ConversationState(greeted=True), [])
    save_conversation("beta", "shared", ConversationState(greeted=False), [])
    assert load_conversation("alpha", "shared")["state"]["greeted"] is True
    assert load_conversation("beta", "shared")["state"]["greeted"] is False


def test_inbound_task_text_uses_transcript_and_file_extract() -> None:
    turn = CustomerTurn(
        tenant_id="t1",
        media=MediaView(transcript="said hours", extract_preview="menu.pdf: open 9-5"),
        extra={"post_caption": "Summer hours"},
        surface="comment",
    )
    text = inbound_task_text(turn, "")
    assert "said hours" in text
    assert "menu.pdf: open 9-5" in text
    assert text.startswith("Summer hours")


def test_live_human_control_blocks_turn(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("services.customer_ai.gates.live_handoff_active", lambda **_k: True)
    monkeypatch.setattr(
        "services.customer_ai.gates.read_published_pointer",
        lambda _tid: SimpleNamespace(revision="1"),
    )
    turn = CustomerTurn(tenant_id="t1", customer_id="u1")
    gate = evaluate_gates(turn, apply_credits=False, message="hi")
    assert gate.reason == "human_control"


def test_shared_redis_takeover_blocks_without_local_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    from services.customer_ai.control import live_handoff_active

    monkeypatch.setattr("services.customer_ai.control._local_takeover", lambda _uid: False)
    monkeypatch.setattr("services.scale.conversation_state_redis.get_takeover", lambda _key: True)
    monkeypatch.setattr(
        "services.scale.conversation_state_redis.shared_conv_state_fail_closed",
        lambda: False,
    )
    assert live_handoff_active(user_id="cust-1", conversation_id="c1") is True


def test_stale_stored_handoff_clears_after_release(monkeypatch: pytest.MonkeyPatch) -> None:
    from services.customer_ai.control import apply_live_control

    monkeypatch.setattr("services.customer_ai.control.live_handoff_active", lambda **_k: False)
    turn = CustomerTurn(
        tenant_id="t1",
        customer_id="u1",
        conversation_id="c1",
        state=ConversationState(handoff_active=True),
    )
    updated = apply_live_control(turn)
    assert updated.state.handoff_active is False


def test_store_never_leaks_other_tenant() -> None:
    reset_memory_store()
    rows_a = [
        {
            "id": "a:serum",
            "tenant_id": "tenant_a",
            "space_id": "space",
            "source_family": "products",
            "source_id": "serum",
            "title": "Serum",
            "search_text": "serum",
            "visible": True,
        }
    ]
    rows_b = [{**rows_a[0], "id": "b:serum", "tenant_id": "tenant_b"}]
    write_documents(None, rows_a, [[1.0, 0.0]])
    write_documents(None, rows_b, [[0.9, 0.1]])
    hits = query_similar(None, tenant_id="tenant_a", space_id="space", vector=[1.0, 0.0], limit=10)
    assert hits.outcome == "found"
    assert {item.tenant_id for item in hits.items} == {"tenant_a"}
    assert all(item.source_id == "serum" for item in hits.items)


def test_store_without_pgvector_is_typed() -> None:
    class FakeSession:
        def execute(self, *_a, **_k):
            raise RuntimeError("no vector")

    result = query_similar(FakeSession(), tenant_id="t1", space_id="space", vector=[1.0])
    assert result.outcome == "index_not_ready"


def test_send_resource_rejects_url_and_wrong_tenant(monkeypatch: pytest.MonkeyPatch) -> None:
    proposal = ActionProposal(task_id="t1", action_type="send_resource", target_id="https://evil.test/pic.jpg")
    receipt = send_resource(tenant_id="t1", proposal=proposal)
    assert receipt.state == "rejected"
    assert receipt.reason == "invented_url"

    monkeypatch.setattr(
        "services.customer_ai.actions.resources.resolve_published_resource",
        lambda **_k: {"ok": False, "error": "resource_not_found"},
    )
    missing = resolve_authorized_resource(tenant_id="t1", resource_ref="res_other")
    assert missing["ok"] is False


@pytest.mark.asyncio
async def test_execute_send_resource_pending(monkeypatch: pytest.MonkeyPatch) -> None:
    from services.customer_ai.actions.execute import execute_actions

    monkeypatch.setattr(
        "services.customer_ai.actions.resources.resolve_published_resource",
        lambda **_k: {
            "ok": True,
            "resource": {"resource_ref": "res_1", "tenant_id": "t1", "source_item_id": "knowledge:k1"},
        },
    )
    turn = CustomerTurn(tenant_id="t1", customer_id="u1")
    out = await execute_actions(
        turn=turn,
        proposals=ActionProposalSet(
            actions=[ActionProposal(task_id="media", action_type="send_resource", target_id="res_1")]
        ),
        customer_text="send the photo",
    )
    assert out.receipts[0].state == "pending"
    assert out.receipts[0].backend_id == "res_1"
    visual = visual_retrieval_decision(has_authorized_asset_id=True, requires_visual_reading=True)
    assert visual.needed is False
    assert visual.reason == "resource_by_id"


def test_material_change_invalidates_confirmation() -> None:
    assert material_fields_changed({"service": "laser", "date": "monday"}, {"service": "botox", "date": "monday"})
    assert (
        confirmation_valid(
            message_id="m1",
            customer_text="yes",
            expected_revision="draft-1",
            current_revision="draft-1",
        )
        is True
    )
    receipt = apply_draft_update(
        proposal=ActionProposal(
            task_id="d1",
            action_type="update_draft",
            expected_revision="draft-1",
            fields={"service": "botox", "previous_fields": {"service": "laser"}},
        ),
        current_revision="draft-1",
    )
    assert receipt.state == "success"
    assert receipt.reason == "confirmation_invalidated"
    assert receipt.revision != "draft-1"


def test_public_comment_does_not_claim_unsent_dm(monkeypatch: pytest.MonkeyPatch) -> None:
    section = CommentsSection(
        rules=[
            CommentRule(
                id="both",
                action="reply_comment_and_dm",
                rule_mode="deterministic",
                trigger_type="all_comments",
                keywords=[],
                reply_template="I sent you a DM 96170123456",
                dm_template="private price",
            )
        ]
    )
    monkeypatch.setattr(
        "services.customer_ai.comments.pipeline.load_published_comments_section",
        lambda _tid: section,
    )
    mode, decision = winning_comment_mode(tenant_id="t1", comment_text="price?")
    assert mode == "static_both"
    result = deterministic_comment_result(mode, decision, event_id="c1")
    assert result is not None
    public = next(item for item in result.envelope.messages if item.destination == "comment")
    private = next(item for item in result.envelope.messages if item.destination == "dm")
    assert "96170123456" not in public.text
    assert "sent you a DM" not in public.text.lower()
    assert public.depends_on == ["private"]
    assert public.idempotency_key != private.idempotency_key
    assert public_comment_safe("I sent you a DM", dm_receipt_ok=True) == "I sent you a DM"


def test_faq_dynamic_answer_needs_current_source() -> None:
    assert looks_like_dynamic_fact("10-8 daily") is True
    assert looks_like_dynamic_fact("We reply within one business day.") is False
    assert faq_static_allowed("We reply within one business day.", tenant_id="missing") is True
    assert faq_static_allowed("Laser is 99 USD", tenant_id="missing") is False


def test_followup_revalidate_and_test_outbox() -> None:
    assert revalidate_followup_send(customer_replied=True).reason == "customer_replied"
    assert revalidate_followup_send(takeover=True).reason == "human_control"
    assert revalidate_followup_send(opt_out=True).reason == "opt_out"
    assert revalidate_followup_send().allow is True
    reset_saved_outbox()
    envelope = FinalReplyEnvelope(
        decision="no_reply",
        messages=[OutboundMessage(destination="dm", text="", component_id="followup")],
    )
    saved = save_envelope_for_test(envelope)
    assert saved.persisted is True
    assert saved.sent is False
    assert len(saved_outbox()) == 1


def test_product_change_marks_index_stale() -> None:
    reset_memory_store()
    write_documents(
        None,
        [
            {
                "id": "t1:p1",
                "tenant_id": "t1",
                "space_id": "space",
                "source_family": "products",
                "source_id": "p1",
                "title": "Serum",
                "search_text": "serum",
                "visible": True,
            }
        ],
        [[1.0, 0.0]],
    )
    from services.customer_ai.search.store import activate_pointer

    activate_pointer(None, tenant_id="t1", space_id="space", source_family="products", version="v1", count=1)
    out = mark_products_stale(None, "t1")
    assert out["reason"] == "source_changed"


@pytest.mark.asyncio
async def test_rerank_skips_exact_and_keeps_fused_on_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    from services.customer_ai.retrieve.cards import TitleCard
    from services.customer_ai.retrieve.hybrid import HybridHit
    from services.customer_ai.retrieve.rerank import rerank_hits, should_rerank

    card = TitleCard(item_id="services:hair", source_family="services", title="Hair", search_text="hair")
    exact = [HybridHit(card=card, lexical_score=1.0, semantic_score=0.2, fused_rank=0)]
    assert should_rerank(exact) is False
    monkeypatch.setenv("VOYAGE_API_KEY", "sk-test")
    monkeypatch.setattr(
        "services.customer_ai.retrieve.rerank.voyage_configured",
        lambda: True,
    )

    async def boom(**_k):
        raise RuntimeError("rerank_down")

    monkeypatch.setattr("services.customer_ai.retrieve.rerank.rerank_texts", boom)
    second = TitleCard(item_id="services:botox", source_family="services", title="Botox", search_text="botox")
    fused = [
        HybridHit(card=card, lexical_score=0.4, semantic_score=0.9, fused_rank=0),
        HybridHit(card=second, lexical_score=0.3, semantic_score=0.2, fused_rank=1),
    ]
    kept = await rerank_hits("hair", fused)
    assert [item.card.item_id for item in kept] == ["services:hair", "services:botox"]


def test_index_job_does_not_claim_ready_without_pgvector(monkeypatch: pytest.MonkeyPatch) -> None:
    from services.customer_ai.search.index_job import _persist_index

    written = _persist_index(
        None,
        [
            {
                "id": "t1:s1",
                "tenant_id": "t1",
                "space_id": "space",
                "source_family": "services",
                "source_id": "s1",
                "title": "Hair",
                "search_text": "hair",
                "visible": True,
            }
        ],
        [[1.0, 0.0]],
        tenant_id="t1",
        revision="r1",
    )
    assert written["ready"] is False
    assert written["reason"] == "index_not_ready"
    _ = monkeypatch


def test_ai_both_comment_uses_public_placeholder() -> None:
    from services.customer_ai.comments.pipeline import apply_ai_comment_destinations
    from services.customer_ai.contracts.reply import TurnResult

    generated = TurnResult(
        stop_reason="ok",
        envelope=FinalReplyEnvelope(
            decision="reply",
            messages=[OutboundMessage(destination="dm", text="Private details here.")],
        ),
        ai_called=True,
    )
    dual = apply_ai_comment_destinations(generated, "ai_both")
    dests = [item.destination for item in dual.envelope.messages]
    assert dests == ["dm", "comment"]
    assert dual.envelope.messages[1].depends_on == ["private"]
    assert "DM" in dual.envelope.messages[1].text


def test_knowledge_index_rows_are_chunked() -> None:
    from services.customer_ai.retrieve.cards import TitleCard
    from services.customer_ai.search.index_job import document_rows

    card = TitleCard(
        item_id="knowledge:hours",
        source_family="knowledge",
        title="Hours",
        search_text="hours policy",
        body="# Hours\nWe open at 10.\n\n# Returns\nNo cash refunds after 7 days.",
    )
    rows = document_rows([card], tenant_id="shop", version="v1")
    assert len(rows) >= 2
    assert all(row["source_family"] == "knowledge" for row in rows)
    assert any(row["chunk_id"] for row in rows)


def test_fixture_eval_runner_has_no_live_spend() -> None:
    from services.customer_ai.evals.runner import run_fixture_corpus

    report = run_fixture_corpus()
    assert report["live_spend"] is False
    assert report["case_count"] >= 1


def test_branch_schedule_hydrates_hours() -> None:
    from services.customer_ai.retrieve.expand import expand_ranked
    from services.customer_ai.retrieve.lexical import LexicalHit
    from services.customer_ai.retrieve.cards import TitleCard

    card = TitleCard(item_id="hours:main", source_family="hours", title="Main", search_text="hours")
    sections = {
        "branches": {
            "items": [
                {
                    "id": "main",
                    "title": "Downtown",
                    "timezone": "Asia/Beirut",
                    "weekly_hours": {"monday": {"open": "10:00", "close": "19:00"}},
                }
            ]
        }
    }
    bundle = expand_ranked([LexicalHit(card=card, score=1.0)], sections, revision="r1")
    assert bundle.items
    assert "10:00" in bundle.items[0].text
    assert "Asia/Beirut" in bundle.items[0].text or "monday" in bundle.items[0].text
