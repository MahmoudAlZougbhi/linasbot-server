"""New message policy for comments; legacy leftover path stays uncharged."""

from __future__ import annotations

import pytest

from services.customer_ai.billing import apply_message_billing, classify_result
from services.customer_ai.contracts.reply import FinalReplyEnvelope, OutboundMessage, TurnResult
from services.customer_ai.contracts.turn import CustomerTurn
from services.membership.lot_window import current_period_id
from services.membership.message_ledger import grant_lot, remaining_messages, reset_ledger_for_tests
from services.membership.message_policy import message_units_for


@pytest.fixture(autouse=True)
def _clean(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LINAS_MESSAGE_STORE", "memory")
    monkeypatch.delenv("MESSAGE_BILLING_ENABLED", raising=False)
    reset_ledger_for_tests()


def _turn(**kwargs) -> CustomerTurn:
    values = {
        "tenant_id": "cmt-shop",
        "conversation_id": "comment:cmt-shop:ig",
        "event_ids": ["cmt-1"],
        "invocation_kind": "comment",
        "surface": "comment",
    }
    values.update(kwargs)
    return CustomerTurn(**values)


def _result(*, text: str, extra: dict, ai_called: bool = False, decision: str = "reply") -> TurnResult:
    return TurnResult(
        stop_reason="ok",
        envelope=FinalReplyEnvelope(
            decision=decision,
            messages=[OutboundMessage(destination="comment", text=text)] if text else [],
        ),
        ai_called=ai_called,
        extra=extra,
    )


def test_static_and_ignore_are_zero_units() -> None:
    static = classify_result(
        _turn(), _result(text="Thanks", extra={"path": "comment_rule", "comment_mode": "static_comment"})
    )
    ignore = classify_result(
        _turn(),
        TurnResult(
            stop_reason="policy_suppressed",
            envelope=FinalReplyEnvelope(decision="no_reply"),
            extra={"path": "comment_rule", "comment_mode": "ignore"},
        ),
    )
    faq = classify_result(_turn(), _result(text="Hours 9-5", extra={"path": "faq_exact", "faq_id": "h"}))
    assert static == "static"
    assert ignore == "no_reply"
    assert faq == "faq_only"
    assert message_units_for(static) == 0
    assert message_units_for(ignore) == 0
    assert message_units_for(faq) == 0


def test_ai_comment_bundle_is_one_message() -> None:
    for mode in ("ai_comment", "ai_dm", "ai_both"):
        klass = classify_result(
            _turn(),
            _result(text="Hello", extra={"comment_mode": mode, "phase": "generate"}, ai_called=True),
        )
        assert klass == "generated_ai"
        assert message_units_for(klass) == 1


def test_mixed_faq_and_ai_comment_is_one_message() -> None:
    klass = classify_result(
        _turn(),
        _result(
            text="The facial is $40 and I can help more.",
            extra={"path": "faq_exact", "faq_id": "p1", "faq_used": True, "comment_mode": "ai_comment"},
            ai_called=True,
        ),
    )
    assert klass == "mixed_faq_ai"
    assert message_units_for(klass) == 1


def test_legacy_comments_stay_uncharged_when_billing_off() -> None:
    result = apply_message_billing(
        _turn(),
        _result(text="Hello", extra={"comment_mode": "ai_comment", "phase": "generate"}, ai_called=True),
    )
    assert result.extra["legacy_comment_uncharged"] is True
    assert result.extra["billing_policy"] == "legacy_credits"
    assert remaining_messages("cmt-shop") == 0


def test_new_policy_debits_one_ai_comment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MESSAGE_BILLING_ENABLED", "true")
    monkeypatch.setattr("services.customer_ai.billing.ensure_included_grant", lambda _tid: None)
    grant_lot(tenant_id="cmt-shop", lot_id="inc", kind="included", period_id=current_period_id(), amount=5)
    result = apply_message_billing(
        _turn(),
        _result(text="Hello", extra={"comment_mode": "ai_both", "phase": "generate"}, ai_called=True),
    )
    assert result.extra["legacy_comment_uncharged"] is False
    assert result.extra["billing_policy"] == "message_units"
    assert result.extra["message_units"] == 1
    assert remaining_messages("cmt-shop") == 4
