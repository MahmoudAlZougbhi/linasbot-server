"""Wave 3: social contact routing must not default missing tenant to linas."""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("LINASLASER_API_BASE_URL", "https://example.com")
os.environ.setdefault("LINASLASER_API_TOKEN", "test-token")
os.environ.setdefault("DASHBOARD_AUTH_SECRET", "wave3-test-secret")

from services.social_contact_routing import route_social_contact_request
from services.social_contact_routing_detect import (
    SocialContactScopeError,
    resolve_social_whatsapp_number,
)


def _scoped_user_data(**overrides) -> dict:
    base = {
        "channel": "instagram",
        "meta_account_id": "17841413184256533",
        "social_sender_id": "tenant-fail-closed-sender",
    }
    base.update(overrides)
    return base


def test_resolve_social_whatsapp_number_rejects_empty_tenant() -> None:
    with pytest.raises(SocialContactScopeError, match="tenant_id required"):
        resolve_social_whatsapp_number("SOCIAL_WHATSAPP_BEIRUT_FEMALE", tenant_id="")
    with pytest.raises(SocialContactScopeError, match="tenant_id required"):
        resolve_social_whatsapp_number("SOCIAL_WHATSAPP_BEIRUT_FEMALE", tenant_id="   ")


def test_resolve_social_whatsapp_number_accepts_explicit_linas(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CM_RUNTIME_MODE", "legacy")
    result = resolve_social_whatsapp_number(
        "SOCIAL_WHATSAPP_BEIRUT_FEMALE",
        tenant_id="linas",
    )
    assert result == "+96178847527"


def test_route_social_contact_request_fails_closed_without_tenant() -> None:
    with pytest.raises(SocialContactScopeError):
        route_social_contact_request("Book an appointment", _scoped_user_data(), "en")


def test_route_social_contact_request_works_with_explicit_tenant(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CM_RUNTIME_MODE", "legacy")
    ud = _scoped_user_data(tenant_id="linas")
    r1 = route_social_contact_request("I want to book", ud, "en")
    assert r1 is not None
    r2 = route_social_contact_request("Beirut", ud, "en")
    assert r2 is not None
    r3 = route_social_contact_request("female", ud, "en")
    assert r3 is not None
    assert "wa.me/96178847527" in r3.reply
