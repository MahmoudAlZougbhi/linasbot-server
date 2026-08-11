"""MetaAppRegistry store/list/authorize helpers (LOC split)."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
import threading
import time
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import asdict
from pathlib import Path
from typing import Any, cast

from services.meta_app_registry_common import (
    REGISTRY_SCHEMA_VERSION,
    AuthFlow,
    BindingStatus,
    MetaAssetBinding,
    MetaBindingConflictError,
    MetaBindingCredential,
    MetaChannel,
    MetaCredentialCipher,
    MetaRegistryError,
    authorized_meta_user_id_hash,
    binding_asset_key,
    normalize_meta_tenant_id,
)
from storage.persistent_storage import _DATA_ROOT


class MetaAppRegistryBindingsMixin:
    """File lock, persistence, listing, and OAuth asset authorization."""

    def __init__(
        self,
        *,
        store_path: Path | None = None,
        audit_path: Path | None = None,
        master_secret: str | None = None,
    ) -> None:
        registry_root = Path(_DATA_ROOT) / "meta_registry"
        self.store_path = store_path or registry_root / "registry.json"
        self.audit_path = audit_path or registry_root / "audit.jsonl"
        self.lock_path = self.store_path.with_suffix(".lock")
        self.store_path.parent.mkdir(parents=True, exist_ok=True)
        self.audit_path.parent.mkdir(parents=True, exist_ok=True)
        self._thread_lock = threading.RLock()
        self._cipher = MetaCredentialCipher(master_secret or os.getenv("META_CREDENTIAL_ENCRYPTION_KEY") or "")

    def _empty(self) -> dict[str, Any]:
        return {
            "schema_version": REGISTRY_SCHEMA_VERSION,
            "bindings": {},
            "credentials": {},
            "oauth_states": {},
        }

    @contextmanager
    def _locked(self) -> Iterator[None]:
        import fcntl

        self.lock_path.touch(mode=0o600, exist_ok=True)
        os.chmod(self.lock_path, 0o600)
        with self._thread_lock, self.lock_path.open("r+", encoding="utf-8") as lock_handle:
            fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(lock_handle.fileno(), fcntl.LOCK_UN)

    def _read_unlocked(self) -> dict[str, Any]:
        if not self.store_path.exists():
            return self._empty()
        try:
            raw = json.loads(self.store_path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise MetaRegistryError("Meta registry is unreadable") from exc
        if not isinstance(raw, dict) or raw.get("schema_version") != REGISTRY_SCHEMA_VERSION:
            raise MetaRegistryError("Meta registry schema is invalid")
        for key in ("bindings", "credentials", "oauth_states"):
            if not isinstance(raw.get(key), dict):
                raise MetaRegistryError("Meta registry structure is invalid")
        return cast(dict[str, Any], raw)

    def _write_unlocked(self, state: dict[str, Any]) -> None:
        self.store_path.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary_name = tempfile.mkstemp(prefix=".meta-registry-", dir=self.store_path.parent)
        temporary_path = Path(temporary_name)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(state, handle, separators=(",", ":"), sort_keys=True)
                handle.flush()
                os.fsync(handle.fileno())
            os.chmod(temporary_path, 0o600)
            os.replace(temporary_path, self.store_path)
            os.chmod(self.store_path, 0o600)
        finally:
            if temporary_path.exists():
                temporary_path.unlink()

    def _append_audit(self, event: dict[str, Any]) -> None:
        actor_id = str(event.get("actor_id") or "system")
        safe = {
            "timestamp": time.time(),
            "event": str(event.get("event") or "unknown"),
            "actor_id_hash": hashlib.sha256(actor_id.encode("utf-8")).hexdigest()[:16],
            "tenant_id": str(event.get("tenant_id") or ""),
            "channel": str(event.get("channel") or ""),
            "asset_id_hash": hashlib.sha256(str(event.get("asset_id") or "").encode("utf-8")).hexdigest()[:16],
            "app_key": str(event.get("app_key") or ""),
            "binding_id": str(event.get("binding_id") or ""),
            "result": str(event.get("result") or "ok"),
        }
        with self.audit_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(safe, separators=(",", ":"), sort_keys=True) + "\n")
        os.chmod(self.audit_path, 0o600)

    @staticmethod
    def _binding_from_dict(raw: dict[str, Any]) -> MetaAssetBinding:
        return MetaAssetBinding(
            binding_id=str(raw["binding_id"]),
            tenant_id=str(raw["tenant_id"]),
            channel=cast(MetaChannel, raw["channel"]),
            asset_id=str(raw["asset_id"]),
            page_id=str(raw.get("page_id") or ""),
            instagram_account_id=str(raw.get("instagram_account_id") or ""),
            app_key=str(raw["app_key"]),
            credential_id=str(raw["credential_id"]),
            status=cast(BindingStatus, raw["status"]),
            generation=int(raw.get("generation") or 1),
            created_at=float(raw.get("created_at") or 0),
            updated_at=float(raw.get("updated_at") or 0),
            previous_binding_id=str(raw.get("previous_binding_id") or ""),
            page_name=str(raw.get("page_name") or ""),
            instagram_username=str(raw.get("instagram_username") or ""),
            authorized_meta_user_id_hash=str(raw.get("authorized_meta_user_id_hash") or ""),
            superseded_by_binding_id=str(raw.get("superseded_by_binding_id") or ""),
            auth_flow=cast(AuthFlow, raw.get("auth_flow") or "facebook_login"),
            webhook_subscription_status=str(raw.get("webhook_subscription_status") or "unknown"),
            webhook_subscribed_fields=tuple(str(item) for item in raw.get("webhook_subscribed_fields") or ()),
            webhook_subscription_error=str(raw.get("webhook_subscription_error") or ""),
            webhook_subscription_checked_at=float(raw.get("webhook_subscription_checked_at") or 0),
        )

    def list_bindings(
        self, *, include_inactive: bool = True, include_superseded: bool = True
    ) -> list[MetaAssetBinding]:
        with self._locked():
            state = self._read_unlocked()
        bindings = [self._binding_from_dict(value) for value in state["bindings"].values()]
        if not include_superseded:
            bindings = [binding for binding in bindings if binding.visible_in_dashboard]
        if not include_inactive:
            bindings = [binding for binding in bindings if binding.active]
        return sorted(bindings, key=lambda item: (item.tenant_id, item.channel, item.asset_id, item.created_at))

    def find_bindings_for_asset_key(
        self,
        *,
        tenant_id: str,
        app_key: str,
        channel: MetaChannel,
        asset_id: str,
        include_superseded: bool = True,
    ) -> list[MetaAssetBinding]:
        key = binding_asset_key(tenant_id, app_key, channel, asset_id)
        matches = [
            binding for binding in self.list_bindings(include_superseded=include_superseded) if binding.asset_key == key
        ]
        return sorted(matches, key=lambda item: item.updated_at, reverse=True)

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
    ) -> MetaAssetBinding:
        """Upsert one workspace asset binding without disconnecting unrelated assets."""

        tenant = normalize_meta_tenant_id(tenant_id)
        asset = asset_id.strip()
        if not asset:
            raise MetaBindingConflictError("asset is required")
        auth_hash = authorized_meta_user_id_hash(credential.authorized_meta_user_id)
        resolved_auth_flow = auth_flow or credential.auth_flow or "facebook_login"
        now = time.time()
        with self._locked():
            state = self._read_unlocked()
            all_bindings = [self._binding_from_dict(value) for value in state["bindings"].values()]
            for other in all_bindings:
                if (
                    other.active
                    and other.channel == channel
                    and other.asset_id == asset
                    and (other.tenant_id != tenant or other.app_key != app_key)
                ):
                    raise MetaBindingConflictError("asset is already active for another workspace")

            same_key = [
                binding
                for binding in all_bindings
                if binding.asset_key == binding_asset_key(tenant, app_key, channel, asset, resolved_auth_flow)
                and not binding.superseded_by_binding_id
            ]
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

            if canonical is not None:
                binding_id = canonical.binding_id
                generation = canonical.generation + 1
                created_at = canonical.created_at
                # Safe reauth: preserve existing webhook subscription metadata unless caller
                # explicitly supplies a new non-empty field set (avoid wiping feed/comments).
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
                )
                state["bindings"][binding_id] = asdict(updated)
                for duplicate in same_key:
                    if duplicate.binding_id == binding_id:
                        continue
                    raw = dict(state["bindings"][duplicate.binding_id])
                    raw["superseded_by_binding_id"] = binding_id
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
