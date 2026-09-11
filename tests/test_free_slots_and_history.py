"""Free slot caps and WhatsApp history mapping — flags stay off unless set."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from services.membership.free_slots import SlotLimitError, assert_cm_section_slots


def test_free_slots_off_by_default() -> None:
    assert_cm_section_slots(
        "anyone",
        "branches",
        {"items": [{"id": "a"}, {"id": "b"}]},
        current_payload={"items": []},
    )


def test_free_branch_and_service_caps(monkeypatch: pytest.MonkeyPatch) -> None:
    from services.entitlements_service import entitlements_store

    monkeypatch.setenv("FREE_PLAN_ENFORCEMENT_ENABLED", "true")
    entitlements_store.set_plan(tenant_id="free-slots", plan_id="free", status="active", source="admin")
    assert_cm_section_slots(
        "free-slots",
        "branches",
        {"items": [{"id": "a"}]},
        current_payload={"items": []},
    )
    with pytest.raises(SlotLimitError) as exc:
        assert_cm_section_slots(
            "free-slots",
            "branches",
            {"items": [{"id": "a"}, {"id": "b"}]},
            current_payload={"items": [{"id": "a"}]},
        )
    assert exc.value.code == "FREE_SLOT_LIMIT"
    assert_cm_section_slots(
        "free-slots",
        "branches",
        {"items": []},
        current_payload={"items": [{"id": "a"}, {"id": "b"}]},
    )
    with pytest.raises(SlotLimitError):
        assert_cm_section_slots(
            "free-slots",
            "services",
            {"items": [{"id": str(i)} for i in range(6)]},
            current_payload={"items": [{"id": str(i)} for i in range(5)]},
        )


def test_whatsapp_history_maps_roles() -> None:
    from services.customer_ai.history_whatsapp import rows_from_wa_messages

    rows = rows_from_wa_messages(
        [
            SimpleNamespace(id="1", direction="inbound", content_preview="hi", meta={}, created_at=None),
            SimpleNamespace(
                id="2", direction="outbound", content_preview="hello", meta={"text": "full"}, created_at=None
            ),
        ]
    )
    assert rows[0]["role"] == "user"
    assert rows[0]["text"] == "hi"
    assert rows[1]["role"] == "assistant"
    assert rows[1]["text"] == "full"
