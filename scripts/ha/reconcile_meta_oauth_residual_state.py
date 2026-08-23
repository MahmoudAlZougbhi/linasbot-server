#!/usr/bin/env python3
"""Report and optionally settle residual Meta OAuth state after a failed Connect."""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

REPO_DIR = Path(__file__).resolve().parents[2]
if str(REPO_DIR) not in sys.path:
    sys.path.insert(0, str(REPO_DIR))

from services.channel_capability_toggles import action_id_for, canonical_channel_bindings, supported_platforms
from services.cm.storage import get_draft
from services.cm.version_store import read_published_pointer
from services.cm.atomic_io import read_json_object
from services.cm.paths import versions_dir
from services.meta_app_registry import get_meta_app_registry
from services.meta_connection_disconnect import disconnect_meta_binding_set
from services.meta_instagram_login_lifecycle import get_instagram_login_lifecycle
from services.meta_instagram_login_subscription_recovery import (
    instagram_login_orphan_cleanup_eligible,
    retry_instagram_login_cleanup,
    retry_instagram_login_orphan_cleanup,
)
from services.meta_instagram_login_subscription import INSTAGRAM_LOGIN_CLEANUP_PENDING_STATUS


def _published_actions(tenant_id: str) -> dict[str, bool]:
    pointer = read_published_pointer(tenant_id)
    if pointer is None:
        return {}
    actions_path = versions_dir(tenant_id) / pointer.content_version_id / "content" / "actions.json"
    if not actions_path.is_file():
        return {}
    payload = read_json_object(actions_path)
    out: dict[str, bool] = {}
    for item in payload.get("items") or []:
        if not isinstance(item, dict):
            continue
        action_id = str(item.get("id") or item.get("action_id") or "").strip()
        if action_id:
            out[action_id] = bool(item.get("enabled"))
    return out


def _draft_actions(tenant_id: str) -> dict[str, bool]:
    envelope = get_draft("actions", tenant_id=tenant_id)
    out: dict[str, bool] = {}
    for item in (envelope.payload or {}).get("items") or []:
        if not isinstance(item, dict):
            continue
        action_id = str(item.get("id") or item.get("action_id") or "").strip()
        if action_id:
            out[action_id] = bool(item.get("enabled"))
    return out


def audit_tenant(tenant_id: str) -> dict[str, object]:
    registry = get_meta_app_registry()
    bindings = [
        item
        for item in registry.list_bindings(include_inactive=True, include_superseded=True)
        if item.tenant_id == tenant_id and item.channel in {"facebook", "instagram"}
    ]
    active = [item for item in bindings if item.active]
    testing = [item for item in bindings if item.status == "testing"]
    cleanup_pending = [
        item
        for item in bindings
        if item.webhook_subscription_status == INSTAGRAM_LOGIN_CLEANUP_PENDING_STATUS
    ]
    orphans = [item for item in bindings if instagram_login_orphan_cleanup_eligible(item)]
    live_creds = [
        item
        for item in bindings
        if registry.binding_credential_is_available(item.binding_id)
    ]
    toggle_mismatches: list[str] = []
    published = _published_actions(tenant_id)
    draft = _draft_actions(tenant_id)
    for platform in supported_platforms():
        connected = bool(canonical_channel_bindings(tenant_id, platform))
        for toggle in ("dm", "comments"):
            action_id = action_id_for(platform, toggle)
            if not action_id:
                continue
            enabled = bool(published.get(action_id))
            if enabled and not connected:
                toggle_mismatches.append(f"published:{action_id}=on_without_binding")
            draft_enabled = draft.get(action_id)
            if draft_enabled is not None and draft_enabled != enabled:
                toggle_mismatches.append(f"draft_published_drift:{action_id}")
    return {
        "tenant_id": tenant_id,
        "active_bindings": len(active),
        "testing_bindings": [item.binding_id for item in testing],
        "cleanup_pending_bindings": [item.binding_id for item in cleanup_pending],
        "orphan_bindings": [item.binding_id for item in orphans],
        "live_credentials": [item.binding_id for item in live_creds],
        "toggle_mismatches": toggle_mismatches,
        "healthy": not testing and not cleanup_pending and not orphans and not toggle_mismatches,
    }


async def repair_tenant(tenant_id: str, *, actor_id: str) -> dict[str, object]:
    registry = get_meta_app_registry()
    repaired: list[str] = []

    for binding in registry.list_bindings(include_inactive=True, include_superseded=True):
        if binding.tenant_id != tenant_id or binding.channel not in {"facebook", "instagram"}:
            continue
        if binding.webhook_subscription_status == INSTAGRAM_LOGIN_CLEANUP_PENDING_STATUS:
            await retry_instagram_login_cleanup(binding.binding_id, registry=registry, actor_id=actor_id)
            repaired.append(f"cleanup:{binding.binding_id}")
        elif instagram_login_orphan_cleanup_eligible(binding):
            await retry_instagram_login_orphan_cleanup(binding.binding_id, registry=registry, actor_id=actor_id)
            repaired.append(f"orphan:{binding.binding_id}")

    testing = [
        item
        for item in registry.list_bindings(include_inactive=True, include_superseded=False)
        if item.tenant_id == tenant_id and item.status == "testing"
    ]
    if testing:
        await disconnect_meta_binding_set(testing, actor_id=actor_id, registry=registry)
        repaired.extend(f"testing:{item.binding_id}" for item in testing)

    lifecycle = await get_instagram_login_lifecycle().run_once(actor_id=actor_id)
    return {"tenant_id": tenant_id, "repaired": repaired, "instagram_lifecycle": lifecycle}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tenant-id", default="linas")
    parser.add_argument("--repair", action="store_true", help="Discard testing bindings and retry IG cleanup markers")
    args = parser.parse_args()

    report = audit_tenant(args.tenant_id)
    print(report)
    if args.repair and not report["healthy"]:
        result = asyncio.run(repair_tenant(args.tenant_id, actor_id="meta-oauth-residual-reconcile"))
        print(result)
        print(audit_tenant(args.tenant_id))
    return 0 if report["healthy"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
