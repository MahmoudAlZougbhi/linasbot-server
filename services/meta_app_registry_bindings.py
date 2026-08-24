"""MetaAppRegistry store/list/authorize helpers (LOC split)."""

from __future__ import annotations

import hashlib
import json
import logging
import os
import tempfile
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager, nullcontext
from pathlib import Path
from typing import Any, cast

from services.meta_app_registry_backend import MetaRegistryBackend, resolve_meta_registry_backend
from services.meta_app_registry_common import (
    REGISTRY_SCHEMA_VERSION,
    AuthFlow,
    BindingStatus,
    MetaAssetBinding,
    MetaChannel,
    MetaCredentialCipher,
    MetaRegistryError,
    binding_asset_key,
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
