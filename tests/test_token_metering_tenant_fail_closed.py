"""Fail-closed tenant resolution for AI token metering."""

from __future__ import annotations

import pytest

from services.token_metering import resolve_tenant_id


def test_resolve_tenant_id_explicit() -> None:
    assert resolve_tenant_id(explicit="Acme") == "acme"


def test_resolve_tenant_id_from_user_data() -> None:
    assert resolve_tenant_id({"tenant_id": "t1"}) == "t1"
    assert resolve_tenant_id({"tenantId": "t2"}) == "t2"


def test_resolve_tenant_id_missing_fails_closed() -> None:
    with pytest.raises(ValueError, match="tenant_id required"):
        resolve_tenant_id(None)
    with pytest.raises(ValueError, match="tenant_id required"):
        resolve_tenant_id({})
    with pytest.raises(ValueError, match="tenant_id required"):
        resolve_tenant_id({"tenant_id": "  "})
