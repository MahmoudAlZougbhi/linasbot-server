"""Wave 2 social routing / intent golden matrix (no Meta send, no OpenAI)."""

from __future__ import annotations

import os

os.environ.setdefault("LINASLASER_API_BASE_URL", "https://example.com")
os.environ.setdefault("LINASLASER_API_TOKEN", "test-token")
os.environ.setdefault("DASHBOARD_AUTH_SECRET", "wave2-test-secret")

from services.conversation_router import is_human_request
from services.social_contact_routing import (
    DEFAULT_SOCIAL_WHATSAPP_CONTACTS,
    is_appointment_request,
    phone_digits,
    route_social_contact_request,
    wa_me_url,
)

REQUIRED = {
    "SOCIAL_WHATSAPP_BEIRUT_FEMALE": "96178847527",
    "SOCIAL_WHATSAPP_ANTELIAS_FEMALE": "96170707354",
    "SOCIAL_WHATSAPP_BEIRUT_MALE": "96171534928",
    "SOCIAL_WHATSAPP_ANTELIAS_MALE": "96171226082",
}


def social_user_data(channel: str = "instagram") -> dict:
    return {
        "tenant_id": "linas",
        "channel": channel,
        "meta_account_id": "17841413184256533" if channel == "instagram" else "378696005334409",
        "social_sender_id": f"{channel}-wave2-sender",
    }


def test_contact_matrix_exact():
    for key, digits in REQUIRED.items():
        got = phone_digits(DEFAULT_SOCIAL_WHATSAPP_CONTACTS[key])
        assert got == digits
        assert wa_me_url(DEFAULT_SOCIAL_WHATSAPP_CONTACTS[key]) == f"https://wa.me/{digits}"


def test_hours_not_booking():
    for text in ["شو مواعيد العمل؟", "مواعيد دوامكن؟", "What are your opening hours?"]:
        assert is_appointment_request(text) is False
        out = route_social_contact_request(text, social_user_data(), "ar")
        assert out is None


def test_personal_care_not_human():
    assert is_human_request("personal care tips") is False
    out = route_social_contact_request("personal care tips", social_user_data(), "en")
    assert out is None


def test_arabic_human_detected():
    assert is_human_request("بدي احكي مع حدا") is True
    out = route_social_contact_request("بدي احكي مع حدا", social_user_data(), "ar")
    assert out is not None
    assert out.intent == "human"


def test_arabizi_booking_detected():
    assert is_appointment_request("bade a7jez") is True
    out = route_social_contact_request("bade a7jez", social_user_data(), "ar")
    assert out is not None
    assert out.intent == "booking"


def test_force_intent_alone_blocked():
    out = route_social_contact_request("thanks", social_user_data(), "en", force_intent="booking")
    assert out is None


def test_explicit_booking_english():
    out = route_social_contact_request("I want to book an appointment", social_user_data("facebook"), "en")
    assert out is not None
    assert out.intent == "booking"


def test_tattoo_request_refuses_without_whatsapp():
    out = route_social_contact_request("tattoo removal", social_user_data(), "en")
    assert out is not None
    assert out.tattoo_removal is True
    assert out.contact_env is None
    assert "71534928" not in out.reply
    assert "wa.me" not in out.reply.lower()
    assert "isn't one of the services" in out.reply.lower()


def test_full_laser_handoff_women_beirut():
    ud = social_user_data()
    r1 = route_social_contact_request("بدي احجز", ud, "ar")
    assert r1 is not None
    r2 = route_social_contact_request("Beirut", ud, "en")
    assert r2 is not None
    r3 = route_social_contact_request("female", ud, "en")
    assert r3 is not None
    assert "wa.me/96178847527" in r3.reply


def test_greetings_stay_on_ai():
    for text in ["Hello", "مرحبا", "kifak", "Au revoir", "ok"]:
        assert route_social_contact_request(text, social_user_data(), "en") is None


def test_price_and_prep_stay_on_ai():
    for text in [
        "كم سعر الليزر؟",
        "How much is laser hair removal?",
        "preparation for laser",
        "شو خدماتكن؟",
    ]:
        assert route_social_contact_request(text, social_user_data(), "ar") is None
