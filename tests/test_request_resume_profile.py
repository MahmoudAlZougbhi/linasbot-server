"""Soft resume + profile confirm only when the request graph requires fields."""

from __future__ import annotations

import pytest

from services.brain.agent.request_snapshot import build_request_snapshot, request_policy_notes
from services.brain.contracts.turn import CustomerTurn
from services.brain.profile.store import (
    confirm_candidates,
    recall_profile,
    remember_profile,
    reset_profile_store_for_tests,
)
from services.brain.tools.registry import execute_tool


@pytest.fixture(autouse=True)
def _reset_profile() -> None:
    reset_profile_store_for_tests()
    yield
    reset_profile_store_for_tests()


def test_profile_stores_only_required_fields() -> None:
    remember_profile(
        "t1",
        "c1",
        {"name": "Ali", "age": "22", "phone": "70123456", "notes": "skip"},
        required={"name", "age"},
        conversation_id="conv",
    )
    stored = recall_profile("t1", "c1", conversation_id="conv")
    assert stored["name"] == "Ali"
    assert stored["age"] == "22"
    assert "phone" not in stored
    assert confirm_candidates(stored, {"name"}) == {"name": "Ali"}
    assert confirm_candidates(stored, set()) == {}


def test_snapshot_distinguishes_new_resume_and_expired() -> None:
    turn = CustomerTurn(tenant_id="t1", conversation_id="c-resume", customer_id="u1", extra={})
    turn.extra = {
        "pending_actions": [
            {
                "action_type": "start_request",
                "fields": {
                    "request_type": "APPOINTMENT",
                    "title": "Laser",
                    "collected_fields": {"name": "Ibrahim", "age": ""},
                },
            }
        ]
    }
    snap = build_request_snapshot(turn)
    pending = snap["pending_confirmation"]
    assert pending
    assert pending[0]["request_type"] == "APPOINTMENT"
    assert pending[0]["kind"] == "resume_active"
    assert pending[0]["collected"]["name"] == "Ibrahim"
    assert "age" in pending[0]["missing_fields"]
    notes = request_policy_notes({**snap, "module_enabled": True})
    blob = "\n".join(notes)
    assert "answer_other_topics_first" in blob or "answer that question first" in blob.lower()
    assert "new ORDER" in blob
    assert "expired" in blob.lower()


@pytest.mark.asyncio
async def test_correction_updates_collected_fields() -> None:
    from services.brain.conversation_store import reset_conversation_store_for_tests

    reset_conversation_store_for_tests()
    turn = CustomerTurn(tenant_id="t1", conversation_id="c-fix", customer_id="u1", event_ids=["m1"])
    await execute_tool(
        "start_request",
        {
            "request_type": "APPOINTMENT",
            "title": "Laser",
            "fields": {"request_type": "APPOINTMENT", "collected_fields": {"name": "Ibrahim"}},
        },
        turn,
    )
    await execute_tool(
        "update_request_draft",
        {"fields": {"request_type": "APPOINTMENT", "collected_fields": {"name": "Ali"}}},
        turn,
    )
    snap = build_request_snapshot(turn)
    pending = snap["pending_confirmation"]
    assert pending
    assert pending[0]["collected"].get("name") == "Ali"


def test_optional_fields_are_not_force_stored() -> None:
    remember_profile("t1", "u2", {"gender": "male"}, required=set(), conversation_id="c2")
    assert recall_profile("t1", "u2", conversation_id="c2") == {}
