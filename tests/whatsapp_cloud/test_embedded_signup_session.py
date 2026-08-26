"""Coexistence session parsing, origins, extras, and Graph phone proof."""

from __future__ import annotations

import pytest

from services.whatsapp_cloud.config import WHATSAPP_COEXISTENCE_FEATURE
from services.whatsapp_cloud.embedded_signup_bridge import render_embedded_signup_bridge_html
from services.whatsapp_cloud.embedded_signup_session import (
    SignupAssetError,
    assert_coexistence_session,
    coexistence_launch_extras,
    origin_is_allowed,
    parse_embedded_signup_session_payload,
    select_proven_coexistence_phone,
    session_event_is_cancel,
    session_event_is_coexistence_finish,
)


def _bridge_html() -> str:
    return render_embedded_signup_bridge_html(
        app_id="2963733803971681",
        state="nonce",
        config_id="cfg",
        redirect_uri="https://example.test/oauth/whatsapp/callback",
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
    assert not session_event_is_coexistence_finish("FINISH")


def test_parse_ignores_non_embedded_signup_type() -> None:
    parsed = parse_embedded_signup_session_payload(
        {"type": "OTHER", "event": "FINISH", "waba_id": "111222333"}
    )
    assert parsed["event"] == ""
    assert parsed["waba_id"] == ""


def test_parse_nested_finish_is_not_coexistence() -> None:
    nested = parse_embedded_signup_session_payload(
        {
            "type": "WA_EMBEDDED_SIGNUP",
            "event": "FINISH",
            "data": {"data": {"waba_id": "111222333", "phone_number_id": "444555666"}},
        }
    )
    assert nested["waba_id"] == "111222333"
    assert nested["event"] == "FINISH"
    assert session_event_is_cancel("CANCEL") is True
    with pytest.raises(SignupAssetError) as exc:
        assert_coexistence_session(
            session_type="WA_EMBEDDED_SIGNUP",
            session_event="FINISH",
            session_version="3",
        )
    assert exc.value.code == "coexistence_flow_required"


def test_select_requires_unique_coexistence_proof() -> None:
    proven = {
        "id": "900100200301",
        "display_phone_number": "+20 100 000 2722",
        "is_on_biz_app": True,
        "platform_type": "CLOUD_API",
    }
    matched = select_proven_coexistence_phone(waba_id="900100200300", phone_number_id="", phones=[proven])
    assert matched["id"] == "900100200301"
    with pytest.raises(SignupAssetError) as missing:
        select_proven_coexistence_phone(
            waba_id="900100200300",
            phone_number_id="",
            phones=[{"id": "900100200301", "is_on_biz_app": False, "platform_type": "CLOUD_API"}],
        )
    assert missing.value.code == "coexistence_not_proven"
    with pytest.raises(SignupAssetError) as platform:
        select_proven_coexistence_phone(
            waba_id="900100200300",
            phone_number_id="",
            phones=[{"id": "900100200301", "is_on_biz_app": True, "platform_type": "NOT_ON_CLOUD_API"}],
        )
    assert platform.value.code == "coexistence_not_proven"
    with pytest.raises(SignupAssetError) as many:
        select_proven_coexistence_phone(
            waba_id="900100200300",
            phone_number_id="",
            phones=[proven, {**proven, "id": "900100200302"}],
        )
    assert many.value.code == "coexistence_phone_ambiguous"


def test_select_rejects_placeholder_and_unknown_phone() -> None:
    phones = [
        {
            "id": "900100200301",
            "display_phone_number": "+1 555 010 1234",
            "is_on_biz_app": True,
            "platform_type": "CLOUD_API",
        }
    ]
    with pytest.raises(SignupAssetError) as exc:
        select_proven_coexistence_phone(waba_id="900100200300", phone_number_id="123456123", phones=phones)
    assert exc.value.code == "sample_phone_forbidden"
    with pytest.raises(SignupAssetError) as unknown:
        select_proven_coexistence_phone(waba_id="900100200300", phone_number_id="999", phones=phones)
    assert unknown.value.code == "phone_not_in_waba"


def test_origins_are_exact_allowlist() -> None:
    assert origin_is_allowed("https://www.facebook.com")
    assert origin_is_allowed("https://web.facebook.com")
    assert origin_is_allowed("https://business.facebook.com")
    assert not origin_is_allowed("https://evilfacebook.com")
    assert not origin_is_allowed("https://www.facebook.com.evil.test")
    assert not origin_is_allowed("https://facebook.com.attacker.test")
    html = _bridge_html()
    assert "evilfacebook.com" not in html
    assert "indexOf('facebook.com')" not in html
    assert "includes('facebook.com')" not in html
    assert "allowedOrigins.has" in html


def test_launch_extras_are_official_coexistence_v4() -> None:
    extras = coexistence_launch_extras()
    assert extras["setup"] == {}
    assert extras["featureType"] == WHATSAPP_COEXISTENCE_FEATURE
    assert extras["sessionInfoVersion"] == "3"
    assert extras["version"] == "v4"
    html = _bridge_html()
    assert "whatsapp_business_app_onboarding" in html
    assert '"sessionInfoVersion": "3"' in html
    assert '"version": "v4"' in html
    assert "FINISH_WHATSAPP_BUSINESS_APP_ONBOARDING" in html
    assert "Connect a WhatsApp Business app" in html
    assert "Create a WhatsApp Business account" in html
    assert "preVerifiedPhone" not in html
    assert "response_type: 'code'" in html or '"response_type": "code"' in html
    assert "maybeComplete" in html
    assert "authCode" in html
    assert "sessionInfo" in html
    assert "session_timeout" in html
    assert "allowedOrigins.has" in html
    assert "parsed.type !== SESSION_TYPE" in html
    assert "/register" not in html
