"""MetaAppRegistry store/list/authorize helpers (LOC split)."""

from __future__ import annotations

import hashlib
import json
import logging
import os
import tempfile
import threading
import time
import uuid
from collections.abc import Iterator
from contextlib import contextmanager, nullcontext
from dataclasses import asdict
from pathlib import Path
from typing import Any, cast

from services.meta_app_registry_backend import MetaRegistryBackend, resolve_meta_registry_backend
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

logger = logging.getLogger(__name__)

__all__ = ["MetaAppRegistryBindingsMixin", "MetaRegistryBackend", "resolve_meta_registry_backend"]


class MetaAppRegistryBindingsMixin:
    """Persistence, listing, and OAuth authorization for the configurable registry backend."""

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
        self._backend = resolve_meta_registry_backend()
        if self._backend in {"file", "dual"}:
            self.store_path.parent.mkdir(parents=True, exist_ok=True)
            self.audit_path.parent.mkdir(parents=True, exist_ok=True)
        self._thread_lock = threading.RLock()
        self._cipher = MetaCredentialCipher(master_secret or os.getenv("META_CREDENTIAL_ENCRYPTION_KEY") or "")
        self._pg_session: Any = None
        self._lock_depth = 0

    def _empty(self) -> dict[str, Any]:
        return {
            "schema_version": REGISTRY_SCHEMA_VERSION,
            "bindings": {},
            "credentials": {},
            "oauth_states": {},
        }

    def _file_lock_cm(self) -> Any:
        import fcntl

        self.lock_path.touch(mode=0o600, exist_ok=True)
        os.chmod(self.lock_path, 0o600)

        @contextmanager
        def _cm() -> Iterator[None]:
            with self.lock_path.open("r+", encoding="utf-8") as lock_handle:
                fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX)
                try:
                    yield
                finally:
                    fcntl.flock(lock_handle.fileno(), fcntl.LOCK_UN)

        return _cm()

    @contextmanager
    def _locked(self) -> Iterator[None]:
        with self._thread_lock:
            # Depth and the shared Postgres session belong to the owning thread.
            # Check re-entry only after acquiring the RLock so another thread can
            # never inherit an in-flight transaction merely because depth > 0.
            if self._lock_depth > 0:
                self._lock_depth += 1
                try:
                    yield
                finally:
                    self._lock_depth -= 1
                return

            from db.session import WhatsAppDatabaseUnavailable, whatsapp_session
            from services.meta_app_registry_pg_store import (
                acquire_registry_advisory_lock,
                release_registry_advisory_lock,
            )

            needs_pg = self._backend in {"postgres", "dual"}
            needs_file = self._backend in {"file", "dual"}
            file_cm = self._file_lock_cm() if needs_file else nullcontext()
            with file_cm:
                if not needs_pg:
                    self._lock_depth = 1
                    try:
                        yield
                    finally:
                        self._lock_depth = 0
                    return
                try:
                    with whatsapp_session(require=True) as session:
                        acquire_registry_advisory_lock(session)
                        self._pg_session = session
                        self._lock_depth = 1
                        try:
                            yield
                        finally:
                            try:
                                release_registry_advisory_lock(session)
                            finally:
                                self._pg_session = None
                                self._lock_depth = 0
                except WhatsAppDatabaseUnavailable as exc:
                    raise MetaRegistryError("Meta registry Postgres backend is unavailable") from exc

    def _read_file_unlocked(self) -> dict[str, Any]:
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

    def _read_unlocked(self) -> dict[str, Any]:
        from services.meta_app_registry_pg_store import load_state, state_fingerprint

        if self._backend == "file":
            return self._read_file_unlocked()
        if self._pg_session is None:
            raise MetaRegistryError("Meta registry Postgres session is not locked")
        pg_state = load_state(self._pg_session)
        if self._backend == "dual":
            file_state = self._read_file_unlocked()
            if state_fingerprint(pg_state) != state_fingerprint(file_state):
                logger.warning(
                    "meta_registry dual-read mismatch: pg=%s file=%s",
                    state_fingerprint(pg_state),
                    state_fingerprint(file_state),
                )
        return pg_state

    def _write_file_unlocked(self, state: dict[str, Any]) -> None:
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

    def _write_unlocked(self, state: dict[str, Any]) -> None:
        from services.meta_app_registry_pg_store import save_state

        if self._backend == "file":
            self._write_file_unlocked(state)
            return
        if self._pg_session is None:
            raise MetaRegistryError("Meta registry Postgres session is not locked")
        save_state(self._pg_session, state)
        if self._backend == "dual":
            self._write_file_unlocked(state)

    def _redacted_audit(self, event: dict[str, Any]) -> dict[str, Any]:
        actor_id = str(event.get("actor_id") or "system")
        return {
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

    def _append_audit_file(self, safe: dict[str, Any]) -> None:
        with self.audit_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(safe, separators=(",", ":"), sort_keys=True) + "\n")
        os.chmod(self.audit_path, 0o600)

    def _append_audit(self, event: dict[str, Any]) -> None:
        from services.meta_app_registry_pg_store import append_audit_event

        safe = self._redacted_audit(event)
        if self._backend in {"postgres", "dual"}:
            if self._pg_session is None:
                raise MetaRegistryError("Meta registry Postgres session is not locked")
            append_audit_event(self._pg_session, safe)
        if self._backend in {"file", "dual"}:
            self._append_audit_file(safe)

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
            comment_permission_status=str(raw.get("comment_permission_status") or "unknown"),
            comment_permission_verified_at=float(raw.get("comment_permission_verified_at") or 0),
            comment_permission_source=str(raw.get("comment_permission_source") or ""),
            comment_permission_credential_id=str(raw.get("comment_permission_credential_id") or ""),
            comment_permission_token_fingerprint=str(raw.get("comment_permission_token_fingerprint") or ""),
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
                float(comment_permission_verified_at)
                if comment_permission_verified_at is not None
                else now
            )
            changed["comment_permission_source"] = str(comment_permission_source or "")
            changed["comment_permission_credential_id"] = str(comment_permission_credential_id or "")
            changed["comment_permission_token_fingerprint"] = str(comment_permission_token_fingerprint or "")
            changed["updated_at"] = now
            state["bindings"][target] = changed
            self._write_unlocked(state)
            binding = self._binding_from_dict(changed)
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
            "archived_at": 0.0,
        }
        return resolved_id

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
                # Preserve webhook metadata unless the caller supplies a replacement.
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
