"""Tenant custom roles + assignable custom role slugs."""

from __future__ import annotations

from typing import Any

import pytest

from services.role_assignment import RoleAssignmentError, assert_assignable_role
from services.tenant_custom_roles import TenantCustomRolesStore, system_role_payloads


def test_system_role_payloads_include_support_label() -> None:
    roles = {item["id"]: item for item in system_role_payloads()}
    assert roles["admin"]["name"] == "Admin"
    assert roles["operator"]["name"] == "Support"
    assert roles["viewer"]["name"] == "Viewer"
    assert roles["admin"]["system"] is True
    assert roles["admin"]["permissions"]["userManagement"] is True
    assert roles["operator"]["permissions"]["liveChat"] is True
    assert roles["operator"]["permissions"]["userManagement"] is False


def test_custom_role_ids_are_assignable() -> None:
    assert assert_assignable_role("sales-lead", custom_role_ids=["sales-lead"]) == "sales-lead"
    with pytest.raises(RoleAssignmentError):
        assert_assignable_role("sales-lead")
    with pytest.raises(RoleAssignmentError):
        assert_assignable_role("platform_owner", custom_role_ids=["platform_owner"])


def test_create_role_persists_permissions(monkeypatch: pytest.MonkeyPatch) -> None:
    store = TenantCustomRolesStore()
    saved: dict[str, Any] = {}

    class _Doc:
        def get(self, **_kwargs: Any) -> Any:
            class Snap:
                exists = False

                def to_dict(self) -> dict[str, Any]:
                    return {}

            return Snap()

        def set(self, payload: dict[str, Any], **_kwargs: Any) -> None:
            saved.update(payload)

    monkeypatch.setattr(store, "_doc", lambda _tenant: _Doc())
    role = store.create_role(
        "tenant-a",
        "Manager",
        {"dashboard": True, "liveChat": True, "requests": True, "unknown": True},
    )
    assert role["id"] == "manager"
    assert role["name"] == "Manager"
    assert role["system"] is False
    assert role["permissions"]["dashboard"] is True
    assert role["permissions"]["liveChat"] is True
    assert role["permissions"]["requests"] is True
    assert "unknown" not in role["permissions"]
    assert saved["roles"][0]["id"] == "manager"


def test_create_role_rejects_reserved_and_short_names(monkeypatch: pytest.MonkeyPatch) -> None:
    store = TenantCustomRolesStore()

    class _Doc:
        def get(self, **_kwargs: Any) -> Any:
            class Snap:
                exists = False

                def to_dict(self) -> dict[str, Any]:
                    return {}

            return Snap()

        def set(self, *_args: Any, **_kwargs: Any) -> None:
            raise AssertionError("should not write")

    monkeypatch.setattr(store, "_doc", lambda _tenant: _Doc())
    with pytest.raises(ValueError, match="required"):
        store.create_role("tenant-a", "A", None)
    with pytest.raises(ValueError, match="already exists"):
        store.create_role("tenant-a", "Admin", None)
