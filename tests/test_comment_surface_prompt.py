"""Public-comment surface contract in Terra compose. No keyword gates."""

from __future__ import annotations

from services.brain.comments.public_request_policy import comment_request_policy_notes
from services.brain.comments.surface_prompt import (
    COMMENT_SURFACE_BLOCK,
    comment_surface_block,
    comment_surface_policy_notes,
    comment_system_addon,
    is_comment_generate_surface,
    merge_policy_notes,
)
from services.brain.comments.thread_parent import JOINER_POLICY_NOTE
from services.brain.compose.blocks import compose_evidence_context, compose_user_prompt, system_prompt
from services.brain.contracts.evidence import EvidenceBundle, EvidenceItem
from services.brain.contracts.turn import CustomerTurn, HistorySnapshot, VisibleMessage
from tests.plan_builders import explicit_plan


def _bundle() -> EvidenceBundle:
    return EvidenceBundle(
        outcome="found",
        items=[
            EvidenceItem(
                evidence_id="e1",
                source_family="hours",
                title="Hours",
                text="Open 10-8",
                source_id="hours-1",
                revision="1",
            )
        ],
    )


def _prompt(*, turn: CustomerTurn, message: str = "hours?", plan=None) -> str:
    plan = plan or explicit_plan(message, ("information", ["knowledge"]))
    notes = merge_policy_notes(
        comment_surface_policy_notes(turn),
        comment_request_policy_notes(turn, plan),
        [str(item) for item in (turn.extra or {}).get("policy_notes") or []],
    )
    context = compose_evidence_context(
        identity=None,
        plan=plan,
        bundle=_bundle(),
        policy_notes=notes or None,
        surface=str(turn.surface or ""),
        invocation_kind=str(turn.invocation_kind or ""),
    )
    history = [f"{item.role}: {item.text}" for item in turn.history.messages]
    return compose_user_prompt(
        context=context,
        history_lines=history,
        message=message,
        language_rule="Reply in language code `en`.",
    )


def test_comment_surface_prompt_contains_public_contract() -> None:
    turn = CustomerTurn(
        tenant_id="t1",
        surface="comment",
        invocation_kind="comment",
        channel="instagram_comment",
        extra={"comment_mode": "ai_comment"},
        history=HistorySnapshot(messages=[VisibleMessage(id="c0", role="user", text="hi there")]),
    )
    prompt = _prompt(turn=turn)
    assert "COMMENT_SURFACE" in prompt
    assert COMMENT_SURFACE_BLOCK.splitlines()[1] in prompt
    assert "PUBLIC social comment" in prompt
    assert prompt.index("COMMENT_SURFACE") < prompt.index("HISTORY")
    assert "1-3 short sentences" in prompt
    assert "Not a private DM" in prompt or "NOT a private DM" in prompt
    sys_prompt = system_prompt(surface="comment", invocation_kind="comment")
    assert "PUBLIC social comment" in sys_prompt
    assert comment_system_addon(turn) != ""
    assert is_comment_generate_surface(turn) is True


def test_dm_surface_prompt_does_not_claim_public_comment() -> None:
    turn = CustomerTurn(
        tenant_id="t1",
        surface="dm",
        invocation_kind="dm",
        channel="instagram_dm",
        extra={"comment_mode": ""},
    )
    prompt = _prompt(turn=turn, message="what are your hours?")
    assert "COMMENT_SURFACE" not in prompt
    assert "PUBLIC social comment" not in prompt
    assert comment_surface_block(turn) == ""
    assert "PUBLIC social comment" not in system_prompt()
    assert is_comment_generate_surface(turn) is False


def test_greeting_compose_skips_comment_surface() -> None:
    context = compose_evidence_context(
        identity=None,
        plan=explicit_plan("hi", ("acknowledgement", ["knowledge"])),
        bundle=EvidenceBundle(outcome="not_found"),
        greeting_turn=True,
        surface="comment",
        invocation_kind="comment",
    )
    assert "COMMENT_SURFACE" not in context


def test_ai_comment_order_keeps_invite_dm_and_no_pii_notes() -> None:
    turn = CustomerTurn(
        tenant_id="t1",
        surface="comment",
        invocation_kind="comment",
        channel="instagram_comment",
        extra={"comment_mode": "ai_comment"},
    )
    plan = explicit_plan("I want to book", ("service_request", ["services"]))
    notes = comment_request_policy_notes(turn, plan)
    blob = " ".join(notes).lower()
    assert "invite" in blob
    assert "dm" in blob
    assert "pii" in blob
    prompt = _prompt(turn=turn, message="I want to book", plan=plan)
    assert "invite the customer to continue in dm" in prompt.lower() or "invite the customer to dm" in prompt.lower()
    assert "pii" in prompt.lower()


def test_thread_parent_note_reaches_policy() -> None:
    turn = CustomerTurn(
        tenant_id="t1",
        surface="comment",
        invocation_kind="comment",
        extra={"comment_mode": "ai_comment", "parent_is_page": True},
    )
    notes = comment_surface_policy_notes(turn)
    assert JOINER_POLICY_NOTE in notes
    prompt = _prompt(turn=turn)
    assert "Answer this customer only" in prompt


def test_tiktok_never_claims_private_send() -> None:
    turn = CustomerTurn(
        tenant_id="t1",
        surface="comment",
        invocation_kind="comment",
        channel="tiktok_comment",
        extra={"comment_mode": "ai_comment"},
    )
    notes = comment_surface_policy_notes(turn)
    assert any("TikTok" in note and "Never claim a private message" in note for note in notes)


def test_merge_policy_notes_dedupes() -> None:
    twice = "AI comment mode=ai_comment. Public comment text only."
    assert merge_policy_notes([twice, twice], [twice]) == [twice]


def test_comment_history_is_thread_not_private_dm() -> None:
    from services.brain.comments.dm_bridge import merge_comment_history_into_dm
    from services.brain.contracts.reply import FinalReplyEnvelope, OutboundMessage, TurnResult
    from services.brain.conversation_history import load_stored_history_rows, record_turn_history
    from services.brain.conversation_store import reset_conversation_store_for_tests

    reset_conversation_store_for_tests()
    turn = CustomerTurn(
        tenant_id="hist-shop",
        customer_id="u1",
        conversation_id="comment:hist-shop:instagram_comment:p1:u1",
        channel="instagram_comment",
        surface="comment",
        extra={"post_id": "p1"},
    )
    record_turn_history(
        turn,
        inbound_id="c1",
        inbound_text="public question",
        result=TurnResult(
            stop_reason="ok",
            envelope=FinalReplyEnvelope(
                decision="reply",
                messages=[
                    OutboundMessage(destination="comment", text="public reply"),
                    OutboundMessage(destination="dm", text="secret private hours"),
                ],
            ),
        ),
        comment_surface=True,
    )
    rows = load_stored_history_rows("hist-shop", turn.conversation_id)
    texts = [str(row.get("text") or "") for row in rows]
    assert "public question" in texts
    assert "public reply" in texts
    assert "secret private hours" not in texts
    comment_history, notes = merge_comment_history_into_dm(
        turn.history,
        tenant_id="hist-shop",
        user_id="u1",
        channel="instagram_comment",
    )
    assert notes == []
    assert comment_history is turn.history
