"""Published tenant dynamic messages are the only customer copy."""

from __future__ import annotations

from services.ai_setup.schemas import DynamicMessageRecord, DynamicMessagesSection
from services.owner_copilot.dynamic_messages_service import get_dynamic_message, get_tenant_dynamic_message


def test_missing_tenant_message_is_silent(monkeypatch) -> None:
    monkeypatch.setattr("services.brain.greeting_policy.load_dynamic_messages", lambda _tid: None)
    assert get_tenant_dynamic_message("tenant-a", "waiting_queue_message", "ar") == ""
    assert get_dynamic_message("waiting_queue_message", "ar") == ""


def test_tenant_message_is_that_tenants_text(monkeypatch) -> None:
    section = DynamicMessagesSection(
        items=[
            DynamicMessageRecord(
                id="waiting_queue_message",
                en="One moment from tenant A",
                ar="لحظة من التينانت",
            )
        ]
    )
    monkeypatch.setattr(
        "services.brain.greeting_policy.load_dynamic_messages", lambda tid: section if tid == "tenant-a" else None
    )
    assert get_tenant_dynamic_message("tenant-a", "waiting_queue_message", "en") == "One moment from tenant A"
    assert get_tenant_dynamic_message("tenant-b", "waiting_queue_message", "en") == ""
    assert "شوي، منكون معك" not in get_tenant_dynamic_message("tenant-a", "waiting_queue_message", "ar")
