#!/usr/bin/env python3
"""Validate App A's Page token and seed only its Facebook Page binding."""

from __future__ import annotations

import os
import urllib.parse

from scripts.validate_meta_social_token import (
    EXPECTED_GRAPH_VERSION,
    EXPECTED_INSTAGRAM_ID,
    EXPECTED_PAGE_ID,
    MetaTokenValidationError,
    _mapping,
    _request_json,
    validate_payloads,
)
from services.meta_app_registry import (
    APP_A_EXPECTED_ID,
    APP_A_KEY,
    MetaAppRegistry,
    MetaBindingCredential,
    get_meta_app_configs,
)
from services.meta_facebook_scope_policy import (
    FACEBOOK_PAGE_BINDING_SCOPES,
    facebook_page_granular_targets_are_allowlisted,
    normalize_facebook_page_token_scopes,
)


def _required_env(name: str) -> str:
    value = (os.getenv(name) or "").strip()
    if not value:
        raise MetaTokenValidationError(f"Required environment variable is missing: {name}")
    return value


def main() -> None:
    app = get_meta_app_configs()[APP_A_KEY]
    if not app.enabled or app.app_id != APP_A_EXPECTED_ID:
        raise MetaTokenValidationError("App A configuration is missing or has an unexpected App ID")
    page_token = _required_env("META_PAGE_ACCESS_TOKEN")
    encryption_key = _required_env("META_CREDENTIAL_ENCRYPTION_KEY")
    if app.graph_api_version != EXPECTED_GRAPH_VERSION:
        raise MetaTokenValidationError("Unexpected Meta Graph API version")

    base = f"https://graph.facebook.com/{app.graph_api_version}"
    debug_query = urllib.parse.urlencode(
        {
            "input_token": page_token,
            "access_token": f"{app.app_id}|{app.app_secret}",
        }
    )
    debug_payload = _request_json(f"{base}/debug_token?{debug_query}", stage="registry_debug_token")
    page_payload = _request_json(
        f"{base}/{EXPECTED_PAGE_ID}?fields=id,instagram_business_account{{id}}",
        bearer=page_token,
        stage="registry_page_relationship",
    )
    validate_payloads(debug_payload, page_payload, page_payload, expected_app_id=app.app_id)
    debug_data = _mapping(debug_payload.get("data"))
    if not facebook_page_granular_targets_are_allowlisted(
        debug_data,
        page_id=EXPECTED_PAGE_ID,
    ):
        raise MetaTokenValidationError("App A token includes a granular permission target for another asset")
    raw_scopes = debug_data.get("scopes")
    raw_token_scopes = tuple(sorted({str(scope) for scope in raw_scopes})) if isinstance(raw_scopes, list) else ()
    scopes, forbidden = normalize_facebook_page_token_scopes(raw_token_scopes)
    if forbidden:
        raise MetaTokenValidationError("App A token includes a prohibited non-messaging permission")
    if not FACEBOOK_PAGE_BINDING_SCOPES.issubset(scopes):
        raise MetaTokenValidationError("App A token is missing a required DM or comment permission")
    expires_raw = debug_data.get("expires_at")
    expires_at = (
        int(expires_raw)
        if isinstance(expires_raw, (int, str)) and not isinstance(expires_raw, bool) and str(expires_raw) != "0"
        else None
    )
    authorized_meta_user_id = str(debug_data.get("user_id") or "").strip()
    if not authorized_meta_user_id.isdigit() or not 3 <= len(authorized_meta_user_id) <= 64:
        raise MetaTokenValidationError("App A token authorization owner is unavailable")

    credential = MetaBindingCredential(
        access_token=page_token,
        token_app_id=app.app_id,
        token_profile_id=EXPECTED_PAGE_ID,
        scopes=scopes,
        expires_at=expires_at,
        authorized_meta_user_id=authorized_meta_user_id,
    )
    registry = MetaAppRegistry(master_secret=encryption_key)
    current = next(
        (
            binding
            for binding in registry.get_active_bindings_for_app(APP_A_KEY)
            if binding.tenant_id == "linas" and binding.channel == "facebook" and binding.asset_id == EXPECTED_PAGE_ID
        ),
        None,
    )
    already_active = False
    if current is not None:
        stored = registry.get_credential(current)
        already_active = (
            stored.access_token == page_token
            and stored.token_app_id == app.app_id
            and stored.token_profile_id == EXPECTED_PAGE_ID
            and stored.authorized_meta_user_id == authorized_meta_user_id
            and set(stored.scopes) == set(scopes)
        )
    if not already_active:
        registry.activate_binding(
            tenant_id="linas",
            channel="facebook",
            asset_id=EXPECTED_PAGE_ID,
            page_id=EXPECTED_PAGE_ID,
            instagram_account_id=EXPECTED_INSTAGRAM_ID,
            app_key=APP_A_KEY,
            credential=credential,
            actor_id="production-seed",
            replace_existing=True,
        )
    print(f"[meta-registry-seed] channel=facebook status={'already_active' if already_active else 'active'}")
    print("[meta-registry-seed] app_a_id_match=true")
    print("[meta-registry-seed] page_id_match=true")
    print("[meta-registry-seed] instagram_relationship_match=true")
    print("[meta-registry-seed] direct_instagram_binding_seeded=false")
    print("[meta-registry-seed] SUCCESS")


if __name__ == "__main__":
    main()
