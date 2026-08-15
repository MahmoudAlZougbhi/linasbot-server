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
    _binding_duplicate_keeper_rank,
    _bindings_share_exclusive_asset,
    authorized_meta_user_id_hash,
    get_meta_app_configs,
    normalize_meta_tenant_id,
)


class MetaAppRegistryLifecycleMixin:
    """Archive duplicates, validate/activate bindings, and set status."""

    _append_audit: Any
    _binding_from_dict: Any
    _cipher: Any
    _locked: Any
    _read_unlocked: Any
    _write_unlocked: Any

    def archive_superseded_duplicate_bindings(self, *, actor_id: str = "binding-archive") -> int:
        """Converge duplicate rows for file-backend and legacy-state repair.

        A ready direct Instagram binding wins; otherwise the healthy linked row wins.
        """

        archived = 0
        with self._locked():
            state = self._read_unlocked()
            bindings = [self._binding_from_dict(value) for value in state["bindings"].values()]
            groups: dict[str, list[MetaAssetBinding]] = {}
            for binding in bindings:
                groups.setdefault(binding.exclusive_asset_key, []).append(binding)
            now = time.time()
            for group in groups.values():
                active_rows = [item for item in group if item.active]
                active_tenants = {item.tenant_id for item in active_rows}
                if len(active_tenants) > 1:
                    # ``superseded_by_binding_id`` is dashboard history metadata;
                    # it must never hide an active cross-tenant ownership split.
                    raise MetaBindingConflictError("asset is active for multiple workspaces")
                visible = [item for item in group if not item.superseded_by_binding_id]
                hidden_active = any(item.active and item.superseded_by_binding_id for item in group)
                if len(visible) < 2 and len(active_rows) < 2 and not hidden_active:
                    continue

                if active_rows:
                    keeper = max(active_rows, key=_binding_duplicate_keeper_rank)
                    duplicates = [item for item in group if item.tenant_id == keeper.tenant_id]
                    keeper_raw = dict(state["bindings"][keeper.binding_id])
                    if keeper_raw.get("superseded_by_binding_id"):
                        keeper_raw["superseded_by_binding_id"] = ""
                        keeper_raw["generation"] = keeper.generation + 1
                        keeper_raw["updated_at"] = now
                        state["bindings"][keeper.binding_id] = keeper_raw
                        archived += 1
                else:
                    # With no active owner, keep histories isolated by tenant/app/flow.
                    historical_groups: dict[str, list[MetaAssetBinding]] = {}
                    for item in visible:
                        historical_groups.setdefault(item.asset_key, []).append(item)
                    duplicates = []
                    for history in historical_groups.values():
                        history_keeper = max(
                            history,
                            key=lambda item: (item.updated_at, item.created_at, item.binding_id),
                        )
                        for item in history:
                            if item.binding_id != history_keeper.binding_id:
                                raw = dict(state["bindings"][item.binding_id])
                                raw["superseded_by_binding_id"] = history_keeper.binding_id
                                raw["generation"] = item.generation + 1
                                raw["updated_at"] = now
                                state["bindings"][item.binding_id] = raw
                                archived += 1
                    continue

                for duplicate in duplicates:
                    if duplicate.binding_id == keeper.binding_id:
                        continue
                    raw = dict(state["bindings"][duplicate.binding_id])
                    if not duplicate.active and raw.get("superseded_by_binding_id"):
                        continue
                    if duplicate.active:
                        raw["status"] = "inactive"
                    raw["superseded_by_binding_id"] = keeper.binding_id
                    raw["generation"] = duplicate.generation + 1
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
        credential = state["credentials"].get(current.credential_id)
        if (
            not isinstance(credential, dict)
            or credential.get("binding_id") != current.binding_id
            or float(credential.get("archived_at") or 0) > 0
        ):
            raise MetaBindingConflictError("binding credential is unavailable; reconnect required")
        if current.app_key == APP_B_KEY and not app.advanced_access_approved:
            raise MetaBindingConflictError("App B cannot activate before Advanced Access approval")
        if (
            current.app_key == APP_B_KEY
            and current.asset_id in {LINAS_PAGE_ID, LINAS_INSTAGRAM_ACCOUNT_ID}
            and not _app_b_linas_cutover_allowed()
        ):
            raise MetaBindingConflictError("App B cannot activate Lina assets without an approved cutover")
        if replacing_binding_id:
            replacement_raw = state["bindings"].get(replacing_binding_id)
            if not isinstance(replacement_raw, dict):
                raise MetaBindingConflictError("replacement binding is unavailable")
            replacement = self._binding_from_dict(replacement_raw)
            if (
                not replacement.active
                or replacement.tenant_id != current.tenant_id
                or not _bindings_share_exclusive_asset(replacement, current)
            ):
                raise MetaBindingConflictError("replacement binding crosses an ownership boundary")
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
    ) -> Any:
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

    def activate_staged_bindings(
        self,
        binding_ids: tuple[str, ...],
        *,
        actor_id: str,
        expected_generations: dict[str, int] | None = None,
        replace_existing: bool = False,
    ) -> tuple[MetaAssetBinding, ...]:
        """Activate a staged asset set in one registry transaction.

        All rows, generations, conflicts, and activation policies are checked
        before any active owner is changed. This prevents a multi-Page OAuth
        callback from cutting over only the Pages processed before a failure.
        """

        resolved_ids = tuple(str(binding_id or "").strip() for binding_id in binding_ids)
        if not resolved_ids or any(not binding_id for binding_id in resolved_ids):
            raise MetaBindingConflictError("staged binding identifiers are required")
        if len(set(resolved_ids)) != len(resolved_ids):
            raise MetaBindingConflictError("staged binding identifiers must be unique")
        expected = expected_generations or {}
        if expected and set(expected) != set(resolved_ids):
            raise MetaBindingConflictError("staged binding generations are incomplete")

        with self._locked():
            state = self._read_unlocked()
            staged: list[MetaAssetBinding] = []
            for binding_id in resolved_ids:
                raw = state["bindings"].get(binding_id)
                if not isinstance(raw, dict):
                    raise MetaBindingNotFoundError("binding not found")
                current = self._binding_from_dict(raw)
                if current.status not in {"testing", "inactive"}:
                    raise MetaBindingConflictError("binding is not staged for activation")
                if binding_id in expected and current.generation != expected[binding_id]:
                    raise MetaBindingConflictError("binding generation changed")
                staged.append(current)

            for index, current in enumerate(staged):
                if any(_bindings_share_exclusive_asset(current, other) for other in staged[index + 1 :]):
                    raise MetaBindingConflictError("staged bindings contain the same exclusive asset")

            replacements: dict[str, MetaAssetBinding | None] = {}
            for current in staged:
                conflicts = [
                    self._binding_from_dict(value)
                    for value in state["bindings"].values()
                    if self._binding_from_dict(value).active
                    and _bindings_share_exclusive_asset(self._binding_from_dict(value), current)
                ]
                if len({conflict.binding_id for conflict in conflicts}) > 1:
                    raise MetaBindingConflictError("active binding indexes are inconsistent")
                if conflicts and conflicts[0].tenant_id != current.tenant_id:
                    raise MetaBindingConflictError("asset is already active for another workspace")
                if conflicts and not replace_existing:
                    raise MetaBindingConflictError("another active binding owns this asset")
                replacement = conflicts[0] if conflicts else None
                replacements[current.binding_id] = replacement
                self._validate_activation_unlocked(
                    state,
                    current,
                    replacing_binding_id=replacement.binding_id if replacement and replace_existing else "",
                )

            now = time.time()
            for replacement in replacements.values():
                if replacement is None:
                    continue
                changed = dict(state["bindings"][replacement.binding_id])
                changed["status"] = "inactive"
                changed["generation"] = replacement.generation + 1
                changed["updated_at"] = now
                state["bindings"][replacement.binding_id] = changed
            activated: list[MetaAssetBinding] = []
            for current in staged:
                changed = dict(state["bindings"][current.binding_id])
                changed["status"] = "active"
                changed["generation"] = current.generation + 1
                changed["updated_at"] = now
                replacement = replacements[current.binding_id]
                if replacement is not None:
                    changed["previous_binding_id"] = replacement.binding_id
                state["bindings"][current.binding_id] = changed
                for other_id, other_raw in list(state["bindings"].items()):
                    if other_id == current.binding_id:
                        continue
                    other = self._binding_from_dict(other_raw)
                    if (
                        other.tenant_id != current.tenant_id
                        or not _bindings_share_exclusive_asset(other, current)
                        or other.superseded_by_binding_id
                    ):
                        continue
                    superseded = dict(other_raw)
                    superseded["superseded_by_binding_id"] = current.binding_id
                    superseded["generation"] = other.generation + 1
                    superseded["updated_at"] = now
                    state["bindings"][other_id] = superseded
                activated.append(self._binding_from_dict(changed))
            for binding in activated:
                self._append_audit(
                    {
                        "event": "binding_cutover_activated"
                        if replacements[binding.binding_id]
                        else "binding_activated",
                        "actor_id": actor_id,
                        "tenant_id": binding.tenant_id,
                        "channel": binding.channel,
                        "asset_id": binding.asset_id,
                        "app_key": binding.app_key,
                        "binding_id": binding.binding_id,
                    }
                )
            self._write_unlocked(state)
            return tuple(activated)

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
    ) -> Any:
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
            if any(existing.tenant_id != tenant for existing in conflicts):
                raise MetaBindingConflictError("asset is already active for another workspace")
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
                        changed["generation"] = current_binding.generation + 1
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
                        raw["generation"] = existing.generation + 1
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
                authorized_meta_user_id_hash=authorized_meta_user_id_hash(credential.authorized_meta_user_id),
                auth_flow=credential.auth_flow,
            )
            aad = f"{binding_id}:{credential_id}:{tenant}:{channel}:{asset}:{app_key}"
            state["credentials"][credential_id] = {
                "binding_id": binding_id,
                "aad": aad,
                "sealed": self._cipher.seal(credential.as_secret_dict(), aad=aad),
                "created_at": now,
                "archived_at": 0.0,
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
    ) -> Any:
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
