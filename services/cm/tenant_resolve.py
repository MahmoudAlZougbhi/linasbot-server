"""Resolve exactly one authorized tenant from channel/account mappings."""

from __future__ import annotations

from typing import Any

from services.cm.constants import DEFAULT_TENANT_ID


class AmbiguousTenantError(ValueError):
    pass


class UnknownTenantMappingError(ValueError):
    pass


def resolve_tenant_from_channel(
    *,
    channel: str | None,
    account_id: str | None = None,
    page_id: str | None = None,
    phone: str | None = None,
    mappings: dict[str, Any] | None = None,
    default_tenant_id: str = DEFAULT_TENANT_ID,
) -> str:
    """Map webhook identity → exactly one tenant_id.

    ``mappings`` shape (tenant-owned config, not platform Lina defaults)::

        {
          "instagram_account_ids": {"IG123": "tenant_a"},
          "facebook_page_ids": {"PAGE1": "tenant_a"},
          "whatsapp_phones": {"+9617...": "tenant_a"},
        }

    When mappings are empty, returns ``default_tenant_id`` (single-tenant deploy).
    Multiple distinct hits raise AmbiguousTenantError.
    """
    table = mappings or {}
    hits: set[str] = set()
    channel_l = (channel or "").strip().lower()

    if account_id and isinstance(table.get("instagram_account_ids"), dict):
        tid = table["instagram_account_ids"].get(str(account_id).strip())
        if tid:
            hits.add(str(tid))
    if page_id and isinstance(table.get("facebook_page_ids"), dict):
        tid = table["facebook_page_ids"].get(str(page_id).strip())
        if tid:
            hits.add(str(tid))
    if phone and isinstance(table.get("whatsapp_phones"), dict):
        tid = table["whatsapp_phones"].get(str(phone).strip())
        if tid:
            hits.add(str(tid))

    # Channel-scoped maps (optional)
    if channel_l and isinstance(table.get(channel_l), dict):
        key = account_id or page_id or phone
        if key:
            tid = table[channel_l].get(str(key).strip())
            if tid:
                hits.add(str(tid))

    if len(hits) > 1:
        raise AmbiguousTenantError(f"multiple tenants matched: {sorted(hits)}")
    if len(hits) == 1:
        return next(iter(hits))
    if mappings:
        raise UnknownTenantMappingError("no tenant mapping for channel identity")
    return default_tenant_id
