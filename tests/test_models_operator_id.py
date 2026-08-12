"""Fail-closed: FeedbackRequest / TakeoverRequest require explicit operator_id."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from modules.models import FeedbackRequest, TakeoverRequest


def test_takeover_request_requires_operator_id() -> None:
    with pytest.raises(ValidationError):
        TakeoverRequest(conversation_id="c1", user_id="u1")


def test_takeover_request_accepts_explicit_operator_id() -> None:
    req = TakeoverRequest(conversation_id="c1", user_id="u1", operator_id="op-real")
    assert req.operator_id == "op-real"


def test_feedback_request_requires_operator_id() -> None:
    with pytest.raises(ValidationError):
        FeedbackRequest(
            conversation_id="c1",
            message_id="m1",
            user_question="q",
            bot_response="a",
            feedback_type="wrong",
        )


def test_feedback_request_no_operator_001_default() -> None:
    req = FeedbackRequest(
        conversation_id="c1",
        message_id="m1",
        user_question="q",
        bot_response="a",
        feedback_type="wrong",
        operator_id="session-user",
    )
    assert req.operator_id == "session-user"
    assert req.operator_id != "operator_001"
