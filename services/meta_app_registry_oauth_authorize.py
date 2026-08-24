"""OAuth asset authorization for the Meta app registry."""

from __future__ import annotations

import time
import uuid
from dataclasses import asdict
from typing import Any

from services.meta_app_registry_common import (
    AuthFlow,
    BindingStatus,
    MetaAssetBinding,
    MetaBindingConflictError,
    MetaBindingCredential,
    MetaChannel,
    authorized_meta_user_id_hash,
    binding_asset_key,
    normalize_meta_tenant_id,
)


class MetaAppRegistryOAuthAuthorizeMixin:
    _append_audit: Any
    _binding_from_dict: Any
    _cipher: Any
    _comment_permission_fields_for_binding: Any
    _locked: Any
    _read_unlocked: Any
    _write_unlocked: Any

    def _write_credential_unlocked(
        self,
        state: dict[str, Any],
        *,
        binding_id: str,
        credential_id: str,
        tenant: str,
        channel: MetaChannel,
        asset: str,
        app_key: str,
        credential: MetaBindingCredential,
        now: float,
    ) -> str:
        resolved_id = credential_id or uuid.uuid4().hex
        aad = f"{binding_id}:{resolved_id}:{tenant}:{channel}:{asset}:{app_key}"
        state["credentials"][resolved_id] = {
            "binding_id": binding_id,
            "aad": aad,
            "sealed": self._cipher.seal(credential.as_secret_dict(), aad=aad),
            "created_at": now,
            "archived_at": 0.0,
        }
        return resolved_id

    def authorize_oauth_asset(
        self,
        *,
        tenant_id: str,
        channel: MetaChannel,
        asset_id: str,
        page_id: str,
        instagram_account_id: str,
        app_key: str,
        credential: MetaBindingCredential,
        actor_id: str,
        page_name: str = "",
        instagram_username: str = "",
        status: BindingStatus = "active",
        auth_flow: AuthFlow = "facebook_login",
        webhook_subscription_status: str = "unknown",
        webhook_subscribed_fields: tuple[str, ...] = (),
        webhook_subscription_error: str = "",
        webhook_subscription_checked_at: float = 0.0,
        create_new_binding: bool = False,
    ) -> MetaAssetBinding:
        """Authorize an asset, optionally staging a new row for fail-closed verification."""

        tenant = normalize_meta_tenant_id(tenant_id)
        asset = asset_id.strip()
        if not asset:
            raise MetaBindingConflictError("asset is required")
        if create_new_binding and status != "testing":
            raise MetaBindingConflictError("new OAuth bindings must be staged for activation")
        auth_hash = authorized_meta_user_id_hash(credential.authorized_meta_user_id)
        resolved_auth_flow = auth_flow or credential.auth_flow or "facebook_login"
        requested_asset_key = binding_asset_key(tenant, app_key, channel, asset, resolved_auth_flow)
        now = time.time()
        with self._locked():
            state = self._read_unlocked()
            all_bindings = [self._binding_from_dict(value) for value in state["bindings"].values()]
            owners = [
                other for other in all_bindings if other.active and other.channel == channel and other.asset_id == asset
            ]
            if any((other.tenant_id, other.app_key) != (tenant, app_key) for other in owners):
                raise MetaBindingConflictError("asset is already active for another workspace")
            if status == "active" and any(other.asset_key != requested_asset_key for other in owners):
                raise MetaBindingConflictError("another active binding owns this asset")

            same_key = (
                []
                if create_new_binding
                else [
                    binding
                    for binding in all_bindings
                    if binding.asset_key == requested_asset_key and not binding.superseded_by_binding_id
                ]
            )
            canonical = (
                max(
                    same_key,
                    key=lambda item: (
                        {"active": 3, "disconnected": 2, "inactive": 1, "testing": 0}.get(item.status, 0),
                        item.updated_at,
                    ),
                )
                if same_key
                else None
            )

            if canonical is not None and canonical.status == "disconnected":
                raise MetaBindingConflictError("disconnected authorization must reconnect with a new binding")

            if canonical is not None:
                binding_id = canonical.binding_id
                generation = canonical.generation + 1
                created_at = canonical.created_at
                preserved_fields = webhook_subscribed_fields or canonical.webhook_subscribed_fields
                preserved_status = (
                    webhook_subscription_status
                    if webhook_subscription_status != "unknown" or not canonical.webhook_subscription_status
                    else canonical.webhook_subscription_status
                )
                preserved_error = (
                    webhook_subscription_error
                    if webhook_subscription_error or not canonical.webhook_subscription_error
                    else canonical.webhook_subscription_error
                )
                preserved_checked_at = (
                    webhook_subscription_checked_at
                    if webhook_subscription_checked_at > 0
                    else canonical.webhook_subscription_checked_at
                )
                credential_id = self._write_credential_unlocked(
                    state,
                    binding_id=binding_id,
                    credential_id=canonical.credential_id,
                    tenant=tenant,
                    channel=channel,
                    asset=asset,
                    app_key=app_key,
                    credential=credential,
                    now=now,
                )
                updated = MetaAssetBinding(
                    binding_id=binding_id,
                    tenant_id=tenant,
                    channel=channel,
                    asset_id=asset,
                    page_id=page_id.strip(),
                    instagram_account_id=instagram_account_id.strip(),
                    app_key=app_key,
                    credential_id=credential_id,
                    status=status,
                    generation=generation,
                    created_at=created_at,
                    updated_at=now,
                    previous_binding_id=canonical.previous_binding_id,
                    page_name=page_name.strip(),
                    instagram_username=instagram_username.strip(),
                    authorized_meta_user_id_hash=auth_hash,
                    superseded_by_binding_id="",
                    auth_flow=resolved_auth_flow,
                    webhook_subscription_status=preserved_status,
                    webhook_subscribed_fields=tuple(preserved_fields),
                    webhook_subscription_error=preserved_error,
                    webhook_subscription_checked_at=preserved_checked_at,
                    **self._comment_permission_fields_for_binding(
                        MetaAssetBinding(
                            binding_id=binding_id,
                            tenant_id=tenant,
                            channel=channel,
                            asset_id=asset,
                            page_id=page_id.strip(),
                            instagram_account_id=instagram_account_id.strip(),
                            app_key=app_key,
                            credential_id=credential_id,
                            status=status,
                            generation=generation,
                            created_at=created_at,
                            updated_at=now,
                            auth_flow=resolved_auth_flow,
                        ),
                        credential,
                        now=now,
                    ),
                )
                state["bindings"][binding_id] = asdict(updated)
                for duplicate in same_key:
                    if duplicate.binding_id == binding_id:
                        continue
                    raw = dict(state["bindings"][duplicate.binding_id])
                    raw["superseded_by_binding_id"] = binding_id
                    raw["generation"] = duplicate.generation + 1
                    raw["updated_at"] = now
                    state["bindings"][duplicate.binding_id] = raw
                self._write_unlocked(state)
                self._append_audit(
                    {
                        "event": "binding_reauthorized",
                        "actor_id": actor_id,
                        "tenant_id": tenant,
                        "channel": channel,
                        "asset_id": asset,
                        "app_key": app_key,
                        "binding_id": binding_id,
                    }
                )
                return updated

            binding_id = uuid.uuid4().hex
            credential_id = self._write_credential_unlocked(
                state,
                binding_id=binding_id,
                credential_id="",
                tenant=tenant,
                channel=channel,
                asset=asset,
                app_key=app_key,
                credential=credential,
                now=now,
            )
            binding = MetaAssetBinding(
                binding_id=binding_id,
                tenant_id=tenant,
                channel=channel,
                asset_id=asset,
                page_id=page_id.strip(),
                instagram_account_id=instagram_account_id.strip(),
                app_key=app_key,
                credential_id=credential_id,
                status=status,
                generation=1,
                created_at=now,
                updated_at=now,
                page_name=page_name.strip(),
                instagram_username=instagram_username.strip(),
                authorized_meta_user_id_hash=auth_hash,
                auth_flow=resolved_auth_flow,
                webhook_subscription_status=webhook_subscription_status,
                webhook_subscribed_fields=webhook_subscribed_fields,
                webhook_subscription_error=webhook_subscription_error,
                webhook_subscription_checked_at=webhook_subscription_checked_at,
                **self._comment_permission_fields_for_binding(
                    MetaAssetBinding(
                        binding_id=binding_id,
                        tenant_id=tenant,
                        channel=channel,
                        asset_id=asset,
                        page_id=page_id.strip(),
                        instagram_account_id=instagram_account_id.strip(),
                        app_key=app_key,
                        credential_id=credential_id,
                        status=status,
                        generation=1,
                        created_at=now,
                        updated_at=now,
                        auth_flow=resolved_auth_flow,
                    ),
                    credential,
                    now=now,
                ),
            )
            state["bindings"][binding_id] = asdict(binding)
            self._write_unlocked(state)
            self._append_audit(
                {
                    "event": "binding_authorized",
                    "actor_id": actor_id,
                    "tenant_id": tenant,
                    "channel": channel,
                    "asset_id": asset,
                    "app_key": app_key,
                    "binding_id": binding_id,
                }
            )
            return binding
