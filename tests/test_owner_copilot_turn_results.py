"""Focused coverage for Owner Copilot V2 terminal-result handling."""

from __future__ import annotations

from typing import Any

import pytest

from services.owner_copilot_v2.models import OwnerV2TurnResult
from services.owner_copilot_v2.turn_results import owner_result_from_done_payload, record_owner_v2_usage


def test_owner_result_from_done_payload_preserves_public_fields() -> None:
    result = owner_result_from_done_payload(
        {
            "reply_text": "Done",
            "tool_calls": [{"name": "read_cm"}],
            "cards": [{"kind": "success"}],
            "choices": [{"id": "continue"}],
            "pending_confirmation": "confirm-1",
            "proposed_patch": {"proposal_id": "proposal-1"},
            "route": {"kind": "owner_v2"},
            "context_tokens": 321,
            "setup_stage": "cm_partial",
            "quick_actions": [{"id": "cm", "label": "Continue Setup"}],
            "model": "gpt-5.6-sol",
        }
    )

    assert result == OwnerV2TurnResult(
        reply_text="Done",
        tool_calls=[{"name": "read_cm"}],
        cards=[{"kind": "success"}],
        choices=[{"id": "continue"}],
        pending_confirmation="confirm-1",
        proposed_patch={"proposal_id": "proposal-1"},
        route={"kind": "owner_v2"},
        context_tokens=321,
        setup_stage="cm_partial",
        quick_actions=[{"id": "cm", "label": "Continue Setup"}],
        model="gpt-5.6-sol",
    )


def test_record_owner_v2_usage_preserves_usage_shape(monkeypatch: pytest.MonkeyPatch) -> None:
    recorded: dict[str, Any] = {}

    def capture_usage(**kwargs: Any) -> None:
        recorded.update(kwargs)

    monkeypatch.setattr("services.owner_ai_model_router.owner_chat_usage_tracker.record", capture_usage)

    record_owner_v2_usage(
        {"tenant_id": "tenant-1", "user_id": "owner-1", "conversation_id": "conversation-1"},
        OwnerV2TurnResult(reply_text="abcdefgh", context_tokens=123, model="gpt-5.6-sol"),
    )

    assert recorded["tenant_id"] == "tenant-1"
    assert recorded["user_id"] == "owner-1"
    assert recorded["conversation_id"] == "conversation-1"
    assert recorded["prompt_tokens"] == 123
    assert recorded["completion_tokens"] == 2
    assert recorded["meta"] == {"source": "owner_copilot_v2", "ok": True}
    assert recorded["route"].kind == "owner_help"
    assert recorded["route"].model == "gpt-5.6-sol"
    assert recorded["route"].reason == "owner_copilot_v2"
