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
    "SOCIAL_WHATSAPP_TATTOO_REMOVAL": "96171534928",
}


def test_contact_matrix_exact():
    for key, digits in REQUIRED.items():
        got = phone_digits(DEFAULT_SOCIAL_WHATSAPP_CONTACTS[key])
        assert got == digits
        assert wa_me_url(DEFAULT_SOCIAL_WHATSAPP_CONTACTS[key]) == f"https://wa.me/{digits}"


def test_hours_not_booking():
    for text in ["شو مواعيد العمل؟", "مواعيد دوامكن؟", "What are your opening hours?"]:
        assert is_appointment_request(text) is False
        out = route_social_contact_request(text, {"channel": "instagram"}, None, "ar")
        assert out is None


def test_personal_care_not_human():
    assert is_human_request("personal care tips") is False
    out = route_social_contact_request("personal care tips", {"channel": "instagram"}, None, "en")
    assert out is None


def test_arabic_human_detected():
    assert is_human_request("بدي احكي مع حدا") is True
    out = route_social_contact_request("بدي احكي مع حدا", {"channel": "instagram"}, None, "ar")
    assert out is not None
    assert out.intent == "human"


def test_arabizi_booking_detected():
    assert is_appointment_request("bade a7jez") is True
    out = route_social_contact_request("bade a7jez", {"channel": "instagram"}, None, "ar")
    assert out is not None
    assert out.intent == "booking"


def test_force_intent_alone_blocked():
    out = route_social_contact_request("thanks", {"channel": "instagram"}, None, "en", force_intent="booking")
    assert out is None


def test_explicit_booking_english():
    out = route_social_contact_request("I want to book an appointment", {"channel": "facebook"}, None, "en")
    assert out is not None
    assert out.intent == "booking"


def test_tattoo_beirut_only_number():
    out = route_social_contact_request("tattoo removal", {"channel": "instagram"}, None, "en")
    assert out is not None
    assert "71534928" in out.reply
    assert "wa.me/96171534928" in out.reply
    assert "Antelias" not in out.reply or "not Antelias" in out.reply


def test_full_laser_handoff_women_beirut():
    ud = {"channel": "instagram"}
    r1 = route_social_contact_request("بدي احجز", ud, None, "ar")
    assert r1 is not None
    r2 = route_social_contact_request("Beirut", ud, None, "en")
    assert r2 is not None
    r3 = route_social_contact_request("female", ud, None, "en")
    assert r3 is not None
    assert "wa.me/96178847527" in r3.reply


def test_greetings_stay_on_ai():
    for text in ["Hello", "مرحبا", "kifak", "Au revoir", "ok"]:
        assert route_social_contact_request(text, {"channel": "instagram"}, None, "en") is None


def test_price_and_prep_stay_on_ai():
    for text in [
        "كم سعر الليزر؟",
        "How much is laser hair removal?",
        "preparation for laser",
        "شو خدماتكن؟",
    ]:
        assert route_social_contact_request(text, {"channel": "instagram"}, None, "ar") is None
