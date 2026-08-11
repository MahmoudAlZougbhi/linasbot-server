"""Shared helpers for Meta connections API (LOC split)."""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException

from services.meta_app_registry import (
    APP_A_KEY,
    MetaAssetBinding,
    MetaRegistryError,
    _bindings_share_exclusive_asset,
    get_meta_app_registry,
)

def _query_text(value: Any) -> str:
    """Normalize FastAPI Query defaults when handlers are awaited directly in tests."""

    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    # Query()/Path() objects are truthy but should behave as empty defaults.
    if hasattr(value, "default") and not isinstance(value, (bytes, bytearray)):
        return ""
    return str(value).strip()


def _tenant_binding(binding_id: str, tenant_id: str) -> MetaAssetBinding:
    registry = get_meta_app_registry()
    binding = next(
        (item for item in registry.list_bindings() if item.binding_id == binding_id and item.tenant_id == tenant_id),
        None,
    )
    if binding is None:
        raise HTTPException(status_code=404, detail="Meta connection not found")
    return binding


def _subscription_identity(binding: MetaAssetBinding) -> tuple[str, str]:
    """Meta Page subscriptions are unique per app and Page, not per token."""

    return binding.app_key, binding.page_id


def _active_conflict(binding: MetaAssetBinding) -> MetaAssetBinding | None:
    matches = [
        item
        for item in get_meta_app_registry().list_bindings(include_inactive=False, include_superseded=False)
        if item.binding_id != binding.binding_id
        and item.tenant_id == binding.tenant_id
        and _bindings_share_exclusive_asset(item, binding)
    ]
    if len(matches) > 1:
        raise MetaRegistryError("Active Meta binding indexes are inconsistent")
    return matches[0] if matches else None


def _authorization_title(app_key: str | None) -> str:
    if app_key == APP_A_KEY:
        return "Meta authorization — App A"
    return "Connected through Linas AI"
