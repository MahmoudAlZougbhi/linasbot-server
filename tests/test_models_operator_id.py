"""Fail-closed: TakeoverRequest requires explicit operator_id."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from modules.models import TakeoverRequest


def test_takeover_request_requires_operator_id() -> None:
    with pytest.raises(ValidationError):
        TakeoverRequest(conversation_id="c1", user_id="u1")


def test_takeover_request_accepts_explicit_operator_id() -> None:
    req = TakeoverRequest(conversation_id="c1", user_id="u1", operator_id="op-real")
    assert req.operator_id == "op-real"
    assert req.operator_id != "operator_001"
