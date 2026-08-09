"""Owner alert service — truthful handoff / sentiment / social human signals."""

from __future__ import annotations

from pathlib import Path

from services import owner_alert_service as mod
from services.owner_alert_service import (
    TYPE_CUSTOMER_ANGRY,
    TYPE_HUMAN_REQUEST,
    TYPE_OFFENSIVE_LANGUAGE,
    OwnerAlertService,
    build_titles,
)
from services.owner_alert_store import OwnerAlertStore


def test_build_titles_instagram_human_request() -> None:
    titles = build_titles(alert_type=TYPE_HUMAN_REQUEST, customer_name="Sara", channel="instagram")
    assert "Sara" in titles["en"]
    assert "Instagram" in titles["en"]
    assert "requested human" in titles["en"]
    assert "إنستغرام" in titles["ar"]


def test_emit_and_list_and_dedupe(tmp_path: Path) -> None:
    store = OwnerAlertStore(root=tmp_path / "alerts")
    svc = OwnerAlertService()
    original = mod.owner_alert_store
    mod.owner_alert_store = store
    try:
        first = svc.emit_social_human_request(
            tenant_id="t1",
            customer_name="Sara",
            user_id="instagram:99",
            conversation_id="c1",
            channel="instagram",
            last_message="بدي احكي مع حدا",
        )
        assert first is not None
        assert first["type"] == TYPE_HUMAN_REQUEST
        second = svc.emit_social_human_request(
            tenant_id="t1",
            customer_name="Sara",
            user_id="instagram:99",
            conversation_id="c1",
            channel="instagram",
            last_message="بدي موظف",
        )
        assert second is None  # deduped
        items = store.list_alerts(tenant_id="t1")
        assert len(items) == 1
        assert store.unread_count(tenant_id="t1") == 1
        store.mark_read(tenant_id="t1", alert_id=first["id"])
        assert store.unread_count(tenant_id="t1") == 0
    finally:
        mod.owner_alert_store = original


def test_sentiment_only_anger_or_offensive(tmp_path: Path) -> None:
    store = OwnerAlertStore(root=tmp_path / "alerts")
    svc = OwnerAlertService()
    original = mod.owner_alert_store
    mod.owner_alert_store = store
    try:
        none = svc.emit_sentiment_signal(
            tenant_id="t1",
            customer_name="A",
            user_id="u1",
            conversation_id="c1",
            sentiment_analysis={
                "should_escalate": True,
                "detected_issues": ["confusion_detected"],
                "escalation_reason": "customer_confused",
            },
            last_message="مش فاهم",
        )
        assert none is None
        angry = svc.emit_sentiment_signal(
            tenant_id="t1",
            customer_name="A",
            user_id="u1",
            conversation_id="c2",
            channel="whatsapp",
            sentiment_analysis={
                "should_escalate": True,
                "detected_issues": ["anger_detected"],
                "escalation_reason": "customer_angry",
            },
            last_message="3asab",
        )
        assert angry is not None
        assert angry["type"] == TYPE_CUSTOMER_ANGRY
        offense = svc.emit_sentiment_signal(
            tenant_id="t1",
            customer_name="A",
            user_id="u1",
            conversation_id="c3",
            sentiment_analysis={
                "should_escalate": True,
                "detected_issues": ["offensive_language"],
                "escalation_reason": "offensive_language_detected",
            },
            last_message="fuck",
        )
        assert offense is not None
        assert offense["type"] == TYPE_OFFENSIVE_LANGUAGE
    finally:
        mod.owner_alert_store = original
