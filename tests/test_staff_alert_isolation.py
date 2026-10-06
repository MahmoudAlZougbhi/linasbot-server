"""Staff takeover alerts stay on the tenant that owns the customer."""

from __future__ import annotations

import pytest

from services.live_chat.staff_alert_numbers import load_staff_alerts, parse_e164_list, save_staff_alerts


@pytest.fixture()
def alerts_db(monkeypatch: pytest.MonkeyPatch, tmp_path):
    import services.live_chat.staff_alert_numbers as store
    from db.session import reset_engine_for_tests

    monkeypatch.setenv("LINAS_WHATSAPP_ALLOW_SQLITE", "true")
    monkeypatch.setenv("LINAS_WHATSAPP_DATABASE_URL", f"sqlite:///{tmp_path}/alerts.sqlite")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    store._READY = False
    reset_engine_for_tests()
    yield
    store._READY = False
    reset_engine_for_tests()


def test_local_numbers_are_not_given_a_country_prefix() -> None:
    assert parse_e164_list("03000000, 96170000004") == []
    assert parse_e164_list("+96170000004, +14155550100") == ["+96170000004", "+14155550100"]


def test_staff_numbers_do_not_cross_tenants(alerts_db) -> None:
    del alerts_db
    save_staff_alerts("tenant-a", ["+96170000004"], template_name="staff_alert", template_language="en")
    save_staff_alerts("tenant-b", ["+14155550100"], template_name="other", template_language="en")
    assert load_staff_alerts("tenant-a")["numbers"] == ["+96170000004"]
    assert load_staff_alerts("tenant-b")["numbers"] == ["+14155550100"]
    assert load_staff_alerts("")["numbers"] == []


@pytest.mark.asyncio
async def test_handoff_does_not_use_the_global_sender(alerts_db, monkeypatch: pytest.MonkeyPatch) -> None:
    del alerts_db
    from services.live_chat.human_takeover_notification_service import HumanTakeoverNotificationService

    called = {"global": False}

    async def _boom(*_args, **_kwargs):
        called["global"] = True
        raise AssertionError("global template sender")

    monkeypatch.setattr(
        "services.integrations.whatsapp.cloud_template_service.whatsapp_cloud_template_service.send_template_message",
        _boom,
    )

    def _dashboard(*_args, **_kwargs):
        return {"id": "alert"}

    monkeypatch.setattr(
        "services.owner_copilot.owner_alert_service.owner_alert_service.emit_handoff",
        _dashboard,
    )
    result = await HumanTakeoverNotificationService().notify_and_audit_handoff(
        user_id="user-1",
        user_gender="unknown",
        customer_name="Customer",
        customer_phone="+10000000000",
        escalation_reason="customer_requested_human",
        last_message="hello",
        trigger_source="test",
        tenant_id="tenant-a",
    )
    assert called["global"] is False
    assert result["notification_result"]["success"] is False
    assert result["owner_alert_id"] == "alert"
