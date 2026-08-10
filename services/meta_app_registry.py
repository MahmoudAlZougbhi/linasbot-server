"""Encrypted registry for Meta apps, tenant assets, OAuth state, and rollback.

The registry intentionally stores application secrets in the process environment and
tenant/Page tokens only as AES-GCM ciphertext. Active bindings are exclusive per
channel/asset_id globally, so two Meta apps can never answer the same Page or
Instagram account at the same time. A workspace may own multiple assets per channel.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import re
import secrets
import tempfile
import threading
import time
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Literal, cast

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from storage.persistent_storage import _DATA_ROOT

APP_A_KEY = "linas_first_party"
APP_B_KEY = "saas_tech_provider"
APP_A_EXPECTED_ID = "2963733803971681"
RETIRED_APP_ID = "1784792718776344"
LINAS_PAGE_ID = "378696005334409"
LINAS_INSTAGRAM_ACCOUNT_ID = "17841413184256533"
REGISTRY_SCHEMA_VERSION = 1

MetaChannel = Literal["facebook", "instagram"]
MetaAppClassification = Literal["own_business", "tech_provider"]
BindingStatus = Literal["active", "inactive", "testing", "disconnected"]
AuthFlow = Literal["facebook_login", "instagram_login"]

META_COMMON_MESSAGING_SCOPES = frozenset(
    {
        "pages_show_list",
        "pages_manage_metadata",
        "pages_read_engagement",
    }
)
META_CHANNEL_SCOPES: dict[MetaChannel, frozenset[str]] = {
    "facebook": META_COMMON_MESSAGING_SCOPES | {"pages_messaging"},
    "instagram": META_COMMON_MESSAGING_SCOPES | {"instagram_basic", "instagram_manage_messages"},
}
META_COMMENT_SCOPES: dict[MetaChannel, frozenset[str]] = {
    "facebook": frozenset({"pages_read_user_content", "pages_manage_engagement"}),
    "instagram": frozenset({"instagram_manage_comments"}),
}
META_PUBLISH_SCOPES: dict[MetaChannel, frozenset[str]] = {
    "facebook": frozenset({"pages_manage_posts"}),
    "instagram": frozenset({"instagram_content_publish"}),
}
META_FORBIDDEN_SCOPES = frozenset(
    {
        "business_management",
        "pages_manage_ads",
        "ads_management",
        "ads_read",
        "catalog_management",
        "commerce_account_manage_orders",
        "whatsapp_business_management",
        "whatsapp_business_messaging",
    }
)


class MetaRegistryError(RuntimeError):
    """Base class for registry failures safe to report by type only."""


class MetaRegistryNotConfiguredError(MetaRegistryError):
    pass


class MetaBindingConflictError(MetaRegistryError):
    pass


class MetaBindingNotFoundError(MetaRegistryError):
    pass


class MetaCredentialError(MetaRegistryError):
    pass


class MetaOAuthStateError(MetaRegistryError):
    pass


def _truthy(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes", "on"}


def meta_multi_app_registry_enabled() -> bool:
    return _truthy(os.getenv("META_MULTI_APP_REGISTRY_ENABLED"))


def _normalized_graph_version(value: str | None) -> str:
    version = (value or "v24.0").strip()
    return version if version.startswith("v") else f"v{version}"


def get_meta_graph_api_version() -> str:
    return _normalized_graph_version(os.getenv("META_GRAPH_API_VERSION"))


def _app_b_linas_cutover_allowed() -> bool:
    return _truthy(os.getenv("META_APP_B_LINAS_CUTOVER_APPROVED"))


def normalize_meta_tenant_id(value: str) -> str:
    """Return the canonical tenant key used in bindings and state namespaces."""

    tenant = str(value or "").strip().lower()
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,63}", tenant):
        raise MetaBindingConflictError("tenant identifier is invalid")
    return tenant


def _bindings_share_exclusive_asset(left: MetaAssetBinding, right: MetaAssetBinding) -> bool:
    if left.tenant_id != right.tenant_id or left.channel != right.channel or left.asset_id != right.asset_id:
        return False
    if left.channel == "instagram":
        return left.auth_flow == right.auth_flow
    return True


def binding_asset_key(
    tenant_id: str,
    app_key: str,
    channel: str,
    asset_id: str,
    auth_flow: AuthFlow = "facebook_login",
) -> str:
    tenant = normalize_meta_tenant_id(tenant_id)
    asset = str(asset_id or "").strip()
    if channel == "instagram":
        return f"{tenant}:{app_key}:{channel}:{auth_flow}:{asset}"
    return f"{tenant}:{app_key}:{channel}:{asset}"


def authorized_meta_user_id_hash(meta_user_id: str) -> str:
    raw = str(meta_user_id or "").strip()
    if not raw:
        return ""
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def mask_asset_id(asset_id: str) -> str:
    raw = str(asset_id or "").strip()
    if len(raw) <= 6:
        return "***"
    return f"{raw[:3]}…{raw[-3:]}"


@dataclass(frozen=True)
class MetaAppConfig:
    key: str
    app_id: str
    app_secret: str
    verify_token: str
    graph_api_version: str
    classification: MetaAppClassification
    oauth_config_id: str = ""
    advanced_access_approved: bool = False
    enabled: bool = False

    def public_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "app_id": self.app_id,
            "classification": self.classification,
            "graph_api_version": self.graph_api_version,
            "oauth_configured": bool(self.oauth_config_id),
            "advanced_access_approved": self.advanced_access_approved,
            "credentials_configured": bool(self.app_secret and self.verify_token),
            "enabled": self.enabled,
        }


def get_meta_app_configs() -> dict[str, MetaAppConfig]:
    """Load the two allowlisted Meta apps without exposing secret values."""

    graph_version = get_meta_graph_api_version()
    app_a_id = (os.getenv("META_APP_A_ID") or os.getenv("META_APP_ID") or "").strip()
    app_a_secret = (os.getenv("META_APP_A_SECRET") or os.getenv("META_APP_SECRET") or "").strip()
    app_a_verify = (
        os.getenv("META_APP_A_WEBHOOK_VERIFY_TOKEN") or os.getenv("META_WEBHOOK_VERIFY_TOKEN") or ""
    ).strip()
    app_a = MetaAppConfig(
        key=APP_A_KEY,
        app_id=app_a_id,
        app_secret=app_a_secret,
        verify_token=app_a_verify,
        graph_api_version=graph_version,
        classification="own_business",
        oauth_config_id=(os.getenv("META_APP_A_LOGIN_CONFIG_ID") or "").strip(),
        advanced_access_approved=_truthy(os.getenv("META_APP_A_ADVANCED_ACCESS_APPROVED")),
        enabled=bool(
            app_a_id and app_a_id == APP_A_EXPECTED_ID and app_a_id != RETIRED_APP_ID and app_a_secret and app_a_verify
        ),
    )

    app_b_id = (os.getenv("META_APP_B_ID") or "").strip()
    app_b_secret = (os.getenv("META_APP_B_SECRET") or "").strip()
    app_b_verify = (os.getenv("META_APP_B_WEBHOOK_VERIFY_TOKEN") or "").strip()
    app_b = MetaAppConfig(
        key=APP_B_KEY,
        app_id=app_b_id,
        app_secret=app_b_secret,
        verify_token=app_b_verify,
        graph_api_version=graph_version,
        classification="tech_provider",
        oauth_config_id=(os.getenv("META_APP_B_LOGIN_CONFIG_ID") or "").strip(),
        advanced_access_approved=_truthy(os.getenv("META_APP_B_ADVANCED_ACCESS_APPROVED")),
        enabled=bool(
            app_b_id
            and app_b_id.isdigit()
            and app_b_id not in {RETIRED_APP_ID, APP_A_EXPECTED_ID}
            and app_b_secret
            and app_b_verify
        ),
    )
    return {APP_A_KEY: app_a, APP_B_KEY: app_b}


def identify_signed_meta_app(raw_body: bytes, signature_header: str | None) -> MetaAppConfig | None:
    """Return the single configured app whose secret authenticates ``raw_body``.

    Every candidate is explicitly allowlisted by registry key.  Ambiguous signatures
    are rejected rather than falling back to an unrestricted secondary secret.
    """

    if not raw_body or not signature_header or not signature_header.startswith("sha256="):
        return None
    received = signature_header[len("sha256=") :].strip().lower()
    matches: list[MetaAppConfig] = []
    for config in get_meta_app_configs().values():
        if not config.enabled:
            continue
        expected = hmac.new(config.app_secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
        if hmac.compare_digest(received, expected):
            matches.append(config)
    return matches[0] if len(matches) == 1 else None


def verify_any_meta_challenge_token(candidate: str | None) -> bool:
    """Constant-time verification against only the two configured app tokens."""

    supplied = candidate or ""
    matched = False
    for config in get_meta_app_configs().values():
        if config.enabled and config.verify_token:
            matched = hmac.compare_digest(supplied, config.verify_token) or matched
    return matched


class MetaCredentialCipher:
    """AES-256-GCM envelope for tenant tokens persisted by the registry."""

    def __init__(self, master_secret: str):
        secret = (master_secret or "").strip()
        if len(secret) < 32:
            raise MetaRegistryNotConfiguredError("META_CREDENTIAL_ENCRYPTION_KEY must be at least 32 characters")
        key = hashlib.sha256(b"linas-meta-registry-v1\x00" + secret.encode("utf-8")).digest()
        self._aead = AESGCM(key)

    def seal(self, payload: dict[str, Any], *, aad: str) -> str:
        nonce = secrets.token_bytes(12)
        plaintext = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
        ciphertext = self._aead.encrypt(nonce, plaintext, aad.encode("utf-8"))
        envelope = base64.urlsafe_b64encode(nonce + ciphertext).decode("ascii").rstrip("=")
        return f"v1.{envelope}"

    def open(self, envelope: str, *, aad: str) -> dict[str, Any]:
        try:
            version, encoded = envelope.split(".", 1)
            if version != "v1":
                raise ValueError("unsupported envelope")
            raw = base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4))
            plaintext = self._aead.decrypt(raw[:12], raw[12:], aad.encode("utf-8"))
            decoded = json.loads(plaintext)
            if not isinstance(decoded, dict):
                raise ValueError("credential payload is not an object")
            return cast(dict[str, Any], decoded)
        except Exception as exc:
            raise MetaCredentialError("stored Meta credential could not be decrypted") from exc


@dataclass(frozen=True)
class MetaAssetBinding:
    binding_id: str
    tenant_id: str
    channel: MetaChannel
    asset_id: str
    page_id: str
    instagram_account_id: str
    app_key: str
    credential_id: str
    status: BindingStatus
    generation: int
    created_at: float
    updated_at: float
    previous_binding_id: str = ""
    page_name: str = ""
    instagram_username: str = ""
    authorized_meta_user_id_hash: str = ""
    superseded_by_binding_id: str = ""
    auth_flow: AuthFlow = "facebook_login"
    webhook_subscription_status: str = "unknown"
    webhook_subscribed_fields: tuple[str, ...] = ()
    webhook_subscription_error: str = ""
    webhook_subscription_checked_at: float = 0.0

    @property
    def active(self) -> bool:
        return self.status == "active"

    @property
    def asset_key(self) -> str:
        return binding_asset_key(
            self.tenant_id,
            self.app_key,
            self.channel,
            self.asset_id,
            self.auth_flow,
        )

    @property
    def instagram_login_ready(self) -> bool:
        if self.auth_flow != "instagram_login":
            return self.active
        from services.meta_instagram_login_subscription import REQUIRED_DM_SUBSCRIPTION_FIELDS

        if self.webhook_subscription_status not in {"ready", "partial"}:
            return False
        return self.active and REQUIRED_DM_SUBSCRIPTION_FIELDS.issubset(self.webhook_subscribed_fields)

    @property
    def visible_in_dashboard(self) -> bool:
        return not self.superseded_by_binding_id

    def public_dict(self) -> dict[str, Any]:
        return {
            "binding_id": self.binding_id,
            "tenant_id": self.tenant_id,
            "channel": self.channel,
            "asset_id": self.asset_id,
            "asset_id_masked": mask_asset_id(self.asset_id),
            "page_id": self.page_id,
            "page_id_masked": mask_asset_id(self.page_id),
            "instagram_account_id": self.instagram_account_id,
            "instagram_account_id_masked": mask_asset_id(self.instagram_account_id),
            "page_name": self.page_name,
            "instagram_username": self.instagram_username,
            "app_key": self.app_key,
            "app_label": "Lina Meta app" if self.app_key == APP_A_KEY else "Legacy provider",
            "status": self.status,
            "generation": self.generation,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "connected_at": self.created_at,
            "previous_binding_id": self.previous_binding_id,
            "authorized_meta_user_id_hash": self.authorized_meta_user_id_hash,
            "superseded_by_binding_id": self.superseded_by_binding_id,
            "auth_flow": self.auth_flow,
            **(
                {
                    "webhook_subscription": {
                        "status": self.webhook_subscription_status,
                        "subscribed_fields": list(self.webhook_subscribed_fields),
                        "error": self.webhook_subscription_error,
                        "checked_at": self.webhook_subscription_checked_at,
                        "ready_for_dm": self.instagram_login_ready,
                        "ready_for_comments": "comments" in self.webhook_subscribed_fields,
                    }
                }
                if self.auth_flow == "instagram_login"
                else {}
            ),
            "asset_key": self.asset_key,
        }


@dataclass(frozen=True)
class MetaBindingCredential:
    access_token: str
    token_app_id: str
    token_profile_id: str
    scopes: tuple[str, ...]
    expires_at: int | None = None
    authorized_meta_user_id: str = ""
    auth_flow: AuthFlow = "facebook_login"
    declined_scopes: tuple[str, ...] = ()

    def as_secret_dict(self) -> dict[str, Any]:
        return {
            "access_token": self.access_token,
            "token_app_id": self.token_app_id,
            "token_profile_id": self.token_profile_id,
            "scopes": list(self.scopes),
            "expires_at": self.expires_at,
            "authorized_meta_user_id": self.authorized_meta_user_id,
            "auth_flow": self.auth_flow,
            "declined_scopes": list(self.declined_scopes),
        }


class MetaAppRegistry:
    """File-backed, process-safe registry with encrypted credential envelopes."""

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

    def consume_oauth_state(self, nonce_hash: str) -> dict[str, Any]:
        with self._locked():
            state = self._read_unlocked()
            raw = state["oauth_states"].pop(nonce_hash, None)
            self._write_unlocked(state)
        if not isinstance(raw, dict) or float(raw.get("expires_at") or 0) < time.time():
            raise MetaOAuthStateError("OAuth state is invalid, expired, or already used")
        return cast(dict[str, Any], raw)


_registry_instance: MetaAppRegistry | None = None


def get_meta_app_registry() -> MetaAppRegistry:
    global _registry_instance
    if _registry_instance is None:
        _registry_instance = MetaAppRegistry()
    return _registry_instance


def reset_meta_app_registry_for_tests() -> None:
    global _registry_instance
    _registry_instance = None


def get_meta_registry_readiness(
    registry: MetaAppRegistry | None = None,
) -> tuple[bool, dict[str, bool]]:
    """Fail-closed readiness for enabling the encrypted multi-app router."""

    checks: dict[str, bool] = {
        "encryption_key_configured": len((os.getenv("META_CREDENTIAL_ENCRYPTION_KEY") or "").strip()) >= 32,
        "app_a_configured": get_meta_app_configs()[APP_A_KEY].enabled,
        "linas_facebook_app_a_active": False,
        "linas_instagram_app_a_active": False,
        "active_indexes_exclusive": True,
        "active_credentials_valid": True,
        "app_b_not_active_on_linas": True,
    }
    try:
        current_registry = registry or get_meta_app_registry()
        bindings = current_registry.list_bindings(include_inactive=False)
        active_asset_keys: set[str] = set()
        now = int(time.time())
        for binding in bindings:
            if binding.asset_key in active_asset_keys:
                checks["active_indexes_exclusive"] = False
            active_asset_keys.add(binding.asset_key)
            if binding.app_key == APP_B_KEY and binding.asset_id in {
                LINAS_PAGE_ID,
                LINAS_INSTAGRAM_ACCOUNT_ID,
            }:
                checks["app_b_not_active_on_linas"] = False
            try:
                credential = current_registry.get_credential(binding)
                app = get_meta_app_configs().get(binding.app_key)
                from services.meta_instagram_login_config import required_scopes_for_binding

                required_scopes = required_scopes_for_binding(
                    channel=binding.channel,
                    auth_flow=binding.auth_flow,
                )
                instagram_login_app_id = (os.getenv("META_INSTAGRAM_LOGIN_APP_ID") or "1035856539045307").strip()
                if (
                    app is None
                    or not app.enabled
                    or (
                        credential.token_app_id != app.app_id
                        and not (
                            binding.auth_flow == "instagram_login" and credential.token_app_id == instagram_login_app_id
                        )
                    )
                    or (binding.auth_flow == "facebook_login" and credential.token_profile_id != binding.page_id)
                    or (binding.auth_flow == "instagram_login" and credential.token_profile_id != binding.asset_id)
                    or not required_scopes.issubset(credential.scopes)
                    or set(credential.scopes) & META_FORBIDDEN_SCOPES
                    or (credential.expires_at is not None and credential.expires_at <= now)
                    or (
                        binding.auth_flow == "instagram_login"
                        and binding.active
                        and binding.webhook_subscription_status != "ready"
                    )
                ):
                    checks["active_credentials_valid"] = False
            except MetaRegistryError:
                checks["active_credentials_valid"] = False
            if (
                binding.app_key == APP_A_KEY
                and binding.tenant_id == "linas"
                and binding.channel == "facebook"
                and binding.asset_id == LINAS_PAGE_ID
            ):
                checks["linas_facebook_app_a_active"] = True
            if (
                binding.app_key == APP_A_KEY
                and binding.tenant_id == "linas"
                and binding.channel == "instagram"
                and binding.asset_id == LINAS_INSTAGRAM_ACCOUNT_ID
            ):
                checks["linas_instagram_app_a_active"] = True
    except MetaRegistryError:
        checks["active_indexes_exclusive"] = False
        checks["active_credentials_valid"] = False
    return all(checks.values()), checks
