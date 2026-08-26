"""debug_token fail-closed checks for Embedded Signup."""

from __future__ import annotations

import pytest

from services.whatsapp_cloud.embedded_signup_session import SignupAssetError
from services.whatsapp_cloud.embedded_signup_token import validate_embedded_signup_token


def _ok(**overrides):
    payload = {
        "is_valid": True,
        "app_id": "2963733803971681",
        "expires_at": 0,
        "scopes": ["whatsapp_business_management", "whatsapp_business_messaging"],
        "granular_scopes": [
            {"scope": "whatsapp_business_management", "target_ids": ["900100200300"]},
            {"scope": "whatsapp_business_messaging", "target_ids": ["900100200300"]},
        ],
    }
    payload.update(overrides)
    return payload


def test_token_accepts_valid_app_and_waba() -> None:
    scopes = validate_embedded_signup_token(_ok(), waba_id="900100200300")
    assert "whatsapp_business_management" in scopes


def test_token_rejects_invalid_wrong_app_expired_and_granular() -> None:
    with pytest.raises(SignupAssetError) as invalid:
        validate_embedded_signup_token(_ok(is_valid=False), waba_id="900100200300")
    assert invalid.value.code == "token_invalid"
    with pytest.raises(SignupAssetError) as app:
        validate_embedded_signup_token(_ok(app_id="1"), waba_id="900100200300")
    assert app.value.code == "token_wrong_app"
    with pytest.raises(SignupAssetError) as expired:
        validate_embedded_signup_token(_ok(expires_at=1), waba_id="900100200300")
    assert expired.value.code == "token_expired"
    with pytest.raises(SignupAssetError) as scopes:
        validate_embedded_signup_token(_ok(scopes=["email"]), waba_id="900100200300")
    assert scopes.value.code == "scopes_missing"
    with pytest.raises(SignupAssetError) as gran:
        validate_embedded_signup_token(_ok(granular_scopes=[]), waba_id="900100200300")
    assert gran.value.code == "waba_not_authorized"
    with pytest.raises(SignupAssetError) as other:
        validate_embedded_signup_token(
            _ok(granular_scopes=[{"scope": "whatsapp_business_management", "target_ids": ["111"]}]),
            waba_id="900100200300",
        )
    assert other.value.code == "waba_not_authorized"
    assert "EAA" not in str(other.value)
    assert "access_token" not in str(other.value)
