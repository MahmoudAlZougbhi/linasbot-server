"""Atomic status cut-off and fair recovery bookkeeping for Meta bindings."""

from __future__ import annotations

import time
from typing import Any, cast

from services.meta_app_registry_common import (
    MetaAssetBinding,
    MetaBindingConflictError,
    MetaBindingNotFoundError,
    MetaChannel,
    normalize_meta_tenant_id,
)


class MetaAppRegistryRecoveryMixin:
    _append_audit: Any
    _binding_from_dict: Any
    _locked: Any
    _read_unlocked: Any
    _write_unlocked: Any

    def disconnect_binding_statuses(
        self,
        binding_ids: tuple[str, ...],
        *,
        tenant_id: str,
        channel: MetaChannel,
        asset_id: str | None,
        actor_id: str,
    ) -> tuple[MetaAssetBinding, ...]:
        """Atomically cut routing for the complete unsettled channel scope."""

        resolved_ids = tuple(str(binding_id or "").strip() for binding_id in binding_ids)
        if not resolved_ids or any(not binding_id for binding_id in resolved_ids):
            raise MetaBindingConflictError("disconnect binding identifiers are required")
        if len(set(resolved_ids)) != len(resolved_ids):
            raise MetaBindingConflictError("disconnect binding identifiers must be unique")
        tenant = normalize_meta_tenant_id(tenant_id)
        asset = None if asset_id is None else str(asset_id or "").strip()
        if channel not in {"facebook", "instagram"} or (asset_id is not None and not asset):
            raise MetaBindingConflictError("disconnect scope is invalid")

        changed_bindings: list[MetaAssetBinding] = []
        with self._locked():
            state = self._read_unlocked()
            scope: list[MetaAssetBinding] = []
            for raw in state["bindings"].values():
                current = self._binding_from_dict(raw)
                if current.tenant_id != tenant or current.channel != channel:
                    continue
                if asset is not None and current.asset_id != asset:
                    continue
                credential = state["credentials"].get(current.credential_id)
                credential_available = False
                if isinstance(credential, dict) and credential.get("binding_id") == current.binding_id:
                    try:
                        credential_available = float(credential.get("archived_at") or 0) <= 0
                    except (TypeError, ValueError):
                        credential_available = True
                if current.status != "disconnected" or credential_available:
                    scope.append(current)
            if {item.binding_id for item in scope} != set(resolved_ids):
                raise MetaBindingConflictError("disconnect scope changed; retry required")

            now = time.time()
            settled: list[MetaAssetBinding] = []
            for current in scope:
                if current.status == "disconnected":
                    settled.append(current)
                    continue
                raw = dict(state["bindings"][current.binding_id])
                raw["status"] = "disconnected"
                raw["generation"] = current.generation + 1
                raw["updated_at"] = now
                state["bindings"][current.binding_id] = raw
                updated = self._binding_from_dict(raw)
                settled.append(updated)
                changed_bindings.append(updated)
            if changed_bindings:
                self._write_unlocked(state)
            for updated in changed_bindings:
                self._append_audit(
                    {
                        "event": "binding_disconnected",
                        "actor_id": actor_id,
                        "tenant_id": updated.tenant_id,
                        "channel": updated.channel,
                        "asset_id": updated.asset_id,
                        "app_key": updated.app_key,
                        "binding_id": updated.binding_id,
                    }
                )
        return tuple(sorted(settled, key=lambda item: resolved_ids.index(item.binding_id)))

    def record_binding_recovery_attempt(
        self,
        binding_id: str,
        *,
        actor_id: str,
        expected_generation: int,
    ) -> MetaAssetBinding:
        """Durably rotate a failed recovery row behind older pending work."""

        with self._locked():
            state = self._read_unlocked()
            raw = state["bindings"].get(binding_id)
            if not isinstance(raw, dict):
                raise MetaBindingNotFoundError("binding not found")
            current = self._binding_from_dict(raw)
            credential = state["credentials"].get(current.credential_id)
            credential_available = (
                isinstance(credential, dict)
                and credential.get("binding_id") == current.binding_id
                and float(credential.get("archived_at") or 0) <= 0
            )
            if current.generation != expected_generation:
                raise MetaBindingConflictError("binding generation changed")
            orphan_pending = (
                current.channel == "instagram"
                and current.auth_flow == "instagram_login"
                and not current.active
                and current.status != "disconnected"
                and current.webhook_subscription_status != "cleanup_pending"
            )
            if not credential_available or (
                current.status != "disconnected"
                and current.webhook_subscription_status != "cleanup_pending"
                and not orphan_pending
            ):
                raise MetaBindingConflictError("binding is no longer pending recovery")
            changed = dict(raw)
            now = time.time()
            changed["webhook_subscription_checked_at"] = now
            changed["updated_at"] = now
            changed["generation"] = current.generation + 1
            state["bindings"][binding_id] = changed
            self._write_unlocked(state)
            updated = self._binding_from_dict(changed)
            self._append_audit(
                {
                    "event": "binding_recovery_attempted",
                    "actor_id": actor_id,
                    "tenant_id": updated.tenant_id,
                    "channel": updated.channel,
                    "asset_id": updated.asset_id,
                    "app_key": updated.app_key,
                    "binding_id": updated.binding_id,
                    "result": "retry",
                }
            )
            return cast(MetaAssetBinding, updated)
