"""Requests capture helpers: pending wording, comment safety, handoff gates."""

from __future__ import annotations

from typing import Any

from services.requests.config_loader import requests_capture_active
from services.requests.constants import SOURCE_CHANNELS

_PUBLIC_COMMENT_CHANNELS = frozenset(
    {
        "instagram_comment",
        "facebook_comment",
        "ig_comment",
        "fb_comment",
        "comment",
    }
)

_CHANNEL_TO_SOURCE: dict[str, str] = {
    "instagram": "instagram_dm",
    "instagram_dm": "instagram_dm",
    "facebook": "facebook_messenger",
    "facebook_dm": "facebook_messenger",
    "facebook_messenger": "facebook_messenger",
    "messenger": "facebook_messenger",
    "page": "facebook_messenger",
    "whatsapp": "whatsapp_cloud",
    "whatsapp_cloud": "whatsapp_cloud",
    "wa": "whatsapp_cloud",
    "comment_linked_dm": "comment_linked_dm",
}


def skip_forced_booking_wa_me(tenant_id: str | None) -> bool:
    """True when appointment/order intent must not force wa.me booking handoff."""
    return requests_capture_active(tenant_id)


def is_public_comment_channel(channel: str | None) -> bool:
    return str(channel or "").strip().lower() in _PUBLIC_COMMENT_CHANNELS


def normalize_source_channel(channel: str | None) -> str | None:
    raw = str(channel or "").strip().lower()
    if not raw:
        return None
    mapped = _CHANNEL_TO_SOURCE.get(raw, raw)
    if mapped in SOURCE_CHANNELS:
        return mapped
    return None


def appointment_pending_confirmation_message(language: str | None = None) -> str:
    """Appointment is a preference until owner Confirm — AI must say pending."""
    lang = str(language or "en").strip().lower() or "en"
    messages = {
        "ar": ("سجلت طلب الموعد كـ تفضيل. موعدك مش مؤكد بعد — بانتظار تأكيد الفريق. منخبرك لما يتأكد."),
        "en": (
            "I’ve recorded your appointment request as a preference. "
            "It is not confirmed yet — pending team confirmation. "
            "We’ll notify you once it’s confirmed."
        ),
        "fr": (
            "J’ai enregistré votre demande de rendez-vous comme préférence. "
            "Ce n’est pas encore confirmé — en attente de confirmation de l’équipe. "
            "Nous vous préviendrons une fois confirmé."
        ),
        "franco": (
            "Sajjalt talab el maw3ad ka preference. "
            "Mesh confirmed ba3d — pending confirmation men el team. "
            "Mnahberak lamma yet2akkad."
        ),
    }
    return messages.get(lang, messages["en"])


def public_comment_dm_invite(language: str | None = None) -> str:
    """Safe public-comment reply: invite to DM only; never collect PII publicly."""
    lang = str(language or "en").strip().lower() or "en"
    messages = {
        "ar": "شكراً لتعليقك! للمتابعة بخصوص طلبك أو موعدك، راسلنا بالخاص (DM) ورح نساعدك هناك.",
        "en": "Thanks for your comment! To continue with your request or appointment, please message us in DM and we’ll help you there.",
        "fr": "Merci pour votre commentaire ! Pour poursuivre votre demande ou rendez-vous, écrivez-nous en message privé (DM).",
        "franco": "Thanks 3a comment! La nkamml request aw maw3ad, rasilna bil DM w mna3tik help hunik.",
    }
    return messages.get(lang, messages["en"])


def comment_capture_policy_reply(
    *,
    tenant_id: str | None,
    message: str,
    response_language: str,
    booking_or_order_intent: bool,
) -> dict[str, Any] | None:
    """When capture is active on a public comment with order/appointment intent, invite to DM only."""
    if not booking_or_order_intent:
        return None
    if not skip_forced_booking_wa_me(tenant_id):
        return None
    return {
        "stop": True,
        "reply": public_comment_dm_invite(response_language),
        "reason": "requests_comment_dm_invite",
        "metadata": {"requests_capture": True, "pii_safe_public_comment": True},
    }
