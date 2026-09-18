"""Platform Owner message-catalog administration. Billing owns catalog state."""

from __future__ import annotations

from typing import Any

from services.billing.membership.catalog_admin import CatalogPublishBlocked, current_catalog, publish, update_draft
from services.billing.membership.daily_edits import decision_payload, set_platform_baseline, set_tenant_override, status

__all__ = ["CatalogPublishBlocked"]


def get_message_catalog() -> dict[str, Any]:
    return current_catalog()


def save_message_catalog_draft(
    *,
    actor: str,
    changes: dict[str, Any],
    reason: str,
) -> dict[str, Any]:
    if "ai_setup_daily_edit_limit" in changes:
        set_platform_baseline(int(changes["ai_setup_daily_edit_limit"]))
    return update_draft(actor=actor, changes=changes, reason=reason)


def publish_message_catalog(*, actor: str) -> dict[str, Any]:
    return publish(actor=actor)


def daily_edits_for_tenant(tenant_id: str) -> dict[str, Any]:
    return decision_payload(status(tenant_id))


def set_daily_edit_policy(*, tenant_id: str | None, limit: int) -> dict[str, Any]:
    if tenant_id:
        set_tenant_override(tenant_id, limit)
        return daily_edits_for_tenant(tenant_id)
    set_platform_baseline(limit)
    return {"limit": limit, "source": "platform_baseline"}
