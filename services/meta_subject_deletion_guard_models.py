"""Types and identity helpers for the Meta OAuth/deletion subject boundary."""

from __future__ import annotations

import hashlib
import hmac
import re
from dataclasses import dataclass
from typing import Literal

from services.meta_app_registry_common import AuthFlow

_FIRESTORE_APP_ID = "linas-ai-bot-backend"
_SUBJECT_INDEX_COLLECTION = "meta_deletion_subject_index"
_REQUEST_COLLECTION = "meta_deletion_requests"
_LEASE_COLLECTION = "meta_deletion_subject_leases"
_DEAUTHORIZATION_COLLECTION = "meta_deauthorization_subjects"
_SCHEMA_VERSION = 1
_DEFAULT_LEASE_SECONDS = 300.0
_DEFAULT_DELETION_WAIT_SECONDS = 30.0
_SUBJECT_KEY_RE = re.compile(r"^[0-9a-f]{64}$")
_CONFIRMATION_CODE_RE = re.compile(r"^[0-9a-f]{32}$")
_META_USER_ID_RE = re.compile(r"^[0-9]{3,64}$")
_INDEX_SAFE_FIELDS = frozenset({"schema_version", "confirmation_code", "created_at"})
_REQUEST_SAFE_FIELDS = frozenset(
    {
        "schema_version",
        "confirmation_code",
        "app_key",
        "app_id",
        "auth_flow",
        "bindings",
        "current_bindings",
        "generation",
        "required_nodes",
        "state",
        "coordinator_state",
        "requested_at",
        "updated_at",
        "completed_at",
        "revoked_bindings",
        "shared_redacted_documents",
        "redacted_ledger_documents",
        "safe_error",
    }
)
_LEASE_SAFE_FIELDS = frozenset({"schema_version", "owner_hash", "purpose", "acquired_at", "updated_at", "expires_at"})
_DEAUTHORIZATION_SAFE_FIELDS = frozenset({"schema_version", "generation", "deauthorized_at"})


class MetaSubjectDeletionGuardError(RuntimeError):
    """Base error for the OAuth/deletion subject boundary."""


class MetaSubjectDeletionStoreUnavailableError(MetaSubjectDeletionGuardError):
    """Raised when Firestore cannot enforce the subject boundary."""


class MetaSubjectDeletionLeaseBusyError(MetaSubjectDeletionGuardError):
    """Raised when another live owner holds the subject lease."""


class MetaSubjectDeletionBlockedError(MetaSubjectDeletionGuardError):
    """Raised when OAuth is blocked by pending or failed deletion."""

    def __init__(self, state: str) -> None:
        self.state = str(state or "unavailable").strip().lower()
        super().__init__(f"Meta OAuth is blocked by deletion state: {self.state}")


class MetaSubjectDeletionChangedError(MetaSubjectDeletionGuardError):
    """Raised when deletion state changes during OAuth provider work."""


@dataclass(frozen=True)
class MetaSubjectDeletionSnapshot:
    """Safe request fingerprint captured before OAuth provider mutation."""

    state: Literal["none", "pending", "completed", "no_data", "failed"]
    generation: int
    fingerprint: str
    deauthorization_generation: int = 0
    deauthorized_at: float = 0.0
    deletion_boundary_at: float = 0.0

    @property
    def oauth_allowed(self) -> bool:
        return self.state in {"none", "completed", "no_data"}

    def oauth_allowed_for(self, oauth_started_at: float) -> bool:
        started_at = float(oauth_started_at)
        if not self.oauth_allowed:
            return False
        if self.deauthorization_generation and started_at <= self.deauthorized_at:
            return False
        if self.state in {"completed", "no_data"} and started_at <= self.deletion_boundary_at:
            return False
        return True


def meta_deletion_subject_hmac(
    *,
    app_key: str,
    app_id: str,
    auth_flow: AuthFlow,
    meta_user_id: str,
    app_secret: str,
) -> str:
    """Return the existing secret-keyed subject index without exposing its ID."""

    resolved_app_key = str(app_key or "").strip()
    resolved_app_id = str(app_id or "").strip()
    resolved_user_id = str(meta_user_id or "").strip()
    resolved_secret = str(app_secret or "").strip()
    if (
        not resolved_app_key
        or len(resolved_app_key) > 64
        or not resolved_app_id.isdigit()
        or auth_flow not in {"facebook_login", "instagram_login"}
        or not _META_USER_ID_RE.fullmatch(resolved_user_id)
        or not resolved_secret
    ):
        raise MetaSubjectDeletionGuardError("Meta deletion subject identity is invalid")
    return hmac.new(
        resolved_secret.encode("utf-8"),
        (f"meta-deletion-index:{resolved_app_key}:{resolved_app_id}:{auth_flow}:{resolved_user_id}").encode(),
        hashlib.sha256,
    ).hexdigest()
