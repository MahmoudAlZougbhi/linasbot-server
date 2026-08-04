#!/usr/bin/env python3
"""Validate and seed App A's two active bindings without rendering secrets."""

from __future__ import annotations

import os
import urllib.parse

from scripts.validate_meta_social_token import (
    EXPECTED_GRAPH_VERSION,
    EXPECTED_INSTAGRAM_ID,
    EXPECTED_PAGE_ID,
    REQUIRED_SCOPES,
    MetaTokenValidationError,
    _mapping,
    _request_json,
    validate_payloads,
)
from services.meta_app_registry import (
    APP_A_EXPECTED_ID,
    APP_A_KEY,
    META_FORBIDDEN_SCOPES,
    MetaAppRegistry,
    MetaBindingCredential,
    get_meta_app_configs,
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
    raw_scopes = debug_data.get("scopes")
    scopes = tuple(sorted({str(scope) for scope in raw_scopes})) if isinstance(raw_scopes, list) else ()
    if not REQUIRED_SCOPES.issubset(scopes):
        raise MetaTokenValidationError("App A token is missing a required messaging permission")
    if set(scopes) & META_FORBIDDEN_SCOPES:
        raise MetaTokenValidationError("App A token includes a prohibited non-messaging permission")
    expires_raw = debug_data.get("expires_at")
    expires_at = (
        int(expires_raw)
        if isinstance(expires_raw, (int, str)) and not isinstance(expires_raw, bool) and str(expires_raw) != "0"
        else None
    )

    credential = MetaBindingCredential(
        access_token=page_token,
        token_app_id=app.app_id,
        token_profile_id=EXPECTED_PAGE_ID,
        scopes=scopes,
        expires_at=expires_at,
    )
    registry = MetaAppRegistry(master_secret=encryption_key)
    expected = {
        "facebook": EXPECTED_PAGE_ID,
        "instagram": EXPECTED_INSTAGRAM_ID,
    }
    for channel, asset_id in expected.items():
        current = next(
            (
                binding
                for binding in registry.get_active_bindings_for_app(APP_A_KEY)
                if binding.tenant_id == "linas" and binding.channel == channel and binding.asset_id == asset_id
            ),
            None,
        )
        if current is not None:
            stored = registry.get_credential(current)
            if (
                stored.access_token == page_token
                and stored.token_app_id == app.app_id
                and stored.token_profile_id == EXPECTED_PAGE_ID
                and REQUIRED_SCOPES.issubset(stored.scopes)
            ):
                print(f"[meta-registry-seed] channel={channel} status=already_active")
                continue
        registry.activate_binding(
            tenant_id="linas",
            channel=channel,  # type: ignore[arg-type]
            asset_id=asset_id,
            page_id=EXPECTED_PAGE_ID,
            instagram_account_id=EXPECTED_INSTAGRAM_ID,
            app_key=APP_A_KEY,
            credential=credential,
            actor_id="production-seed",
            replace_existing=True,
        )
        print(f"[meta-registry-seed] channel={channel} status=active")
    print("[meta-registry-seed] app_a_id_match=true")
    print("[meta-registry-seed] page_id_match=true")
    print("[meta-registry-seed] instagram_account_id_match=true")
    print("[meta-registry-seed] SUCCESS")


if __name__ == "__main__":
    main()
