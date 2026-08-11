"""MetaAppRegistry activation/status lifecycle (LOC split)."""

from __future__ import annotations

import time
import uuid
from dataclasses import asdict
from typing import Any

from services.meta_app_registry_common import (
    APP_B_KEY,
    LINAS_INSTAGRAM_ACCOUNT_ID,
    LINAS_PAGE_ID,
    META_CHANNEL_SCOPES,
    META_FORBIDDEN_SCOPES,
    BindingStatus,
    MetaAssetBinding,
    MetaBindingConflictError,
    MetaBindingCredential,
    MetaBindingNotFoundError,
    MetaChannel,
    _app_b_linas_cutover_allowed,
    _bindings_share_exclusive_asset,
    get_meta_app_configs,
    normalize_meta_tenant_id,
)


class MetaAppRegistryLifecycleMixin:
    """Archive duplicates, validate/activate bindings, and set status."""

    def archive_superseded_duplicate_bindings(self, *, actor_id: str = "binding-archive") -> int:
        """Mark older duplicate rows superseded when a newer active row exists for the same asset key."""

        archived = 0
        with self._locked():
            state = self._read_unlocked()
            bindings = [self._binding_from_dict(value) for value in state["bindings"].values()]
            groups: dict[str, list[MetaAssetBinding]] = {}
            for binding in bindings:
                groups.setdefault(binding.asset_key, []).append(binding)
            now = time.time()
            for group in groups.values():
                if len(group) < 2:
                    continue
                visible = [item for item in group if not item.superseded_by_binding_id]
                if len(visible) < 2:
                    continue
                active_rows = [item for item in visible if item.active]
                keeper = active_rows[0] if active_rows else max(visible, key=lambda item: item.updated_at)
                for duplicate in visible:
                    if duplicate.binding_id == keeper.binding_id:
                        continue
                    raw = dict(state["bindings"][duplicate.binding_id])
                    if raw.get("superseded_by_binding_id"):
                        continue
                    raw["superseded_by_binding_id"] = keeper.binding_id
                    raw["updated_at"] = now
                    state["bindings"][duplicate.binding_id] = raw
                    archived += 1
            if archived:
                self._write_unlocked(state)
                self._append_audit(
                    {
                        "event": "binding_duplicates_archived",
                        "actor_id": actor_id,
                        "tenant_id": "",
                        "channel": "",
                        "asset_id": "",
                        "app_key": "",
                        "binding_id": "",
                        "result": str(archived),
                    }
                )
        return archived

    def _validate_activation_unlocked(
        self,
        state: dict[str, Any],
        current: MetaAssetBinding,
        *,
        replacing_binding_id: str = "",
    ) -> None:
        app = get_meta_app_configs().get(current.app_key)
        if app is None or not app.enabled:
            raise MetaBindingConflictError("target Meta app is not configured")
        if current.app_key == APP_B_KEY and not app.advanced_access_approved:
            raise MetaBindingConflictError("App B cannot activate before Advanced Access approval")
        if (
            current.app_key == APP_B_KEY
            and current.asset_id in {LINAS_PAGE_ID, LINAS_INSTAGRAM_ACCOUNT_ID}
            and not _app_b_linas_cutover_allowed()
        ):
            raise MetaBindingConflictError("App B cannot activate Lina assets without an approved cutover")
        for value in state["bindings"].values():
            other = self._binding_from_dict(value)
            if other.binding_id in {current.binding_id, replacing_binding_id} or not other.active:
                continue
            if _bindings_share_exclusive_asset(other, current):
                raise MetaBindingConflictError("another active binding owns this asset")

    def assert_binding_can_activate(
        self,
        binding_id: str,
        *,
        expected_generation: int | None = None,
        replacing_binding_id: str = "",
    ) -> MetaAssetBinding:
        """Read-only activation preflight used before any Meta subscription change."""

        with self._locked():
            state = self._read_unlocked()
            raw = state["bindings"].get(binding_id)
            if not isinstance(raw, dict):
                raise MetaBindingNotFoundError("binding not found")
            current = self._binding_from_dict(raw)
            if expected_generation is not None and current.generation != expected_generation:
                raise MetaBindingConflictError("binding generation changed")
            self._validate_activation_unlocked(
                state,
                current,
                replacing_binding_id=replacing_binding_id,
            )
            return current

    def activate_binding(
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
        expected_generation: int | None = None,
        replace_existing: bool = False,
        status: BindingStatus = "active",
    ) -> MetaAssetBinding:
        tenant = normalize_meta_tenant_id(tenant_id)
        asset = asset_id.strip()
        if not tenant or channel not in {"facebook", "instagram"} or not asset:
            raise MetaBindingConflictError("tenant, channel, and asset are required")
        if status not in {"active", "inactive", "testing", "disconnected"}:
            raise MetaBindingConflictError("invalid binding status")
        app = get_meta_app_configs().get(app_key)
        if app is None or not app.enabled:
            raise MetaBindingConflictError("target Meta app is not configured")
        if credential.token_app_id != app.app_id:
            raise MetaBindingConflictError("token app does not match target Meta app")
        if credential.token_profile_id != page_id:
            raise MetaBindingConflictError("token profile does not match the selected Page")
        scopes = set(credential.scopes)
        missing_scopes = META_CHANNEL_SCOPES[channel] - scopes
        if missing_scopes:
            raise MetaBindingConflictError("token is missing required private-messaging permissions")
        if scopes & META_FORBIDDEN_SCOPES:
            raise MetaBindingConflictError("token includes a prohibited non-messaging permission")
        if status == "active" and app_key == APP_B_KEY and not app.advanced_access_approved:
            raise MetaBindingConflictError("App B cannot activate before Advanced Access approval")
        if (
            status == "active"
            and app_key == APP_B_KEY
            and asset in {LINAS_PAGE_ID, LINAS_INSTAGRAM_ACCOUNT_ID}
            and not _app_b_linas_cutover_allowed()
        ):
            raise MetaBindingConflictError("App B cannot activate Lina assets without an approved cutover")

        now = time.time()
        with self._locked():
            state = self._read_unlocked()
            all_bindings = [self._binding_from_dict(value) for value in state["bindings"].values()]
            active_candidates = [
                existing
                for existing in all_bindings
                if existing.active and existing.channel == channel and existing.asset_id == asset
            ]
            if len({candidate.binding_id for candidate in active_candidates}) > 1:
                raise MetaBindingConflictError("active binding indexes are inconsistent")
            conflicts = [existing for existing in active_candidates if status == "active"]
            identical = next(
                (
                    existing
                    for existing in conflicts
                    if existing.tenant_id == tenant
                    and existing.channel == channel
                    and existing.asset_id == asset
                    and existing.app_key == app_key
                ),
                None,
            )
            if identical and expected_generation is not None and identical.generation != expected_generation:
                raise MetaBindingConflictError("binding generation changed")
            if conflicts and not replace_existing and identical is None:
                raise MetaBindingConflictError("an active binding already owns this asset")

            previous_binding_id = (
                identical.binding_id if identical else (active_candidates[0].binding_id if active_candidates else "")
            )
            if status == "active":
                for binding_id, raw_binding in list(state["bindings"].items()):
                    current_binding = self._binding_from_dict(raw_binding)
                    if (
                        current_binding.active
                        and current_binding.channel == channel
                        and current_binding.asset_id == asset
                    ):
                        changed = dict(raw_binding)
                        changed["status"] = "inactive"
                        changed["updated_at"] = now
                        state["bindings"][binding_id] = changed
            if status == "testing":
                for existing in all_bindings:
                    if (
                        existing.status == "testing"
                        and existing.tenant_id == tenant
                        and existing.channel == channel
                        and existing.asset_id == asset
                        and existing.app_key == app_key
                    ):
                        raw = dict(state["bindings"][existing.binding_id])
                        raw["status"] = "inactive"
                        raw["updated_at"] = now
                        state["bindings"][existing.binding_id] = raw

            credential_id = uuid.uuid4().hex
            binding_id = uuid.uuid4().hex
            generation = (identical.generation + 1) if identical else 1
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
                generation=generation,
                created_at=now,
                updated_at=now,
                previous_binding_id=previous_binding_id,
            )
            aad = f"{binding_id}:{credential_id}:{tenant}:{channel}:{asset}:{app_key}"
            state["credentials"][credential_id] = {
                "binding_id": binding_id,
                "aad": aad,
                "sealed": self._cipher.seal(credential.as_secret_dict(), aad=aad),
                "created_at": now,
            }
            state["bindings"][binding_id] = asdict(binding)
            self._write_unlocked(state)
            self._append_audit(
                {
                    "event": "binding_activated" if status == "active" else f"binding_{status}_created",
                    "actor_id": actor_id,
                    "tenant_id": tenant,
                    "channel": channel,
                    "asset_id": asset,
                    "app_key": app_key,
                    "binding_id": binding_id,
                }
            )
        return binding

    def set_binding_status(
        self,
        binding_id: str,
        *,
        status: BindingStatus,
        actor_id: str,
        expected_generation: int | None = None,
    ) -> MetaAssetBinding:
        if status not in {"active", "inactive", "testing", "disconnected"}:
            raise MetaBindingConflictError("invalid binding status")
        with self._locked():
            state = self._read_unlocked()
            raw = state["bindings"].get(binding_id)
            if not isinstance(raw, dict):
                raise MetaBindingNotFoundError("binding not found")
            current = self._binding_from_dict(raw)
            if expected_generation is not None and current.generation != expected_generation:
                raise MetaBindingConflictError("binding generation changed")
            if status == "active":
                self._validate_activation_unlocked(state, current)
            raw = dict(raw)
            raw["status"] = status
            raw["generation"] = current.generation + 1
            raw["updated_at"] = time.time()
            state["bindings"][binding_id] = raw
            self._write_unlocked(state)
            updated = self._binding_from_dict(raw)
            self._append_audit(
                {
                    "event": f"binding_{status}",
                    "actor_id": actor_id,
                    "tenant_id": current.tenant_id,
                    "channel": current.channel,
                    "asset_id": current.asset_id,
                    "app_key": current.app_key,
                    "binding_id": current.binding_id,
                }
            )
            return updated
