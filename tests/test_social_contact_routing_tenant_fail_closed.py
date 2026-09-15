"""Social contact resolve must not default missing tenant to linas."""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("EXTERNAL_API_BASE_URL", "https://example.com")
os.environ.setdefault("EXTERNAL_API_TOKEN", "test-token")
os.environ.setdefault("DASHBOARD_AUTH_SECRET", "wave3-test-secret")

from services.integrations.social.social_contact_routing_detect import (
    SocialContactScopeError,
    resolve_social_whatsapp_number,
)


def test_resolve_social_whatsapp_number_rejects_empty_tenant() -> None:
    with pytest.raises(SocialContactScopeError, match="tenant_id required"):
        resolve_social_whatsapp_number("SOCIAL_WHATSAPP_BEIRUT_FEMALE", tenant_id="")
    with pytest.raises(SocialContactScopeError, match="tenant_id required"):
        resolve_social_whatsapp_number("SOCIAL_WHATSAPP_BEIRUT_FEMALE", tenant_id="   ")


def test_resolve_social_whatsapp_number_unpublished_tenant_has_no_matrix(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CM_RUNTIME_MODE", "legacy")
    result = resolve_social_whatsapp_number(
        "SOCIAL_WHATSAPP_BEIRUT_FEMALE",
        tenant_id="linas",
    )
    assert result is None
