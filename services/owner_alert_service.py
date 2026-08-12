"""Create truthful owner alerts from real handoff / sentiment / social human signals."""

from __future__ import annotations

from typing import Any

from services.cm.constants import DEFAULT_TENANT_ID
from services.owner_alert_store import owner_alert_store

# Alert types that map to product requirements.
TYPE_HUMAN_REQUEST = "human_request"
TYPE_CUSTOMER_ANGRY = "customer_angry"
TYPE_OFFENSIVE_LANGUAGE = "offensive_language"

# Sentiment analyzer issues that should create owner alerts (existing keyword path).
_ANGER_ISSUES = frozenset({"anger_detected"})
_OFFENSE_ISSUES = frozenset({"offensive_language"})

_CHANNEL_LABELS = {
    "instagram": {"en": "Instagram", "ar": "إنستغرام"},
    "facebook": {"en": "Facebook", "ar": "فيسبوك"},
    "whatsapp": {"en": "WhatsApp", "ar": "واتساب"},
}


def _channel_key(channel: str | None, user_id: str | None = None) -> str:
    raw = str(channel or "").strip().lower()
    if raw in _CHANNEL_LABELS:
        return raw
    uid = str(user_id or "").strip().lower()
    if uid.startswith("instagram:"):
        return "instagram"
    if uid.startswith("facebook:") or uid.startswith("messenger:"):
        return "facebook"
    return "whatsapp" if uid else "whatsapp"


def _display_name(customer_name: str | None, user_id: str | None) -> str:
    name = (customer_name or "").strip()
    if name and name.lower() not in {"unknown", "user", "customer"}:
        return name
    uid = (user_id or "").strip()
    if ":" in uid:
        return uid.split(":", 1)[-1][:16] or "Customer"
    return uid[-8:] if uid else "Customer"


def build_titles(*, alert_type: str, customer_name: str, channel: str) -> dict[str, str]:
    ch_en = _CHANNEL_LABELS.get(channel, {}).get("en") or channel.title()
    ch_ar = _CHANNEL_LABELS.get(channel, {}).get("ar") or ch_en
    if alert_type == TYPE_HUMAN_REQUEST:
        return {
            "en": f"This user {customer_name} on {ch_en} requested human",
            "ar": f"المستخدم {customer_name} على {ch_ar} طلب التحدث مع موظف",
        }
    if alert_type == TYPE_OFFENSIVE_LANGUAGE:
        return {
            "en": f"This user {customer_name} on {ch_en} used offensive language",
            "ar": f"المستخدم {customer_name} على {ch_ar} استخدم لغة غير لائقة",
        }
    if alert_type == TYPE_CUSTOMER_ANGRY:
        return {
            "en": f"This user {customer_name} on {ch_en} is angry / escalated",
            "ar": f"المستخدم {customer_name} على {ch_ar} غاضب / متصاعد",
        }
    return {
        "en": f"Alert for {customer_name} on {ch_en}",
        "ar": f"تنبيه بخصوص {customer_name} على {ch_ar}",
    }


def alert_type_from_escalation_reason(reason: str | None) -> str:
    key = str(reason or "").strip().lower()
    if key in {"offensive_language_detected", "offensive_language"}:
        return TYPE_OFFENSIVE_LANGUAGE
    if key in {"customer_angry", "anger_detected", "customer_frustrated", "negative_sentiment_detected"}:
        return TYPE_CUSTOMER_ANGRY
    return TYPE_HUMAN_REQUEST


def alert_type_from_sentiment_issues(detected_issues: list[str] | None) -> str | None:
    issues = {str(i) for i in (detected_issues or [])}
    if issues & _OFFENSE_ISSUES:
        return TYPE_OFFENSIVE_LANGUAGE
    if issues & _ANGER_ISSUES:
        return TYPE_CUSTOMER_ANGRY
    return None


class OwnerAlertService:
    def emit(
        self,
        *,
        tenant_id: str | None,
        alert_type: str,
        customer_name: str | None,
        user_id: str | None,
        conversation_id: str | None,
        channel: str | None = None,
        escalation_reason: str | None = None,
        last_message: str | None = None,
        trigger_source: str | None = None,
        dedupe_seconds: float = 1800.0,
    ) -> dict[str, Any] | None:
        tid = (tenant_id or DEFAULT_TENANT_ID).strip() or DEFAULT_TENANT_ID
        atype = (alert_type or TYPE_HUMAN_REQUEST).strip() or TYPE_HUMAN_REQUEST
        if owner_alert_store.recent_duplicate(
            tenant_id=tid,
            alert_type=atype,
            conversation_id=conversation_id,
            user_id=user_id,
            within_seconds=dedupe_seconds,
        ):
            print(f"[owner_alert] dedupe skip type={atype} conv={conversation_id} user=...{str(user_id)[-4:]}")
            return None

        channel_key = _channel_key(channel, user_id)
        name = _display_name(customer_name, user_id)
        titles = build_titles(alert_type=atype, customer_name=name, channel=channel_key)
        record = owner_alert_store.create(
            tenant_id=tid,
            payload={
                "type": atype,
                "title_en": titles["en"],
                "title_ar": titles["ar"],
                "customer_name": name,
                "user_id": user_id,
                "conversation_id": conversation_id,
                "channel": channel_key,
                "escalation_reason": escalation_reason,
                "last_message": (last_message or "")[:250],
                "trigger_source": trigger_source,
                # Deep link payload for mobile Live Chat open.
                "deep_link": {
                    "screen": "livechat",
                    "user_id": user_id,
                    "conversation_id": conversation_id,
                },
            },
        )
        print(f"[owner_alert] created id={record['id']} type={atype} channel={channel_key} conv={conversation_id}")
        return record

    def emit_handoff(
        self,
        *,
        tenant_id: str | None = None,
        customer_name: str | None = None,
        user_id: str | None = None,
        conversation_id: str | None = None,
        channel: str | None = None,
        escalation_reason: str | None = None,
        last_message: str | None = None,
        trigger_source: str | None = None,
    ) -> dict[str, Any] | None:
        return self.emit(
            tenant_id=tenant_id,
            alert_type=alert_type_from_escalation_reason(escalation_reason),
            customer_name=customer_name,
            user_id=user_id,
            conversation_id=conversation_id,
            channel=channel,
            escalation_reason=escalation_reason,
            last_message=last_message,
            trigger_source=trigger_source or "handoff",
        )

    def emit_sentiment_signal(
        self,
        *,
        tenant_id: str | None = None,
        customer_name: str | None = None,
        user_id: str | None = None,
        conversation_id: str | None = None,
        channel: str | None = None,
        sentiment_analysis: dict[str, Any] | None = None,
        last_message: str | None = None,
    ) -> dict[str, Any] | None:
        """Owner alert from existing keyword sentiment analyzer (no ML invention).

        Only anger / offensive_language issues — not confusion/urgency alone.
        """
        analysis = sentiment_analysis or {}
        if not analysis.get("should_escalate"):
            return None
        atype = alert_type_from_sentiment_issues(analysis.get("detected_issues"))
        if not atype:
            return None
        return self.emit(
            tenant_id=tenant_id,
            alert_type=atype,
            customer_name=customer_name,
            user_id=user_id,
            conversation_id=conversation_id,
            channel=channel,
            escalation_reason=analysis.get("escalation_reason"),
            last_message=last_message,
            trigger_source="sentiment_keyword_analyzer",
        )

    def emit_social_human_request(
        self,
        *,
        tenant_id: str | None = None,
        customer_name: str | None = None,
        user_id: str | None = None,
        conversation_id: str | None = None,
        channel: str | None = None,
        last_message: str | None = None,
        trigger_source: str | None = None,
    ) -> dict[str, Any] | None:
        """Instagram/Facebook human request (dashboard waiting_human is blocked for social)."""
        return self.emit(
            tenant_id=tenant_id,
            alert_type=TYPE_HUMAN_REQUEST,
            customer_name=customer_name,
            user_id=user_id,
            conversation_id=conversation_id,
            channel=channel or "instagram",
            escalation_reason="customer_requested_human",
            last_message=last_message,
            trigger_source=trigger_source or "social_human_request",
        )


owner_alert_service = OwnerAlertService()
