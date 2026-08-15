#!/usr/bin/env python3
"""Read-only audit of App A binding scopes (no tokens or secrets printed)."""

from __future__ import annotations

import os
from collections.abc import Sequence
from pathlib import Path
from typing import TYPE_CHECKING

from dotenv import load_dotenv

if TYPE_CHECKING:
    from services.meta_app_registry_common import MetaAssetBinding

FACEBOOK_PAGE_REVIEW_SCOPES = frozenset(
    {
        "pages_show_list",
        "pages_manage_metadata",
        "pages_read_engagement",
        "pages_messaging",
        "pages_read_user_content",
        "pages_manage_engagement",
    }
)
# Back-compatible export for the focused tests and external read-only callers.
# ``business_management`` belongs to the user/integration token and is proven
# during the OAuth callback; it is not expected on the resulting Page token.
FACEBOOK_REVIEW_SCOPES = FACEBOOK_PAGE_REVIEW_SCOPES
FACEBOOK_LOGIN_REVIEW_SCOPES = frozenset({"business_management"})


def _load_runtime_environment(env_path: str | Path | None = None) -> Path | None:
    """Parse the production dotenv file without evaluating it as shell code."""

    raw_path = str(env_path or os.getenv("META_SCOPE_AUDIT_ENV_FILE") or "").strip()
    if not raw_path:
        return None
    path = Path(raw_path).expanduser()
    if not path.is_file():
        raise SystemExit(f"Configured scope-audit env file is missing: {path}")
    load_dotenv(dotenv_path=path, override=False)
    return path


def _truthy(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _print_cm_comment_actions(tenant_id: str) -> dict[str, bool]:
    from services.cm.actions import (
        ACTION_FACEBOOK_COMMENTS,
        ACTION_INSTAGRAM_COMMENTS,
        action_enabled,
        load_actions_section,
    )

    actions = load_actions_section(tenant_id)
    print(f"[scope-audit] tenant={tenant_id}")
    states = {
        "facebook": action_enabled(actions, ACTION_FACEBOOK_COMMENTS),
        "instagram": action_enabled(actions, ACTION_INSTAGRAM_COMMENTS),
    }
    print(f"[scope-audit] cm_action_{ACTION_FACEBOOK_COMMENTS}={states['facebook']}")
    print(f"[scope-audit] cm_action_{ACTION_INSTAGRAM_COMMENTS}={states['instagram']}")
    print(f"[scope-audit] cm_disable_linas_legacy_bridge={os.getenv('CM_DISABLE_LINAS_LEGACY_BRIDGE', '')}")
    print(f"[scope-audit] customer_retrieval_model={os.getenv('LINAS_CUSTOMER_RETRIEVAL_MODEL', 'gpt-5.6-luna')}")
    print(f"[scope-audit] customer_answer_model={os.getenv('LINAS_CUSTOMER_ANSWER_MODEL', 'gpt-5.6-terra')}")
    print(f"[scope-audit] customer_media_context={os.getenv('CUSTOMER_MEDIA_CONTEXT_ENABLED', 'true')}")
    print(
        f"[scope-audit] meta_app_a_advanced_access_approved="
        f"{(os.getenv('META_APP_A_ADVANCED_ACCESS_APPROVED') or '').strip().lower() or 'unset'}"
    )
    return states


def _select_required_social_bindings(
    bindings: Sequence[MetaAssetBinding],
    *,
    tenant_id: str,
    expected_page_id: str,
    expected_instagram_id: str,
) -> tuple[list[MetaAssetBinding], list[str]]:
    """Select exactly the Lina Facebook and Direct-IG production surfaces."""

    tenant_bindings = [item for item in bindings if str(getattr(item, "tenant_id", "")) == tenant_id]
    expected = (
        ("facebook", "facebook_login", expected_page_id),
        ("instagram", "instagram_login", expected_instagram_id),
    )
    selected: list[MetaAssetBinding] = []
    failures: list[str] = []
    for channel, auth_flow, asset_id in expected:
        matching = [
            item
            for item in tenant_bindings
            if str(getattr(item, "channel", "")) == channel
            and str(getattr(item, "auth_flow", "")) == auth_flow
            and str(getattr(item, "asset_id", "")) == asset_id
        ]
        if len(matching) != 1:
            failures.append(f"required_binding_{channel}_{auth_flow}_count_{len(matching)}")
            continue
        selected.append(matching[0])
    return selected, failures


def main() -> None:
    _load_runtime_environment()
    # Import runtime services only after dotenv is loaded; several storage/config
    # modules resolve their paths and backends during import.
    from services.meta_app_registry import APP_A_KEY, get_meta_app_registry
    from services.meta_comment_reply_settings import get_comment_reply_setting
    from services.meta_facebook_scope_policy import normalize_facebook_page_token_scopes
    from services.meta_graph_routing import (
        required_comment_scopes_for_binding,
        required_publish_scopes_for_binding,
    )
    from services.meta_instagram_login_config import required_scopes_for_binding

    app_id = (os.getenv("META_APP_ID") or os.getenv("META_APP_A_ID") or "").strip()
    if app_id != "2963733803971681":
        raise SystemExit("Refusing unexpected Meta App ID")
    tenant_id = (os.getenv("META_COMMENT_AUDIT_TENANT") or "linas").strip() or "linas"
    expected_page_id = (os.getenv("META_SCOPE_AUDIT_PAGE_ID") or "378696005334409").strip()
    expected_instagram_id = (os.getenv("META_SCOPE_AUDIT_INSTAGRAM_ID") or "17841413184256533").strip()
    registry = get_meta_app_registry()
    active_app_bindings = [
        item
        for item in registry.list_bindings(include_superseded=False)
        if item.app_key == APP_A_KEY and item.status == "active"
    ]
    bindings, binding_failures = _select_required_social_bindings(
        active_app_bindings,
        tenant_id=tenant_id,
        expected_page_id=expected_page_id,
        expected_instagram_id=expected_instagram_id,
    )
    comment_actions = _print_cm_comment_actions(tenant_id)
    strict_comments = _truthy(os.getenv("META_SCOPE_AUDIT_REQUIRE_COMMENTS"))
    strict_failures = len(binding_failures)
    print(f"[scope-audit] active_app_bindings={len(active_app_bindings)}")
    print(f"[scope-audit] required_bindings={len(bindings)}")
    for failure in binding_failures:
        print(f"[scope-audit] binding_failure={failure}")
    for binding in bindings:
        credential = registry.get_credential(binding)
        granted = set(credential.scopes)
        masked = binding.asset_id[-6:] if binding.asset_id else "unknown"
        print(
            f"[scope-audit] channel={binding.channel} auth_flow={binding.auth_flow} "
            f"asset_suffix={masked} binding_suffix={binding.binding_id[-6:]}"
        )
        required_dm = sorted(
            required_scopes_for_binding(
                channel=binding.channel,
                auth_flow=binding.auth_flow,
            )
        )
        for scope in required_dm:
            print(f"[scope-audit] dm_scope_{scope}={scope in granted}")
        required_comment = sorted(required_comment_scopes_for_binding(binding))
        for scope in required_comment:
            print(f"[scope-audit] comment_scope_{scope}={scope in granted}")
        required_publish = sorted(required_publish_scopes_for_binding(binding))
        for scope in required_publish:
            print(f"[scope-audit] publish_scope_{scope}={scope in granted}")
        dm_ready = set(required_dm).issubset(granted)
        comment_ready = set(required_comment).issubset(granted)
        publish_ready = set(required_publish).issubset(granted)
        setting = get_comment_reply_setting(
            tenant_id=binding.tenant_id,
            app_key=binding.app_key,
            channel=binding.channel,
            asset_id=binding.asset_id,
        )
        print(f"[scope-audit] dm_features_ready={dm_ready}")
        print(f"[scope-audit] comment_features_ready={comment_ready}")
        print(f"[scope-audit] publish_features_ready={publish_ready}")
        print(f"[scope-audit] per_asset_comment_enabled={bool(setting.enabled)}")
        declined = sorted(set(credential.declined_scopes or ()))
        print(f"[scope-audit] declined_scopes={','.join(declined) or 'none'}")
        print(
            f"[scope-audit] webhook_subscribed_fields={','.join(sorted(binding.webhook_subscribed_fields)) or 'none'}"
        )
        if not dm_ready:
            strict_failures += 1
        if strict_comments:
            comment_field = "feed" if binding.channel == "facebook" else "comments"
            if not comment_ready:
                strict_failures += 1
            if comment_field not in set(binding.webhook_subscribed_fields):
                strict_failures += 1
            if not setting.enabled:
                strict_failures += 1
            if not comment_actions.get(binding.channel, False):
                strict_failures += 1
        if binding.channel == "facebook" and binding.auth_flow == "facebook_login":
            _persisted, prohibited = normalize_facebook_page_token_scopes(granted)
            print(f"[scope-audit] page_token_prohibited_scopes={','.join(prohibited) or 'none'}")
            print("[scope-audit] business_management_proof=oauth_callback_and_login_configuration")
            if prohibited:
                strict_failures += 1
        live_required = FACEBOOK_PAGE_REVIEW_SCOPES if strict_comments else frozenset(required_dm)
        live_scope_ready = _print_debug_permission_statuses(
            credential,
            auth_flow=binding.auth_flow,
            required_scopes=live_required,
        )
        if binding.channel == "facebook" and live_scope_ready is not True:
            strict_failures += 1
    for root in (
        Path("/opt/linasbot_data/meta_comment_settings"),
        Path("/opt/linasbot/data/meta_comment_settings"),
    ):
        print(f"[scope-audit] comment_settings_dir path={root} exists={root.is_dir()}")
    _print_capability_probe(tenant_id=tenant_id)
    print(f"[scope-audit] strict_comments={strict_comments}")
    print(f"[scope-audit] strict_failure_count={strict_failures}")
    if strict_failures:
        raise SystemExit("Meta scope readiness gate failed")
    print("[scope-audit] SUCCESS")


def _print_debug_permission_statuses(
    credential: object,
    *,
    auth_flow: str,
    required_scopes: frozenset[str] = FACEBOOK_PAGE_REVIEW_SCOPES,
) -> bool | None:
    """Print Meta debug_token permission names + status only (never tokens)."""

    if auth_flow == "instagram_login":
        # Direct Instagram credentials belong to a separate app/secret and host.
        # Never send them to App A's Facebook debug_token endpoint.
        print("[scope-audit] permission_debug=skipped_direct_instagram_trust_domain")
        return None
    try:
        import json
        import urllib.parse
        import urllib.request

        token = str(getattr(credential, "access_token", "") or "").strip()
        app_id = (os.getenv("META_APP_ID") or os.getenv("META_APP_A_ID") or "").strip()
        app_secret = (os.getenv("META_APP_SECRET") or os.getenv("META_APP_A_SECRET") or "").strip()
        if not token or not app_id or not app_secret:
            print("[scope-audit] permission_debug=skipped_missing_inputs")
            return False
        app_token = f"{app_id}|{app_secret}"
        query = urllib.parse.urlencode({"input_token": token, "access_token": app_token})
        url = f"https://graph.facebook.com/v24.0/debug_token?{query}"
        with urllib.request.urlopen(url, timeout=20) as response:
            payload = json.loads(response.read(500_000))
        data = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(data, dict):
            print("[scope-audit] permission_debug=invalid_response")
            return False
        scopes_raw = data.get("scopes")
        scopes_list: list[object] = list(scopes_raw) if isinstance(scopes_raw, list) else []
        granular_raw = data.get("granular_scopes")
        granular_list: list[object] = list(granular_raw) if isinstance(granular_raw, list) else []
        token_is_valid = data.get("is_valid") is True
        print(f"[scope-audit] debug_token_is_valid={token_is_valid}")
        print(f"[scope-audit] debug_token_scopes={','.join(str(s) for s in scopes_list) or 'none'}")
        for row in granular_list:
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
        granted = {str(s) for s in scopes_list}
        for scope in comment_targets:
            if scope in granted:
                print(f"[scope-audit] permission_status name={scope} status=granted")
            elif scope in declined:
                continue
            else:
                print(f"[scope-audit] permission_status name={scope} status=absent")
        live_ready = token_is_valid and set(required_scopes).issubset(granted)
        print(f"[scope-audit] live_required_scopes_ready={live_ready}")
        return live_ready
    except Exception as exc:  # pragma: no cover - prod enrichment
        print(f"[scope-audit] permission_debug_failed={type(exc).__name__}")
        return False


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
