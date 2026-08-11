"""MetaAppRegistry staged activation, credentials, and OAuth state (LOC split)."""

from __future__ import annotations

import re
import time
from typing import Any, cast

from services.meta_app_registry_common import (
    AuthFlow,
    MetaAssetBinding,
    MetaBindingConflictError,
    MetaBindingCredential,
    MetaBindingNotFoundError,
    MetaCredentialError,
    MetaOAuthStateError,
    MetaRegistryError,
    _bindings_share_exclusive_asset,
)


class MetaAppRegistryOAuthMixin:
    """Staged activation, credentials, revoke/rollback, and OAuth state."""

    def activate_staged_binding(
        self,
        binding_id: str,
        *,
        actor_id: str,
        expected_generation: int | None = None,
        replace_existing: bool = False,
    ) -> MetaAssetBinding:
        """Atomically activate a staged binding and optionally replace one provider."""

        with self._locked():
            state = self._read_unlocked()
            raw = state["bindings"].get(binding_id)
            if not isinstance(raw, dict):
                raise MetaBindingNotFoundError("binding not found")
            current = self._binding_from_dict(raw)
            if current.status not in {"testing", "inactive"}:
                raise MetaBindingConflictError("binding is not staged for activation")
            if expected_generation is not None and current.generation != expected_generation:
                raise MetaBindingConflictError("binding generation changed")
            conflicts: list[MetaAssetBinding] = []
            for value in state["bindings"].values():
                other = self._binding_from_dict(value)
                if not other.active:
                    continue
                if _bindings_share_exclusive_asset(other, current):
                    conflicts.append(other)
            conflict_ids = {conflict.binding_id for conflict in conflicts}
            if len(conflict_ids) > 1:
                raise MetaBindingConflictError("active binding indexes are inconsistent")
            if conflicts and not replace_existing:
                raise MetaBindingConflictError("another active binding owns this asset")
            replacement_id = conflicts[0].binding_id if conflicts else ""
            self._validate_activation_unlocked(
                state,
                current,
                replacing_binding_id=replacement_id if replace_existing else "",
            )
            now = time.time()
            for conflict in conflicts:
                changed = dict(state["bindings"][conflict.binding_id])
                changed["status"] = "inactive"
                changed["updated_at"] = now
                state["bindings"][conflict.binding_id] = changed
            changed_current = dict(raw)
            changed_current["status"] = "active"
            changed_current["generation"] = current.generation + 1
            changed_current["updated_at"] = now
            if replacement_id:
                changed_current["previous_binding_id"] = replacement_id
            state["bindings"][binding_id] = changed_current
            self._write_unlocked(state)
            activated = self._binding_from_dict(changed_current)
            self._append_audit(
                {
                    "event": "binding_cutover_activated" if replacement_id else "binding_activated",
                    "actor_id": actor_id,
                    "tenant_id": activated.tenant_id,
                    "channel": activated.channel,
                    "asset_id": activated.asset_id,
                    "app_key": activated.app_key,
                    "binding_id": activated.binding_id,
                }
            )
            return activated

    def get_active_bindings_for_app(self, app_key: str) -> list[MetaAssetBinding]:
        return [binding for binding in self.list_bindings(include_inactive=False) if binding.app_key == app_key]

    def get_credential(self, binding: MetaAssetBinding) -> MetaBindingCredential:
        with self._locked():
            state = self._read_unlocked()
            record = state["credentials"].get(binding.credential_id)
            if not isinstance(record, dict) or record.get("binding_id") != binding.binding_id:
                raise MetaCredentialError("binding credential is unavailable")
            aad = str(record.get("aad") or "")
            decoded = self._cipher.open(str(record.get("sealed") or ""), aad=aad)
        scopes = decoded.get("scopes")
        if not isinstance(scopes, list):
            raise MetaCredentialError("binding credential scopes are invalid")
        declined = decoded.get("declined_scopes")
        declined_scopes = tuple(str(scope) for scope in declined) if isinstance(declined, list) else ()
        return MetaBindingCredential(
            access_token=str(decoded.get("access_token") or ""),
            token_app_id=str(decoded.get("token_app_id") or ""),
            token_profile_id=str(decoded.get("token_profile_id") or ""),
            scopes=tuple(str(scope) for scope in scopes),
            expires_at=int(decoded["expires_at"]) if decoded.get("expires_at") is not None else None,
            authorized_meta_user_id=str(decoded.get("authorized_meta_user_id") or ""),
            auth_flow=cast(AuthFlow, decoded.get("auth_flow") or binding.auth_flow),
            declined_scopes=declined_scopes,
        )

    def revoke_authorization(
        self,
        *,
        app_key: str,
        authorized_meta_user_id: str,
        actor_id: str = "meta-deauthorization",
    ) -> list[MetaAssetBinding]:
        """Disconnect matching bindings and remove their local encrypted tokens."""

        meta_user_id = str(authorized_meta_user_id or "").strip()
        if not re.fullmatch(r"[0-9]{3,64}", meta_user_id):
            raise MetaCredentialError("authorization identifier is invalid")
        revoked: list[MetaAssetBinding] = []
        with self._locked():
            state = self._read_unlocked()
            now = time.time()
            for binding_id, raw_binding in list(state["bindings"].items()):
                binding = self._binding_from_dict(raw_binding)
                if binding.app_key != app_key:
                    continue
                record = state["credentials"].get(binding.credential_id)
                if not isinstance(record, dict) or record.get("binding_id") != binding.binding_id:
                    continue
                aad = str(record.get("aad") or "")
                decoded = self._cipher.open(str(record.get("sealed") or ""), aad=aad)
                if str(decoded.get("authorized_meta_user_id") or "") != meta_user_id:
                    continue
                changed = dict(raw_binding)
                changed["status"] = "disconnected"
                changed["generation"] = binding.generation + 1
                changed["updated_at"] = now
                state["bindings"][binding_id] = changed
                state["credentials"].pop(binding.credential_id, None)
                revoked.append(self._binding_from_dict(changed))
            self._write_unlocked(state)
            for binding in revoked:
                self._append_audit(
                    {
                        "event": "authorization_revoked",
                        "actor_id": actor_id,
                        "tenant_id": binding.tenant_id,
                        "channel": binding.channel,
                        "asset_id": binding.asset_id,
                        "app_key": binding.app_key,
                        "binding_id": binding.binding_id,
                    }
                )
        return revoked

    def rollback_binding(self, binding_id: str, *, actor_id: str) -> MetaAssetBinding:
        with self._locked():
            state = self._read_unlocked()
            raw = state["bindings"].get(binding_id)
            if not isinstance(raw, dict):
                raise MetaBindingNotFoundError("binding not found")
            current = self._binding_from_dict(raw)
            previous_raw = state["bindings"].get(current.previous_binding_id)
            if not isinstance(previous_raw, dict):
                raise MetaBindingNotFoundError("previous binding is unavailable")
            previous = self._binding_from_dict(previous_raw)
            self._validate_activation_unlocked(
                state,
                previous,
                replacing_binding_id=current.binding_id,
            )
            for value in state["bindings"].values():
                other = self._binding_from_dict(value)
                if not other.active:
                    continue
                if (
                    other.channel == previous.channel
                    and other.asset_id == previous.asset_id
                    and other.binding_id != current.binding_id
                ):
                    changed = dict(state["bindings"][other.binding_id])
                    changed["status"] = "inactive"
                    changed["updated_at"] = time.time()
                    state["bindings"][other.binding_id] = changed
            current_raw = dict(raw)
            current_raw["status"] = "inactive"
            current_raw["generation"] = current.generation + 1
            current_raw["updated_at"] = time.time()
            state["bindings"][binding_id] = current_raw
            previous_raw = dict(previous_raw)
            previous_raw["status"] = "active"
            previous_raw["generation"] = previous.generation + 1
            previous_raw["updated_at"] = time.time()
            state["bindings"][previous.binding_id] = previous_raw
            self._write_unlocked(state)
            restored = self._binding_from_dict(previous_raw)
            self._append_audit(
                {
                    "event": "binding_rollback",
                    "actor_id": actor_id,
                    "tenant_id": restored.tenant_id,
                    "channel": restored.channel,
                    "asset_id": restored.asset_id,
                    "app_key": restored.app_key,
                    "binding_id": restored.binding_id,
                }
            )
            return restored

    def store_oauth_state(self, nonce_hash: str, payload: dict[str, Any]) -> None:
        with self._locked():
            state = self._read_unlocked()
            now = time.time()
            state["oauth_states"] = {
                key: value for key, value in state["oauth_states"].items() if float(value.get("expires_at") or 0) >= now
            }
            state["oauth_states"][nonce_hash] = dict(payload)
            self._write_unlocked(state)

    def update_instagram_login_webhook_subscription(
        self,
        binding_id: str,
        *,
        state: Any,
        actor_id: str,
    ) -> MetaAssetBinding:
        from services.meta_instagram_login_subscription import InstagramLoginSubscriptionState

        if not isinstance(state, InstagramLoginSubscriptionState):
            raise MetaRegistryError("subscription state is invalid")
        with self._locked():
            raw = self._read_unlocked()["bindings"].get(binding_id)
            if not isinstance(raw, dict):
                raise MetaBindingNotFoundError("binding not found")
            binding = self._binding_from_dict(raw)
            if binding.auth_flow != "instagram_login":
                raise MetaBindingConflictError("subscription state applies only to Instagram Login bindings")
            changed = dict(raw)
            changed["webhook_subscription_status"] = state.status
            changed["webhook_subscribed_fields"] = list(state.verified_fields or state.subscribed_fields)
            changed["webhook_subscription_error"] = state.error
            changed["webhook_subscription_checked_at"] = time.time()
            changed["updated_at"] = time.time()
            state_store = self._read_unlocked()
            state_store["bindings"][binding_id] = changed
            self._write_unlocked(state_store)
            updated = self._binding_from_dict(changed)
        self._append_audit(
            {
                "event": "instagram_login_webhook_subscription",
                "actor_id": actor_id,
                "tenant_id": updated.tenant_id,
                "binding_id": updated.binding_id,
                "status": state.status,
                "verified_fields": list(state.verified_fields),
            }
        )
        return updated

    def peek_oauth_state(self, nonce_hash: str) -> dict[str, Any]:
        """Read OAuth state without consuming it (for return_surface on error paths)."""

        with self._locked():
            state = self._read_unlocked()
            raw = state["oauth_states"].get(nonce_hash)
        if not isinstance(raw, dict) or float(raw.get("expires_at") or 0) < time.time():
            raise MetaOAuthStateError("OAuth state is invalid, expired, or already used")
        return cast(dict[str, Any], dict(raw))

    def consume_oauth_state(self, nonce_hash: str) -> dict[str, Any]:
        with self._locked():
            state = self._read_unlocked()
            raw = state["oauth_states"].pop(nonce_hash, None)
            self._write_unlocked(state)
        if not isinstance(raw, dict) or float(raw.get("expires_at") or 0) < time.time():
            raise MetaOAuthStateError("OAuth state is invalid, expired, or already used")
        return cast(dict[str, Any], raw)
