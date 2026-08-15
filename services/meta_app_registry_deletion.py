"""Exact, generation-bound Meta registry revocation for data deletion."""

from __future__ import annotations

import re
import time
from typing import Any, cast

from services.meta_app_registry_common import (
    AuthFlow,
    MetaAssetBinding,
    MetaBindingConflictError,
    MetaBindingCredential,
    MetaCredentialError,
    authorized_meta_user_id_hash,
)


class MetaAppRegistryDeletionMixin:
    """All-or-nothing revocation used by the HA deletion coordinator."""

    _append_audit: Any
    _binding_from_dict: Any
    _cipher: Any
    _locked: Any
    _read_unlocked: Any
    _write_credential_unlocked: Any
    _write_unlocked: Any

    def refresh_binding_credential_exact(
        self,
        *,
        binding_id: str,
        expected_generation: int,
        credential: MetaBindingCredential,
        actor_id: str = "meta-token-refresh",
    ) -> MetaAssetBinding:
        """Replace one active credential with a generation-bound CAS.

        A disconnected binding with its credential removed is the durable
        deletion tombstone.  Refresh never routes through generic OAuth
        authorization, so an in-flight provider call cannot recreate that
        credential after exact revocation.
        """

        target_id = str(binding_id or "").strip()
        if not target_id or expected_generation < 1:
            raise MetaBindingConflictError("binding refresh scope is invalid")
        now = time.time()
        with self._locked():
            state = self._read_unlocked()
            raw = state["bindings"].get(target_id)
            if not isinstance(raw, dict):
                raise MetaBindingConflictError("binding changed during credential refresh")
            binding = self._binding_from_dict(raw)
            stored_credential = state["credentials"].get(binding.credential_id)
            if (
                binding.generation != expected_generation
                or binding.status != "active"
                or binding.superseded_by_binding_id
                or not isinstance(stored_credential, dict)
                or stored_credential.get("binding_id") != target_id
                or float(stored_credential.get("archived_at") or 0) > 0
                or credential.auth_flow != binding.auth_flow
                or authorized_meta_user_id_hash(credential.authorized_meta_user_id)
                != binding.authorized_meta_user_id_hash
            ):
                raise MetaBindingConflictError("binding changed during credential refresh")
            stored_secret = self._cipher.open(
                str(stored_credential.get("sealed") or ""),
                aad=str(stored_credential.get("aad") or ""),
            )
            if (
                credential.token_app_id != str(stored_secret.get("token_app_id") or "")
                or credential.token_profile_id != str(stored_secret.get("token_profile_id") or "")
                or tuple(credential.scopes) != tuple(str(item) for item in stored_secret.get("scopes") or ())
                or credential.auth_flow != str(stored_secret.get("auth_flow") or binding.auth_flow)
            ):
                raise MetaBindingConflictError("credential refresh scope changed")
            credential_id = self._write_credential_unlocked(
                state,
                binding_id=target_id,
                credential_id=binding.credential_id,
                tenant=binding.tenant_id,
                channel=binding.channel,
                asset=binding.asset_id,
                app_key=binding.app_key,
                credential=credential,
                now=now,
            )
            changed = dict(raw)
            changed.update(
                {
                    "credential_id": credential_id,
                    "generation": binding.generation + 1,
                    "updated_at": now,
                }
            )
            state["bindings"][target_id] = changed
            self._write_unlocked(state)
            updated = cast(MetaAssetBinding, self._binding_from_dict(changed))
            self._append_audit(
                {
                    "event": "binding_credential_refreshed",
                    "actor_id": actor_id,
                    "tenant_id": updated.tenant_id,
                    "channel": updated.channel,
                    "asset_id": updated.asset_id,
                    "app_key": updated.app_key,
                    "binding_id": updated.binding_id,
                }
            )
            return updated

    def revoke_authorization_exact(
        self,
        *,
        app_key: str,
        auth_flow: AuthFlow,
        authorized_meta_user_id: str,
        expected_bindings: dict[str, int],
        actor_id: str = "meta-data-deletion",
    ) -> list[MetaAssetBinding]:
        """Revoke exactly one deletion request's binding generations atomically.

        A retry after a committed revocation accepts the same rows at generation
        ``expected + 1`` only when their credential is already gone.
        """

        meta_user_id = str(authorized_meta_user_id or "").strip()
        if not re.fullmatch(r"[0-9]{3,64}", meta_user_id):
            raise MetaCredentialError("authorization identifier is invalid")
        if auth_flow not in {"facebook_login", "instagram_login"}:
            raise MetaCredentialError("authorization flow is invalid")
        expected = {
            str(binding_id).strip(): int(generation)
            for binding_id, generation in expected_bindings.items()
            if str(binding_id).strip()
        }
        if len(expected) != len(expected_bindings) or any(generation < 1 for generation in expected.values()):
            raise MetaBindingConflictError("deletion binding generations are invalid")

        owner_hash = authorized_meta_user_id_hash(meta_user_id)
        revoked: list[MetaAssetBinding] = []
        with self._locked():
            state = self._read_unlocked()
            candidates: dict[str, tuple[MetaAssetBinding, dict[str, Any] | None]] = {}
            for raw_binding in state["bindings"].values():
                binding = self._binding_from_dict(raw_binding)
                if binding.app_key != app_key or binding.auth_flow != auth_flow:
                    continue
                raw_credential = state["credentials"].get(binding.credential_id)
                credential = raw_credential if isinstance(raw_credential, dict) else None
                matches_subject = False
                if credential is not None and credential.get("binding_id") == binding.binding_id:
                    aad = str(credential.get("aad") or "")
                    decoded = self._cipher.open(str(credential.get("sealed") or ""), aad=aad)
                    matches_subject = str(decoded.get("authorized_meta_user_id") or "") == meta_user_id
                elif credential is None:
                    matches_subject = binding.authorized_meta_user_id_hash == owner_hash
                if matches_subject:
                    candidates[binding.binding_id] = (binding, credential)

            if set(candidates) != set(expected):
                raise MetaBindingConflictError("authorization scope changed during data deletion")
            for binding_id, (binding, credential) in candidates.items():
                expected_generation = expected[binding_id]
                already_revoked = binding.status == "disconnected" and credential is None
                allowed_generations = (
                    {expected_generation, expected_generation + 1} if already_revoked else {expected_generation}
                )
                if binding.generation not in allowed_generations:
                    raise MetaBindingConflictError("binding generation changed during data deletion")

            now = time.time()
            for binding_id, (binding, credential) in candidates.items():
                if binding.status == "disconnected" and credential is None:
                    continue
                changed = dict(state["bindings"][binding_id])
                changed["status"] = "disconnected"
                changed["generation"] = binding.generation + 1
                changed["updated_at"] = now
                state["bindings"][binding_id] = changed
                state["credentials"].pop(binding.credential_id, None)
                revoked.append(self._binding_from_dict(changed))
            if revoked:
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
                            "auth_flow": binding.auth_flow,
                        }
                    )
        return revoked
