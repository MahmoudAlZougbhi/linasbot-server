#!/usr/bin/env python3
"""Read-only audit of App A binding scopes (no tokens or secrets printed)."""

from __future__ import annotations

import os

from services.meta_app_registry import APP_A_KEY, get_meta_app_registry

COMMENT_SCOPES = {
    "facebook": ("pages_read_user_content", "pages_manage_engagement"),
    "instagram": ("instagram_manage_comments",),
}
PUBLISH_SCOPES = {
    "facebook": ("pages_manage_posts",),
    "instagram": ("instagram_content_publish",),
}
DM_SCOPES = (
    "pages_show_list",
    "pages_manage_metadata",
    "pages_read_engagement",
    "pages_messaging",
    "instagram_basic",
    "instagram_manage_messages",
)


def main() -> None:
    app_id = (os.getenv("META_APP_ID") or "").strip()
    if app_id != "2963733803971681":
        raise SystemExit("Refusing unexpected Meta App ID")
    registry = get_meta_app_registry()
    bindings = [
        item
        for item in registry.list_bindings(include_superseded=False)
        if item.app_key == APP_A_KEY and item.status == "active"
    ]
    print(f"[scope-audit] active_bindings={len(bindings)}")
    for binding in bindings:
        credential = registry.get_credential(binding)
        granted = set(credential.scopes)
        masked = binding.asset_id[-6:] if binding.asset_id else "unknown"
        print(f"[scope-audit] channel={binding.channel} asset_suffix={masked} binding_suffix={binding.binding_id[-6:]}")
        for scope in DM_SCOPES:
            print(f"[scope-audit] dm_scope_{scope}={scope in granted}")
        for scope in COMMENT_SCOPES.get(binding.channel, ()):
            print(f"[scope-audit] comment_scope_{scope}={scope in granted}")
        for scope in PUBLISH_SCOPES.get(binding.channel, ()):
            print(f"[scope-audit] publish_scope_{scope}={scope in granted}")
        comment_ready = all(scope in granted for scope in COMMENT_SCOPES.get(binding.channel, ()))
        publish_ready = all(scope in granted for scope in PUBLISH_SCOPES.get(binding.channel, ()))
        print(f"[scope-audit] comment_features_ready={comment_ready}")
        print(f"[scope-audit] publish_features_ready={publish_ready}")
    print("[scope-audit] SUCCESS")


if __name__ == "__main__":
    main()
