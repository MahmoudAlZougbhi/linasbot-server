"""Tenant-scoped connected accounts and posts for Comment Rule targeting."""

from __future__ import annotations

from typing import Any

from services.meta_app_registry import get_meta_app_registry


def list_tenant_comment_accounts(tenant_id: str) -> list[dict[str, str]]:
    tenant = str(tenant_id or "").strip()
    try:
        registry = get_meta_app_registry()
        bindings = registry.list_bindings(include_inactive=False, include_superseded=False)
    except Exception:
        return []
    rows: list[dict[str, str]] = []
    for binding in bindings:
        if str(binding.tenant_id or "") != tenant:
            continue
        if binding.channel not in {"facebook", "instagram"}:
            continue
        rows.append(
            {
                "platform": binding.channel,
                "connected_account_id": binding.asset_id,
                "page_or_ig_account_id": binding.instagram_account_id or binding.page_id or binding.asset_id,
                "name": binding.instagram_username or binding.page_name or binding.asset_id,
                "binding_id": binding.binding_id,
            }
        )
    return rows


def account_belongs_to_tenant(*, tenant_id: str, platform: str, connected_account_id: str) -> bool:
    want = str(connected_account_id or "").strip()
    plat = str(platform or "").strip().lower()
    for row in list_tenant_comment_accounts(tenant_id):
        if row["connected_account_id"] == want and row["platform"] == plat:
            return True
        if row["page_or_ig_account_id"] == want and row["platform"] == plat:
            return True
    return False


async def list_connected_posts(
    *,
    tenant_id: str,
    platform: str,
    connected_account_id: str,
    graph_fetch: Any | None = None,
) -> dict[str, Any]:
    if not account_belongs_to_tenant(tenant_id=tenant_id, platform=platform, connected_account_id=connected_account_id):
        return {"ok": False, "error": "account_not_in_tenant", "posts": []}
    posts: list[dict[str, str]] = []
    source = "not_fetched"
    if graph_fetch is not None:
        posts = list(await graph_fetch(platform=platform, account_id=connected_account_id) or [])
        source = "graph"
    return {"ok": True, "posts": posts[:50], "posts_source": source}
