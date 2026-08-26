"""Coexistence session parsing, phone discovery, and launch extras."""

from __future__ import annotations

import pytest

from services.whatsapp_cloud.config import WHATSAPP_COEXISTENCE_FEATURE
from services.whatsapp_cloud.embedded_signup_bridge import render_embedded_signup_bridge_html
from services.whatsapp_cloud.embedded_signup_session import (
    SignupAssetError,
    coexistence_launch_extras,
    parse_embedded_signup_session_payload,
    resolve_signup_phone,
    session_event_is_cancel,
    session_event_is_coexistence_finish,
)


def test_parse_official_coexistence_finish_omits_phone() -> None:
    parsed = parse_embedded_signup_session_payload(
        {
            "data": {"waba_id": "900100200300"},
            "type": "WA_EMBEDDED_SIGNUP",
            "event": "FINISH_WHATSAPP_BUSINESS_APP_ONBOARDING",
            "version": 3,
        }
    )
    assert parsed["event"] == "FINISH_WHATSAPP_BUSINESS_APP_ONBOARDING"
    assert parsed["waba_id"] == "900100200300"
    assert parsed["phone_number_id"] == ""
    assert session_event_is_coexistence_finish(parsed["event"])


def test_parse_nested_data_and_cancel() -> None:
    nested = parse_embedded_signup_session_payload(
        {
            "type": "WA_EMBEDDED_SIGNUP",
            "event": "FINISH",
            "data": {"data": {"waba_id": "111222333", "phone_number_id": "444555666"}},
        }
    )
    assert nested["waba_id"] == "111222333"
    assert nested["phone_number_id"] == "444555666"
    assert session_event_is_cancel("CANCEL") is True
    assert session_event_is_cancel("FINISH") is False


def test_resolve_phone_omitted_single_and_ambiguous() -> None:
    only = [{"id": "900100200301", "display_phone_number": "+20 100 000 2722", "verified_name": "Clinic"}]
    matched = resolve_signup_phone(waba_id="900100200300", phone_number_id="", phones=only)
    assert matched["id"] == "900100200301"
    many = only + [{"id": "900100200302", "display_phone_number": "+20 100 000 0001"}]
    with pytest.raises(SignupAssetError) as exc:
        resolve_signup_phone(waba_id="900100200300", phone_number_id="", phones=many)
    assert exc.value.code == "phone_ambiguous"


def test_resolve_rejects_placeholder_and_unknown_phone() -> None:
    phones = [{"id": "900100200301", "display_phone_number": "+1 555 010 1234"}]
    with pytest.raises(SignupAssetError) as exc:
        resolve_signup_phone(waba_id="900100200300", phone_number_id="123456123", phones=phones)
    assert exc.value.code == "sample_phone_forbidden"
    with pytest.raises(SignupAssetError) as exc2:
        resolve_signup_phone(waba_id="900100200300", phone_number_id="999", phones=phones)
    assert exc2.value.code == "phone_not_in_waba"


def test_launch_extras_are_official_coexistence_not_new_number() -> None:
    extras = coexistence_launch_extras()
    assert extras["setup"] == {}
    assert extras["featureType"] == WHATSAPP_COEXISTENCE_FEATURE
    assert extras["sessionInfoVersion"] == "3"
    assert "phone" not in extras["setup"]
    html = render_embedded_signup_bridge_html(
        app_id="2963733803971681",
        state="nonce",
        config_id="cfg",
        redirect_uri="https://example.test/oauth/whatsapp/callback",
    )
    assert "whatsapp_business_app_onboarding" in html
    assert "sessionInfoVersion: '3'" in html
    assert "setup: {}" in html
    assert "FINISH_WHATSAPP_BUSINESS_APP_ONBOARDING" in html
    assert "Do not choose Add a new number" in html
    assert "preVerifiedPhone" not in html
    assert "response_type: 'code'" in html
    assert "waitThenFinish" in html
