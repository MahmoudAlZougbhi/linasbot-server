#!/usr/bin/env python3
"""Read-only audit of App A binding scopes (no tokens or secrets printed)."""

from __future__ import annotations

import os
from pathlib import Path

from services.cm.actions import (
    ACTION_FACEBOOK_COMMENTS,
    ACTION_INSTAGRAM_COMMENTS,
    action_enabled,
    load_actions_section,
)
from services.meta_app_registry import APP_A_KEY, get_meta_app_registry
from services.meta_comment_reply_settings import get_comment_reply_setting
from services.meta_graph_routing import required_comment_scopes_for_binding

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


def _print_cm_comment_actions() -> None:
    tenant_id = (os.getenv("META_COMMENT_AUDIT_TENANT") or "linas").strip() or "linas"
    actions = load_actions_section(tenant_id)
    print(f"[scope-audit] tenant={tenant_id}")
    print(
        f"[scope-audit] cm_action_{ACTION_FACEBOOK_COMMENTS}="
        f"{action_enabled(actions, ACTION_FACEBOOK_COMMENTS)}"
    )
    print(
        f"[scope-audit] cm_action_{ACTION_INSTAGRAM_COMMENTS}="
        f"{action_enabled(actions, ACTION_INSTAGRAM_COMMENTS)}"
    )
    print(f"[scope-audit] cm_disable_linas_legacy_bridge={os.getenv('CM_DISABLE_LINAS_LEGACY_BRIDGE', '')}")
    print(f"[scope-audit] customer_reply_ai_v2={os.getenv('CUSTOMER_REPLY_AI_V2', '')}")
    print(f"[scope-audit] customer_reply_ai_v2_live={os.getenv('CUSTOMER_REPLY_AI_V2_LIVE', '')}")


def main() -> None:
    app_id = (os.getenv("META_APP_ID") or os.getenv("META_APP_A_ID") or "").strip()
    if app_id != "2963733803971681":
        raise SystemExit("Refusing unexpected Meta App ID")
    registry = get_meta_app_registry()
    bindings = [
        item
        for item in registry.list_bindings(include_superseded=False)
        if item.app_key == APP_A_KEY and item.status == "active"
    ]
    _print_cm_comment_actions()
    print(f"[scope-audit] active_bindings={len(bindings)}")
    for binding in bindings:
        credential = registry.get_credential(binding)
        granted = set(credential.scopes)
        masked = binding.asset_id[-6:] if binding.asset_id else "unknown"
        print(
            f"[scope-audit] channel={binding.channel} auth_flow={binding.auth_flow} "
            f"asset_suffix={masked} binding_suffix={binding.binding_id[-6:]}"
        )
        for scope in DM_SCOPES:
            print(f"[scope-audit] dm_scope_{scope}={scope in granted}")
        required_comment = sorted(required_comment_scopes_for_binding(binding))
        for scope in required_comment:
            print(f"[scope-audit] comment_scope_{scope}={scope in granted}")
        for scope in COMMENT_SCOPES.get(binding.channel, ()):
            if scope not in required_comment:
                print(f"[scope-audit] comment_scope_{scope}={scope in granted}")
        for scope in PUBLISH_SCOPES.get(binding.channel, ()):
            print(f"[scope-audit] publish_scope_{scope}={scope in granted}")
        comment_ready = set(required_comment).issubset(granted)
        publish_ready = all(scope in granted for scope in PUBLISH_SCOPES.get(binding.channel, ()))
        setting = get_comment_reply_setting(
            tenant_id=binding.tenant_id,
            app_key=binding.app_key,
            channel=binding.channel,
            asset_id=binding.asset_id,
        )
        print(f"[scope-audit] comment_features_ready={comment_ready}")
        print(f"[scope-audit] publish_features_ready={publish_ready}")
        print(f"[scope-audit] per_asset_comment_enabled={bool(setting.enabled)}")
        print(
            f"[scope-audit] webhook_subscribed_fields="
            f"{','.join(sorted(binding.webhook_subscribed_fields)) or 'none'}"
        )
    for root in (
        Path("/opt/linasbot_data/meta_comment_settings"),
        Path("/opt/linasbot/data/meta_comment_settings"),
    ):
        print(f"[scope-audit] comment_settings_dir path={root} exists={root.is_dir()}")
    print("[scope-audit] SUCCESS")


if __name__ == "__main__":
    main()
