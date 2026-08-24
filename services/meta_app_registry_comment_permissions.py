"""Comment permission verification persistence on Meta asset bindings."""

from __future__ import annotations

import time
from typing import Any, cast

from services.meta_app_registry_common import (
    MetaAssetBinding,
    MetaBindingCredential,
    MetaRegistryError,
)


class MetaAppRegistryCommentPermissionsMixin:
    """Persist token-bound comment permission verification on binding rows."""

    _append_audit: Any
    _binding_from_dict: Any
    _locked: Any
    _read_unlocked: Any
    _write_unlocked: Any

    @staticmethod
    def _comment_permission_fields_for_binding(
        binding: MetaAssetBinding,
        credential: MetaBindingCredential,
        *,
        now: float,
    ) -> dict[str, Any]:
        from services.meta_comment_permission_verification import (
            comment_permission_token_fingerprint,
            verify_comment_permission_from_stored_scopes,
        )

        status, source = verify_comment_permission_from_stored_scopes(binding, credential)
        return {
            "comment_permission_status": status,
            "comment_permission_verified_at": now,
            "comment_permission_source": source,
            "comment_permission_credential_id": binding.credential_id,
            "comment_permission_token_fingerprint": comment_permission_token_fingerprint(credential.access_token),
        }

    def update_comment_permission_verification(
        self,
        binding_id: str,
        *,
        comment_permission_status: str,
        comment_permission_verified_at: float,
        comment_permission_source: str,
        comment_permission_credential_id: str,
        comment_permission_token_fingerprint: str,
        actor_id: str = "system",
    ) -> MetaAssetBinding:
        target = str(binding_id or "").strip()
        if not target:
            raise MetaRegistryError("binding_id is required")
        now = time.time()
        with self._locked():
            state = self._read_unlocked()
            raw = state["bindings"].get(target)
            if not isinstance(raw, dict):
                raise MetaRegistryError("binding was not found")
            changed = dict(raw)
            changed["comment_permission_status"] = str(comment_permission_status or "unknown")
            changed["comment_permission_verified_at"] = (
                float(comment_permission_verified_at) if comment_permission_verified_at is not None else now
            )
            changed["comment_permission_source"] = str(comment_permission_source or "")
            changed["comment_permission_credential_id"] = str(comment_permission_credential_id or "")
            changed["comment_permission_token_fingerprint"] = str(comment_permission_token_fingerprint or "")
            changed["updated_at"] = now
            state["bindings"][target] = changed
            self._write_unlocked(state)
            binding = cast(MetaAssetBinding, self._binding_from_dict(changed))
            self._append_audit(
                {
                    "event": "comment_permission_verified",
                    "actor_id": actor_id,
                    "tenant_id": binding.tenant_id,
                    "channel": binding.channel,
                    "asset_id": binding.asset_id,
                    "app_key": binding.app_key,
                    "binding_id": binding.binding_id,
                    "result": binding.comment_permission_status,
                }
            )
            return binding
