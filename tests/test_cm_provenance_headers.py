"""Provenance headers are remigrate markers — strip for owners and models."""

from services.cm.provenance_headers import (
    sanitize_ai_basics_payload,
    sanitize_section_payload,
    sanitize_style_payload,
    strip_provenance_headers,
)


def test_strip_provenance_headers_keeps_body() -> None:
    raw = (
        "--- redistributed from id=legacy_91146d54bf70 "
        "file=8ce381d0-bf6b-4206-b278-869b99b72744.json "
        "checksum=9f0aabd72af1de152e8126ad905156bb004feeacf8ca33500e23679f7310c14e "
        "title=## New User Handling Rules "
        "targets=ai_basics,dynamic_messages ---\n"
        "For every new user whose gender is still unknown, follow these rules."
    )
    cleaned = strip_provenance_headers(raw)
    assert "redistributed from" not in cleaned
    assert "checksum=" not in cleaned
    assert cleaned.startswith("For every new user")


def test_sanitize_ai_basics_payload() -> None:
    payload = {
        "short_introduction": "--- redistributed from id=a title=t ---\nHello",
        "ai_role": "Assistant",
    }
    out = sanitize_ai_basics_payload(payload)
    assert out["short_introduction"] == "Hello"
    assert out["ai_role"] == "Assistant"
    assert "redistributed from" not in out["short_introduction"]


def test_sanitize_style_payload() -> None:
    payload = {"style_body": "--- redistributed from id=a ---\nWarm tone", "tone": "friendly"}
    out = sanitize_style_payload(payload)
    assert out["style_body"] == "Warm tone"
    assert out["tone"] == "friendly"


def test_sanitize_section_payload_routes_by_section() -> None:
    payload = {"short_introduction": "--- redistributed from id=a ---\nHi"}
    assert sanitize_section_payload("ai_basics", payload)["short_introduction"] == "Hi"
    assert sanitize_section_payload("services", payload) == payload
