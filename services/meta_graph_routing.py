"""Shared Meta Graph host, scope, and settings routing for auth_flow-aware bindings."""

from __future__ import annotations

from services.meta_app_registry import (
    META_COMMENT_SCOPES,
    META_PUBLISH_SCOPES,
    MetaAppConfig,
    MetaAppRegistry,
    MetaAssetBinding,
    MetaBindingCredential,
    get_meta_app_configs,
    get_meta_app_registry,
    get_meta_graph_api_version,
)
from services.meta_instagram_login_config import (
    META_INSTAGRAM_GRAPH_BASE_URL,
    instagram_login_app_id,
    instagram_login_app_secret,
    instagram_login_webhook_verify_token,
)
from services.meta_messaging import MetaMessagingSettings

FACEBOOK_GRAPH_BASE_URL = "https://graph.facebook.com"


def graph_base_url_for_binding(binding: MetaAssetBinding) -> str:
    if binding.auth_flow == "instagram_login":
        return META_INSTAGRAM_GRAPH_BASE_URL
    return FACEBOOK_GRAPH_BASE_URL


def graph_api_url(binding: MetaAssetBinding, *, graph_api_version: str, path: str) -> str:
    base = graph_base_url_for_binding(binding).rstrip("/")
    version = graph_api_version if graph_api_version.startswith("v") else f"v{graph_api_version}"
    normalized = path.lstrip("/")
    return f"{base}/{version}/{normalized}"


def required_comment_scopes_for_binding(binding: MetaAssetBinding) -> frozenset[str]:
    if binding.auth_flow == "instagram_login" and binding.channel == "instagram":
        return frozenset({"instagram_business_manage_comments"})
    return META_COMMENT_SCOPES.get(binding.channel, frozenset())


def required_publish_scopes_for_binding(binding: MetaAssetBinding) -> frozenset[str]:
    if binding.auth_flow == "instagram_login" and binding.channel == "instagram":
        return frozenset({"instagram_business_content_publish"})
    return META_PUBLISH_SCOPES.get(binding.channel, frozenset())


def credential_has_comment_scopes(
    binding: MetaAssetBinding,
    registry: MetaAppRegistry | None = None,
) -> bool:
    current_registry = registry or get_meta_app_registry()
    credential = current_registry.get_credential(binding)
    return required_comment_scopes_for_binding(binding).issubset(credential.scopes)


def credential_has_publish_scopes(
    binding: MetaAssetBinding,
    registry: MetaAppRegistry | None = None,
) -> bool:
    current_registry = registry or get_meta_app_registry()
    credential = current_registry.get_credential(binding)
    return required_publish_scopes_for_binding(binding).issubset(credential.scopes)


def build_messaging_settings_for_binding(
    binding: MetaAssetBinding,
    *,
    credential: MetaBindingCredential,
    app_config: MetaAppConfig | None = None,
) -> MetaMessagingSettings:
    resolved_app = app_config or get_meta_app_configs()[binding.app_key]
    graph_api_version = resolved_app.graph_api_version or get_meta_graph_api_version()
    if binding.auth_flow == "instagram_login":
        return MetaMessagingSettings(
            enabled=True,
            app_secret=instagram_login_app_secret(),
            page_id=binding.page_id,
            page_access_token=credential.access_token,
            instagram_account_id=binding.instagram_account_id or binding.asset_id,
            verify_token=instagram_login_webhook_verify_token(),
            graph_api_version=graph_api_version,
            app_id=instagram_login_app_id(),
            app_key=binding.app_key,
            tenant_id=binding.tenant_id,
            binding_id=binding.binding_id,
            auth_flow=binding.auth_flow,
            graph_base_url=META_INSTAGRAM_GRAPH_BASE_URL,
        )
    return MetaMessagingSettings(
        enabled=True,
        app_secret=resolved_app.app_secret,
        page_id=binding.page_id,
        page_access_token=credential.access_token,
        instagram_account_id=binding.instagram_account_id or binding.asset_id,
        verify_token=resolved_app.verify_token,
        graph_api_version=graph_api_version,
        app_id=resolved_app.app_id,
        app_key=resolved_app.key,
        tenant_id=binding.tenant_id,
        binding_id=binding.binding_id,
        auth_flow=binding.auth_flow,
        graph_base_url=FACEBOOK_GRAPH_BASE_URL,
    )
