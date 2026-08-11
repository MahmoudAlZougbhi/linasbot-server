"""Encrypted registry for Meta apps, tenant assets, OAuth state, and rollback.

The registry intentionally stores application secrets in the process environment and
tenant/Page tokens only as AES-GCM ciphertext. Active bindings are exclusive per
channel/asset_id globally, so two Meta apps can never answer the same Page or
Instagram account at the same time. A workspace may own multiple assets per channel.

Helpers: meta_app_registry_common; mixins: bindings/lifecycle/oauth (LOC split).
"""

from __future__ import annotations

import os
import time

from services.meta_app_registry_bindings import MetaAppRegistryBindingsMixin
from services.meta_app_registry_common import (
    APP_A_EXPECTED_ID,
    APP_A_KEY,
    APP_B_KEY,
    FACEBOOK_ONLY_LOGIN_CONFIG_ID_DEFAULT,
    LINAS_INSTAGRAM_ACCOUNT_ID,
    LINAS_PAGE_ID,
    META_CHANNEL_SCOPES,
    META_COMMENT_SCOPES,
    META_COMMON_MESSAGING_SCOPES,
    META_FACEBOOK_LOGIN_EXTRA_SCOPES,
    META_FORBIDDEN_SCOPES,
    META_PUBLISH_SCOPES,
    REGISTRY_SCHEMA_VERSION,
    AuthFlow,
    BindingStatus,
    MetaAppClassification,
    MetaAppConfig,
    MetaAssetBinding,
    MetaBindingConflictError,
    MetaBindingCredential,
    MetaBindingNotFoundError,
    MetaChannel,
    MetaCredentialCipher,
    MetaCredentialError,
    MetaOAuthStateError,
    MetaRegistryError,
    MetaRegistryNotConfiguredError,
    _app_b_linas_cutover_allowed,
    _bindings_share_exclusive_asset,
    _normalized_graph_version,
    _truthy,
    authorized_meta_user_id_hash,
    binding_asset_key,
    get_meta_app_configs,
    get_meta_graph_api_version,
    identify_signed_meta_app,
    mask_asset_id,
    meta_multi_app_registry_enabled,
    normalize_meta_tenant_id,
    verify_any_meta_challenge_token,
)
from services.meta_app_registry_lifecycle import MetaAppRegistryLifecycleMixin
from services.meta_app_registry_oauth import MetaAppRegistryOAuthMixin

__all__ = [
    "APP_A_EXPECTED_ID",
    "APP_A_KEY",
    "APP_B_KEY",
    "FACEBOOK_ONLY_LOGIN_CONFIG_ID_DEFAULT",
    "LINAS_INSTAGRAM_ACCOUNT_ID",
    "LINAS_PAGE_ID",
    "META_CHANNEL_SCOPES",
    "META_COMMENT_SCOPES",
    "META_COMMON_MESSAGING_SCOPES",
    "META_FACEBOOK_LOGIN_EXTRA_SCOPES",
    "META_FORBIDDEN_SCOPES",
    "META_PUBLISH_SCOPES",
    "REGISTRY_SCHEMA_VERSION",
    "AuthFlow",
    "BindingStatus",
    "MetaAppClassification",
    "MetaAppConfig",
    "MetaAppRegistry",
    "MetaAssetBinding",
    "MetaBindingConflictError",
    "MetaBindingCredential",
    "MetaBindingNotFoundError",
    "MetaChannel",
    "MetaCredentialCipher",
    "MetaCredentialError",
    "MetaOAuthStateError",
    "MetaRegistryError",
    "MetaRegistryNotConfiguredError",
    "_app_b_linas_cutover_allowed",
    "_bindings_share_exclusive_asset",
    "_normalized_graph_version",
    "_truthy",
    "authorized_meta_user_id_hash",
    "binding_asset_key",
    "get_meta_app_configs",
    "get_meta_app_registry",
    "get_meta_graph_api_version",
    "get_meta_registry_readiness",
    "identify_signed_meta_app",
    "mask_asset_id",
    "meta_multi_app_registry_enabled",
    "normalize_meta_tenant_id",
    "reset_meta_app_registry_for_tests",
    "verify_any_meta_challenge_token",
]


class MetaAppRegistry(
    MetaAppRegistryBindingsMixin,
    MetaAppRegistryLifecycleMixin,
    MetaAppRegistryOAuthMixin,
):
    """File-backed, process-safe registry with encrypted credential envelopes."""


_registry_instance: MetaAppRegistry | None = None


def get_meta_app_registry() -> MetaAppRegistry:
    global _registry_instance
    if _registry_instance is None:
        _registry_instance = MetaAppRegistry()
    return _registry_instance


def reset_meta_app_registry_for_tests() -> None:
    global _registry_instance
    _registry_instance = None


def get_meta_registry_readiness(
    registry: MetaAppRegistry | None = None,
) -> tuple[bool, dict[str, bool]]:
    """Fail-closed readiness for enabling the encrypted multi-app router."""

    checks: dict[str, bool] = {
        "encryption_key_configured": len((os.getenv("META_CREDENTIAL_ENCRYPTION_KEY") or "").strip()) >= 32,
        "app_a_configured": get_meta_app_configs()[APP_A_KEY].enabled,
        "linas_facebook_app_a_active": False,
        "linas_instagram_app_a_active": False,
        "active_indexes_exclusive": True,
        "active_credentials_valid": True,
        "app_b_not_active_on_linas": True,
    }
    try:
        current_registry = registry or get_meta_app_registry()
        bindings = current_registry.list_bindings(include_inactive=False)
        active_asset_keys: set[str] = set()
        now = int(time.time())
        for binding in bindings:
            if binding.asset_key in active_asset_keys:
                checks["active_indexes_exclusive"] = False
            active_asset_keys.add(binding.asset_key)
            if binding.app_key == APP_B_KEY and binding.asset_id in {
                LINAS_PAGE_ID,
                LINAS_INSTAGRAM_ACCOUNT_ID,
            }:
                checks["app_b_not_active_on_linas"] = False
            try:
                credential = current_registry.get_credential(binding)
                app = get_meta_app_configs().get(binding.app_key)
                from services.meta_instagram_login_config import required_scopes_for_binding

                required_scopes = required_scopes_for_binding(
                    channel=binding.channel,
                    auth_flow=binding.auth_flow,
                )
                instagram_login_app_id = (os.getenv("META_INSTAGRAM_LOGIN_APP_ID") or "1035856539045307").strip()
                if (
                    app is None
                    or not app.enabled
                    or (
                        credential.token_app_id != app.app_id
                        and not (
                            binding.auth_flow == "instagram_login" and credential.token_app_id == instagram_login_app_id
                        )
                    )
                    or (binding.auth_flow == "facebook_login" and credential.token_profile_id != binding.page_id)
                    or (binding.auth_flow == "instagram_login" and credential.token_profile_id != binding.asset_id)
                    or not required_scopes.issubset(credential.scopes)
                    or set(credential.scopes) & META_FORBIDDEN_SCOPES
                    or (credential.expires_at is not None and credential.expires_at <= now)
                    or (
                        binding.auth_flow == "instagram_login"
                        and binding.active
                        and binding.webhook_subscription_status != "ready"
                    )
                ):
                    checks["active_credentials_valid"] = False
            except MetaRegistryError:
                checks["active_credentials_valid"] = False
            if (
                binding.app_key == APP_A_KEY
                and binding.tenant_id == "linas"
                and binding.channel == "facebook"
                and binding.asset_id == LINAS_PAGE_ID
            ):
                checks["linas_facebook_app_a_active"] = True
            if (
                binding.app_key == APP_A_KEY
                and binding.tenant_id == "linas"
                and binding.channel == "instagram"
                and binding.asset_id == LINAS_INSTAGRAM_ACCOUNT_ID
            ):
                checks["linas_instagram_app_a_active"] = True
    except MetaRegistryError:
        checks["active_indexes_exclusive"] = False
        checks["active_credentials_valid"] = False
    return all(checks.values()), checks
