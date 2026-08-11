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
    print(f"[scope-audit] cm_action_{ACTION_FACEBOOK_COMMENTS}={action_enabled(actions, ACTION_FACEBOOK_COMMENTS)}")
    print(f"[scope-audit] cm_action_{ACTION_INSTAGRAM_COMMENTS}={action_enabled(actions, ACTION_INSTAGRAM_COMMENTS)}")
    print(f"[scope-audit] cm_disable_linas_legacy_bridge={os.getenv('CM_DISABLE_LINAS_LEGACY_BRIDGE', '')}")
    print(f"[scope-audit] customer_retrieval_model={os.getenv('LINAS_CUSTOMER_RETRIEVAL_MODEL', 'gpt-5.6-luna')}")
    print(f"[scope-audit] customer_answer_model={os.getenv('LINAS_CUSTOMER_ANSWER_MODEL', 'gpt-5.6-terra')}")
    print(f"[scope-audit] customer_media_context={os.getenv('CUSTOMER_MEDIA_CONTEXT_ENABLED', 'true')}")
    print(
        f"[scope-audit] meta_app_a_advanced_access_approved="
        f"{(os.getenv('META_APP_A_ADVANCED_ACCESS_APPROVED') or '').strip().lower() or 'unset'}"
    )


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
        declined = sorted(set(credential.declined_scopes or ()))
        print(f"[scope-audit] declined_scopes={','.join(declined) or 'none'}")
        print(
            f"[scope-audit] webhook_subscribed_fields={','.join(sorted(binding.webhook_subscribed_fields)) or 'none'}"
        )
        _print_debug_permission_statuses(credential)
    for root in (
        Path("/opt/linasbot_data/meta_comment_settings"),
        Path("/opt/linasbot/data/meta_comment_settings"),
    ):
        print(f"[scope-audit] comment_settings_dir path={root} exists={root.is_dir()}")
    _print_capability_probe(tenant_id=(os.getenv("META_COMMENT_AUDIT_TENANT") or "linas").strip() or "linas")
    print("[scope-audit] SUCCESS")


def _print_debug_permission_statuses(credential: object) -> None:
    """Print Meta debug_token permission names + status only (never tokens)."""

    try:
        import json
        import urllib.parse
        import urllib.request

        token = str(getattr(credential, "access_token", "") or "").strip()
        app_id = (os.getenv("META_APP_ID") or os.getenv("META_APP_A_ID") or "").strip()
        app_secret = (os.getenv("META_APP_SECRET") or os.getenv("META_APP_A_SECRET") or "").strip()
        if not token or not app_id or not app_secret:
            print("[scope-audit] permission_debug=skipped_missing_inputs")
            return
        app_token = f"{app_id}|{app_secret}"
        query = urllib.parse.urlencode({"input_token": token, "access_token": app_token})
        url = f"https://graph.facebook.com/v24.0/debug_token?{query}"
        with urllib.request.urlopen(url, timeout=20) as response:
            payload = json.loads(response.read(500_000))
        data = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(data, dict):
            print("[scope-audit] permission_debug=invalid_response")
            return
        scopes = data.get("scopes") if isinstance(data.get("scopes"), list) else []
        granular = data.get("granular_scopes") if isinstance(data.get("granular_scopes"), list) else []
        print(f"[scope-audit] debug_token_is_valid={bool(data.get('is_valid'))}")
        print(f"[scope-audit] debug_token_scopes={','.join(str(s) for s in scopes) or 'none'}")
        for row in granular:
            if not isinstance(row, dict):
                continue
            scope = str(row.get("scope") or "").strip()
            if scope:
                print(f"[scope-audit] debug_granular_scope={scope}")
        # Page tokens do not expose /me/permissions; report declined from credential only.
        declined = sorted(set(getattr(credential, "declined_scopes", ()) or ()))
        for scope in declined:
            print(f"[scope-audit] permission_status name={scope} status=declined")
        comment_targets = (
            "pages_read_user_content",
            "pages_manage_engagement",
            "instagram_manage_comments",
            "instagram_business_manage_comments",
        )
        granted = {str(s) for s in scopes}
        for scope in comment_targets:
            if scope in granted:
                print(f"[scope-audit] permission_status name={scope} status=granted")
            elif scope in declined:
                continue
            else:
                print(f"[scope-audit] permission_status name={scope} status=absent")
    except Exception as exc:  # pragma: no cover - prod enrichment
        print(f"[scope-audit] permission_debug_failed={type(exc).__name__}")


def _print_capability_probe(*, tenant_id: str) -> None:
    try:
        from services.channel_capability_state import comment_capability_state, dm_capability_state
        from services.entitlements_service import entitlements_store
        from services.plan_economics import PLAN_PRICES_USD
    except Exception as exc:  # pragma: no cover - prod-only enrichment
        print(f"[scope-audit] capability_probe_skipped={type(exc).__name__}")
        return
    try:
        ent = entitlements_store.get(tenant_id)
        print(f"[scope-audit] entitlement_plan={ent.plan_id} status={ent.status}")
    except Exception as exc:  # pragma: no cover
        print(f"[scope-audit] entitlement_probe_failed={type(exc).__name__}")
    print(f"[scope-audit] catalog_plans={','.join(PLAN_PRICES_USD.keys())}")
    for platform in ("facebook", "instagram"):
        st = comment_capability_state(tenant_id, platform)
        missing = ",".join(st.get("missing_scopes") or []) or "none"
        print(
            f"[scope-audit] comments platform={platform} "
            f"permission_present={st.get('permission_present')} "
            f"webhook_subscribed={st.get('webhook_subscribed')} "
            f"effective_enabled={st.get('effective_enabled')} "
            f"blocker_code={st.get('blocker_code')} "
            f"missing_scopes={missing} "
            f"advanced={st.get('app_review', {}).get('advanced_access_approved')}"
        )
        dm = dm_capability_state(tenant_id, platform)
        print(
            f"[scope-audit] dm platform={platform} "
            f"permission_present={dm.get('permission_present')} "
            f"effective_enabled={dm.get('effective_enabled')} "
            f"blocker_code={dm.get('blocker_code')}"
        )
    print("[scope-audit] capability_probe_done")


if __name__ == "__main__":
    main()
