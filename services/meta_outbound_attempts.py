"""Shared at-most-once safety boundary for Meta provider sends.

The provider call cannot be made atomically with Firestore.  We therefore favor
duplicate prevention over automatic retry when the result is ambiguous:

* persist ``sending`` before the provider call;
* persist ``accepted`` only after a response with a provider message id;
* permit retry only after a definitive provider rejection;
* treat a crash/timeout or lost post-send acknowledgement as owner action.

No provider/customer identifiers or user/provider message contents are stored.
For image-quota notices only, schema v2 retains one bounded, validated copy of
the system-generated notice so a crash replay never has to recalculate quota or
change customer-facing copy.  The inbound event id is already a SHA-derived
correlation id and provider ids are hashed.
"""

from __future__ import annotations

import asyncio
import hashlib
import re
import secrets
import time
import unicodedata
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any, Literal

from services.firestore_transaction_compat import run_firestore_transaction
from services.meta_controlled_evidence import MetaEvidenceSurface
from services.meta_outbound_purposes import ALLOWED_PURPOSES as _ALLOWED_PURPOSES
from services.meta_outbound_purposes import PURPOSE_PREDECESSORS as _PURPOSE_PREDECESSORS
from services.meta_outbound_purposes import MetaOutboundPurpose

_EVENT_ID_RE = re.compile(r"ibe_[0-9a-f]{40}")
_ALLOWED_SURFACES = frozenset({"facebook_dm", "instagram_dm", "facebook_comment", "instagram_comment"})
_COLLECTION = "meta_outbound_attempts"
_APP_DOCUMENT = "linas-ai-bot-backend"
_MAX_TRANSACTION_ATTEMPTS = 5
_PURPOSE_DOCUMENT_DOMAIN = "meta-outbound-purpose-v1"
_IMAGE_QUOTA_NOTICE_DOMAIN = "meta-image-quota-notice-v1"
_MAX_IMAGE_QUOTA_NOTICE_BYTES = 1_000
_SHA256_RE = re.compile(r"[0-9a-f]{64}")

AttemptDecisionKind = Literal[
    "send",
    "quota_reserved",
    "duplicate_suppressed",
    "needs_owner_action",
    "nonproduction_bypass",
]
ImageQuotaDisposition = Literal["allowed", "blocked", "truncated"]
ImageQuotaPhase = Literal["reserved", "consumed", "provider"]
MetaOutboundAttemptStatus = Literal[
    "sending",
    "accepted",
    "definitive_failure",
    "needs_owner_action",
]
_ALLOWED_QUOTA_DISPOSITIONS = frozenset({"allowed", "blocked", "truncated"})
_ALLOWED_QUOTA_PHASES = frozenset({"reserved", "consumed", "provider"})
_ALLOWED_STATUSES = frozenset({"sending", "accepted", "definitive_failure", "needs_owner_action"})
_SEND_PURPOSE: ContextVar[MetaOutboundPurpose] = ContextVar(
    "meta_outbound_send_purpose",
    default="primary_reply",
)


class MetaOutboundAttemptStoreError(RuntimeError):
    """The shared at-most-once store could not be trusted."""


@dataclass(frozen=True)
class MetaOutboundAttemptDecision:
    kind: AttemptDecisionKind
    event_id: str
    surface: MetaEvidenceSurface
    purpose: MetaOutboundPurpose = "primary_reply"
    image_quota_disposition: str = ""
    image_quota_allowed_amount: int = 0
    image_quota_phase: str = ""
    image_quota_notice_text: str = field(default="", repr=False)
    image_quota_notice_sha256: str = ""
    attempt_token: str = ""
    attempt_sequence: int = 0
    binding_id: str = field(default="", repr=False)


@dataclass(frozen=True)
class MetaOutboundAttemptReceipt:
    event_id: str
    surface: MetaEvidenceSurface
    purpose: MetaOutboundPurpose
    status: MetaOutboundAttemptStatus
    image_quota_disposition: str = ""
    image_quota_allowed_amount: int = 0
    image_quota_phase: str = ""
    image_quota_notice_text: str = field(default="", repr=False)
    image_quota_notice_sha256: str = ""
    attempt_sequence: int = 0


def current_meta_outbound_send_purpose() -> MetaOutboundPurpose:
    return _SEND_PURPOSE.get()


@contextmanager
def meta_outbound_send_purpose(purpose: MetaOutboundPurpose | str) -> Iterator[None]:
    """Set one task-local semantic send role without changing SendFunc APIs."""

    safe_purpose = _validate_purpose(purpose)
    if safe_purpose == "image_quota_notice":
        raise ValueError("Image-quota notice purpose is reserved for its guarded path")
    token = _SEND_PURPOSE.set(safe_purpose)
    try:
        yield
    finally:
        _SEND_PURPOSE.reset(token)


def _validate_event_id(event_id: str) -> str:
    value = str(event_id or "").strip().lower()
    if _EVENT_ID_RE.fullmatch(value) is None:
        raise ValueError("Meta outbound event identity is invalid")
    return value


def _validate_surface(surface: MetaEvidenceSurface | str | None) -> MetaEvidenceSurface:
    value = str(surface or "").strip().lower()
    if value not in _ALLOWED_SURFACES:
        raise ValueError("Meta outbound surface is invalid")
    return value  # type: ignore[return-value]


def _validate_purpose(purpose: MetaOutboundPurpose | str) -> MetaOutboundPurpose:
    value = str(purpose or "").strip().lower()
    if value not in _ALLOWED_PURPOSES:
        raise ValueError("Meta outbound purpose is invalid")
    return value  # type: ignore[return-value]


def _validate_quota_context(
    purpose: MetaOutboundPurpose,
    disposition: ImageQuotaDisposition | str,
    allowed_amount: int,
    phase: ImageQuotaPhase | str | None = None,
    notice_text: str = "",
    notice_sha256: str | None = None,
) -> tuple[str, int, str, str, str]:
    value = str(disposition or "").strip().lower()
    safe_phase = "" if phase is None else str(phase or "").strip().lower()
    if type(notice_text) is not str or (notice_sha256 is not None and type(notice_sha256) is not str):
        raise ValueError("Meta outbound image-quota notice authority is invalid")
    safe_notice_sha256 = "" if notice_sha256 is None else notice_sha256
    if type(allowed_amount) is not int or not 0 <= allowed_amount <= 100_000:
        raise ValueError("Meta outbound image-quota amount is invalid")
    if purpose != "image_quota_notice":
        if value or allowed_amount or safe_phase or notice_text or safe_notice_sha256:
            raise ValueError("Non-quota outbound purpose cannot carry image-quota context")
    else:
        if (
            value not in _ALLOWED_QUOTA_DISPOSITIONS
            or (value == "blocked" and allowed_amount)
            or (value in {"allowed", "truncated"} and allowed_amount <= 0)
        ):
            raise ValueError("Meta outbound image-quota disposition is invalid")
        if phase is not None and safe_phase not in _ALLOWED_QUOTA_PHASES:
            raise ValueError("Meta outbound image-quota phase is invalid")
    carries_notice = purpose == "image_quota_notice" and value in {"blocked", "truncated"}
    if not carries_notice:
        if notice_text or safe_notice_sha256:
            raise ValueError("Meta outbound image-quota notice authority is invalid")
        return value, allowed_amount, safe_phase, "", ""
    try:
        notice_bytes = notice_text.encode("utf-8", errors="strict")
    except UnicodeEncodeError as exc:
        raise ValueError("Meta outbound image-quota notice text is invalid") from exc
    if (
        not notice_text.strip()
        or len(notice_bytes) > _MAX_IMAGE_QUOTA_NOTICE_BYTES
        or any(unicodedata.category(character).startswith("C") for character in notice_text)
    ):
        raise ValueError("Meta outbound image-quota notice text is invalid")
    expected_sha256 = hashlib.sha256(
        f"{_IMAGE_QUOTA_NOTICE_DOMAIN}\0{value}\0{allowed_amount}\0".encode() + notice_bytes
    ).hexdigest()
    if notice_sha256 is not None and notice_sha256 != expected_sha256:
        raise ValueError("Meta outbound image-quota notice authority is invalid")
    return value, allowed_amount, safe_phase, notice_text, expected_sha256


def _owner_hash(token: str) -> str:
    return hashlib.sha256(f"meta-outbound-owner\0{token}".encode()).hexdigest()


def _provider_id_hash(provider_message_id: str) -> str:
    return hashlib.sha256(f"meta-provider-message\0{provider_message_id}".encode()).hexdigest()


def _attempt_document_id(event_id: str, purpose: MetaOutboundPurpose | str) -> str:
    safe_event_id = _validate_event_id(event_id)
    safe_purpose = _validate_purpose(purpose)
    if safe_purpose == "primary_reply":
        return safe_event_id
    digest = hashlib.sha256(f"{_PURPOSE_DOCUMENT_DOMAIN}\0{safe_event_id}\0{safe_purpose}".encode()).hexdigest()
    return f"moa_{digest}"


def _ref(db: Any, event_id: str, purpose: MetaOutboundPurpose | str) -> Any:
    document_id = _attempt_document_id(event_id, purpose)
    return db.collection("artifacts").document(_APP_DOCUMENT).collection(_COLLECTION).document(document_id)


def _validate_stored_identity(
    current: dict[str, Any], *, event_id: str, purpose: MetaOutboundPurpose
) -> tuple[str, int, str, str, str]:
    schema_version = current.get("schema_version")
    if type(schema_version) is not int:
        raise MetaOutboundAttemptStoreError("Meta outbound-attempt schema changed")
    if schema_version == 1:
        quota_keys = {
            "purpose",
            "image_quota_disposition",
            "image_quota_allowed_amount",
            "image_quota_phase",
            "image_quota_notice_text",
            "image_quota_notice_sha256",
        }
        if purpose != "primary_reply" or quota_keys.intersection(current):
            raise MetaOutboundAttemptStoreError("Meta outbound-attempt purpose changed")
        quota_context = ("", 0, "", "", "")
    elif schema_version == 2:
        if current.get("purpose") != purpose:
            raise MetaOutboundAttemptStoreError("Meta outbound-attempt purpose changed")
        required = {
            "image_quota_disposition",
            "image_quota_allowed_amount",
            "image_quota_phase",
        }
        if not required.issubset(current):
            raise MetaOutboundAttemptStoreError("Meta outbound-attempt quota context changed")
        disposition = current["image_quota_disposition"]
        notice_required = purpose == "image_quota_notice" and disposition in {"blocked", "truncated"}
        notice_keys = {"image_quota_notice_text", "image_quota_notice_sha256"}
        if notice_required and not notice_keys.issubset(current):
            raise MetaOutboundAttemptStoreError("Meta outbound-attempt quota notice changed")
        stored_notice_text = current.get("image_quota_notice_text", "")
        stored_notice_sha256 = current.get("image_quota_notice_sha256", "")
        if type(stored_notice_text) is not str or type(stored_notice_sha256) is not str:
            raise MetaOutboundAttemptStoreError("Meta outbound-attempt quota notice changed")
        if notice_required and _SHA256_RE.fullmatch(stored_notice_sha256) is None:
            raise MetaOutboundAttemptStoreError("Meta outbound-attempt quota notice changed")
        try:
            quota_context = _validate_quota_context(
                purpose,
                disposition,
                current["image_quota_allowed_amount"],
                current["image_quota_phase"],
                stored_notice_text,
                stored_notice_sha256,
            )
        except ValueError as exc:
            raise MetaOutboundAttemptStoreError("Meta outbound-attempt quota context changed") from exc
    else:
        raise MetaOutboundAttemptStoreError("Meta outbound-attempt schema changed")
    if current.get("event_id") != event_id:
        raise MetaOutboundAttemptStoreError("Meta outbound-attempt event identity changed")
    return quota_context


def _db_or_bypass() -> Any | None:
    resolution_error: BaseException | None
    try:
        from utils.utils import get_firestore_db

        db = get_firestore_db()
    except Exception as exc:
        db = None
        resolution_error = exc
    else:
        resolution_error = None
    if db is not None:
        return db
    from config import is_production_runtime

    if is_production_runtime():
        raise MetaOutboundAttemptStoreError("Shared Meta outbound-attempt store is unavailable") from resolution_error
    return None


def _binding_authority(db: Any, binding_id: str) -> tuple[Any | None, str]:
    if not binding_id:
        return None, ""
    from services.meta_inbound_deletion_fence import firestore_binding_deletion_fence_ref

    fence_reference = firestore_binding_deletion_fence_ref(db, binding_id)
    from services.durable_event_claim import meta_claim_binding_digest

    return fence_reference, meta_claim_binding_digest(binding_id)


def _validate_stored_authority(
    current: dict[str, Any],
    *,
    event_id: str,
    surface: MetaEvidenceSurface,
    purpose: MetaOutboundPurpose,
    binding_digest: str,
) -> tuple[MetaOutboundAttemptStatus, tuple[str, int, str, str, str], int]:
    context = _validate_stored_identity(current, event_id=event_id, purpose=purpose)
    status = str(current.get("status") or "")
    if status not in _ALLOWED_STATUSES:
        raise MetaOutboundAttemptStoreError("Meta outbound-attempt state is invalid")
    if current.get("surface") != surface:
        raise MetaOutboundAttemptStoreError("Meta outbound-attempt surface changed")
    stored_binding = current.get("binding_id_sha256")
    if current.get("schema_version") == 1 and stored_binding is None:
        stored_binding = ""
    if not isinstance(stored_binding, str):
        raise MetaOutboundAttemptStoreError("Meta outbound-attempt binding changed")
    if current.get("schema_version") == 2 and stored_binding != binding_digest:
        raise MetaOutboundAttemptStoreError("Meta outbound-attempt binding changed")
    if stored_binding and stored_binding != binding_digest:
        raise MetaOutboundAttemptStoreError("Meta outbound-attempt binding changed")
    sequence = current.get("attempt_sequence")
    if type(sequence) is not int or sequence < 0:
        raise MetaOutboundAttemptStoreError("Meta outbound-attempt sequence changed")
    if current.get("schema_version") == 2:
        owner_hash = current.get("owner_hash")
        if not isinstance(owner_hash, str):
            raise MetaOutboundAttemptStoreError("Meta outbound-attempt ownership changed")
        phase = context[2]
        if purpose == "image_quota_notice":
            disposition = context[0]
            if disposition == "allowed" and (
                (status == "accepted" and phase != "consumed") or status == "definitive_failure" or phase == "provider"
            ):
                raise MetaOutboundAttemptStoreError("Meta outbound-attempt quota phase changed")
            if disposition != "allowed" and status in {"accepted", "definitive_failure"} and phase != "provider":
                raise MetaOutboundAttemptStoreError("Meta outbound-attempt quota phase changed")
            if status == "sending" and phase == "reserved" and _SHA256_RE.fullmatch(owner_hash) is None:
                raise MetaOutboundAttemptStoreError("Meta outbound-attempt ownership changed")
            if status == "sending" and phase == "consumed" and owner_hash:
                raise MetaOutboundAttemptStoreError("Meta outbound-attempt ownership changed")
            if status == "sending" and phase == "provider" and _SHA256_RE.fullmatch(owner_hash) is None:
                raise MetaOutboundAttemptStoreError("Meta outbound-attempt ownership changed")
        elif status == "sending" and _SHA256_RE.fullmatch(owner_hash) is None:
            raise MetaOutboundAttemptStoreError("Meta outbound-attempt ownership changed")
        if status != "sending" and owner_hash:
            raise MetaOutboundAttemptStoreError("Meta outbound-attempt ownership changed")
    return status, context, sequence  # type: ignore[return-value]


def _read_receipt_sync(
    db: Any,
    *,
    event_id: str,
    surface: MetaEvidenceSurface,
    binding_id: str,
    purpose: MetaOutboundPurpose,
) -> MetaOutboundAttemptReceipt | None:
    snapshot = _ref(db, event_id, purpose).get()
    if not snapshot.exists:
        return None
    current = snapshot.to_dict()
    if not isinstance(current, dict):
        raise MetaOutboundAttemptStoreError("Meta outbound-attempt document is invalid")
    _, binding_digest = _binding_authority(db, binding_id)
    status, context, sequence = _validate_stored_authority(
        current,
        event_id=event_id,
        surface=surface,
        purpose=purpose,
        binding_digest=binding_digest,
    )
    return MetaOutboundAttemptReceipt(
        event_id=event_id,
        surface=surface,
        purpose=purpose,
        status=status,
        image_quota_disposition=context[0],
        image_quota_allowed_amount=context[1],
        image_quota_phase=context[2],
        image_quota_notice_text=context[3],
        image_quota_notice_sha256=context[4],
        attempt_sequence=sequence,
    )


async def read_meta_outbound_attempt_receipt(
    *,
    event_id: str,
    surface: MetaEvidenceSurface | str | None,
    binding_id: str = "",
    purpose: MetaOutboundPurpose | str = "primary_reply",
) -> MetaOutboundAttemptReceipt | None:
    """Read one exact receipt without changing provider or quota authority."""

    safe_event_id = _validate_event_id(event_id)
    safe_surface = _validate_surface(surface)
    safe_purpose = _validate_purpose(purpose)
    safe_binding_id = str(binding_id or "").strip()
    db = _db_or_bypass()
    if db is None:
        return None
    return await asyncio.to_thread(
        _read_receipt_sync,
        db,
        event_id=safe_event_id,
        surface=safe_surface,
        binding_id=safe_binding_id,
        purpose=safe_purpose,
    )


def _reconcile_image_quota_receipt_sync(
    db: Any,
    *,
    event_id: str,
    surface: MetaEvidenceSurface,
    binding_id: str,
) -> MetaOutboundAttemptReceipt | None:
    purpose: MetaOutboundPurpose = "image_quota_notice"
    reference = _ref(db, event_id, purpose)
    fence_reference, binding_digest = _binding_authority(db, binding_id)
    last_error: Exception | None = None
    for _attempt in range(_MAX_TRANSACTION_ATTEMPTS):
        try:

            def _reconcile(transaction: Any) -> MetaOutboundAttemptReceipt | None:
                fenced = bool(fence_reference is not None and fence_reference.get(transaction=transaction).exists)
                snapshot = reference.get(transaction=transaction)
                if not snapshot.exists:
                    return None
                current = snapshot.to_dict()
                if not isinstance(current, dict):
                    raise MetaOutboundAttemptStoreError("Meta outbound-attempt document is invalid")
                status, context, sequence = _validate_stored_authority(
                    current,
                    event_id=event_id,
                    surface=surface,
                    purpose=purpose,
                    binding_digest=binding_digest,
                )
                if fenced and status == "sending" and context[2] in {"reserved", "consumed"}:
                    current.update(
                        {
                            "status": "needs_owner_action",
                            "owner_hash": "",
                            "updated_at": time.time(),
                            "safe_reason": "authorization_deletion_fenced",
                        }
                    )
                    transaction.set(reference, current)
                    status = "needs_owner_action"
                return MetaOutboundAttemptReceipt(
                    event_id=event_id,
                    surface=surface,
                    purpose=purpose,
                    status=status,
                    image_quota_disposition=context[0],
                    image_quota_allowed_amount=context[1],
                    image_quota_phase=context[2],
                    image_quota_notice_text=context[3],
                    image_quota_notice_sha256=context[4],
                    attempt_sequence=sequence,
                )

            return run_firestore_transaction(db, _reconcile)
        except MetaOutboundAttemptStoreError:
            raise
        except Exception as exc:
            last_error = exc
    raise MetaOutboundAttemptStoreError("Meta image-quota reconciliation failed") from last_error


async def reconcile_image_quota_receipt(
    *,
    event_id: str,
    surface: MetaEvidenceSurface | str | None,
    binding_id: str,
) -> MetaOutboundAttemptReceipt | None:
    """Read quota authority and terminalize safe pre-provider phases when fenced."""

    safe_event_id = _validate_event_id(event_id)
    safe_surface = _validate_surface(surface)
    safe_binding_id = str(binding_id or "").strip()
    db = _db_or_bypass()
    if db is None:
        return None
    return await asyncio.to_thread(
        _reconcile_image_quota_receipt_sync,
        db,
        event_id=safe_event_id,
        surface=safe_surface,
        binding_id=safe_binding_id,
    )


def reconcile_fenced_image_quota_attempts_for_bindings(
    db: Any,
    binding_ids: set[str] | frozenset[str],
) -> int:
    """Settle only exact fenced pre-provider quota rows before deletion scans."""

    safe_bindings = frozenset(str(value).strip() for value in binding_ids if str(value).strip())
    if not safe_bindings:
        return 0
    from services.durable_event_claim import meta_claim_binding_digest
    from services.meta_inbound_deletion_fence import firestore_binding_deletion_fence_ref

    by_digest = {meta_claim_binding_digest(value): value for value in safe_bindings}
    collection = db.collection("artifacts").document(_APP_DOCUMENT).collection(_COLLECTION)
    try:
        snapshots = list(collection.stream())
    except Exception as exc:
        raise MetaOutboundAttemptStoreError("Meta image-quota reconciliation scan failed") from exc
    changed = 0
    for snapshot in snapshots:
        initial = snapshot.to_dict()
        if not isinstance(initial, dict):
            raise MetaOutboundAttemptStoreError("Meta outbound-attempt document is invalid")
        binding_digest = str(initial.get("binding_id_sha256") or "")
        binding_id = by_digest.get(binding_digest)
        if binding_id is None or initial.get("purpose") != "image_quota_notice":
            continue
        reference = getattr(snapshot, "reference", None)
        if reference is None:
            raise MetaOutboundAttemptStoreError("Meta outbound-attempt reference is invalid")
        last_error: Exception | None = None
        for _attempt in range(_MAX_TRANSACTION_ATTEMPTS):
            try:

                def _reconcile_one(
                    transaction: Any,
                    binding_id: str = binding_id,
                    reference: Any = reference,
                    binding_digest: str = binding_digest,
                ) -> bool:
                    fence = firestore_binding_deletion_fence_ref(db, binding_id).get(transaction=transaction)
                    current_snapshot = reference.get(transaction=transaction)
                    if not current_snapshot.exists:
                        return False
                    current = current_snapshot.to_dict()
                    if not isinstance(current, dict):
                        raise MetaOutboundAttemptStoreError("Meta outbound-attempt document is invalid")
                    event_id = _validate_event_id(str(current.get("event_id") or ""))
                    surface = _validate_surface(current.get("surface"))
                    expected_reference = _ref(db, event_id, "image_quota_notice")
                    if str(getattr(reference, "path", "")) != str(getattr(expected_reference, "path", "")):
                        raise MetaOutboundAttemptStoreError("Meta outbound-attempt document identity changed")
                    status, context, _ = _validate_stored_authority(
                        current,
                        event_id=event_id,
                        surface=surface,
                        purpose="image_quota_notice",
                        binding_digest=binding_digest,
                    )
                    if (
                        not fence.exists
                        or status != "sending"
                        or context[2]
                        not in {
                            "reserved",
                            "consumed",
                        }
                    ):
                        return False
                    current.update(
                        {
                            "status": "needs_owner_action",
                            "owner_hash": "",
                            "updated_at": time.time(),
                            "safe_reason": "authorization_deletion_fenced",
                        }
                    )
                    transaction.set(reference, current)
                    return True

                if run_firestore_transaction(db, _reconcile_one):
                    changed += 1
                break
            except MetaOutboundAttemptStoreError:
                raise
            except Exception as exc:
                last_error = exc
        else:
            raise MetaOutboundAttemptStoreError("Meta image-quota reconciliation transaction failed") from last_error
    return changed


def _reserve_image_quota_sync(
    db: Any,
    *,
    event_id: str,
    surface: MetaEvidenceSurface,
    binding_id: str,
    disposition: str,
    allowed_amount: int,
    notice_text: str,
    notice_sha256: str,
    token: str,
) -> MetaOutboundAttemptDecision:
    purpose: MetaOutboundPurpose = "image_quota_notice"
    reference = _ref(db, event_id, purpose)
    fence_reference, binding_digest = _binding_authority(db, binding_id)
    last_error: Exception | None = None
    for _attempt in range(_MAX_TRANSACTION_ATTEMPTS):
        try:

            def _reserve(transaction: Any) -> MetaOutboundAttemptDecision:
                if fence_reference is not None and fence_reference.get(transaction=transaction).exists:
                    return MetaOutboundAttemptDecision(
                        kind="needs_owner_action",
                        event_id=event_id,
                        surface=surface,
                        purpose=purpose,
                        image_quota_disposition=disposition,
                        image_quota_allowed_amount=allowed_amount,
                        image_quota_notice_text=notice_text,
                        image_quota_notice_sha256=notice_sha256,
                        binding_id=binding_id,
                    )
                snapshot = reference.get(transaction=transaction)
                if snapshot.exists:
                    current = snapshot.to_dict()
                    if not isinstance(current, dict):
                        raise MetaOutboundAttemptStoreError("Meta outbound-attempt document is invalid")
                    status, context, sequence = _validate_stored_authority(
                        current,
                        event_id=event_id,
                        surface=surface,
                        purpose=purpose,
                        binding_digest=binding_digest,
                    )
                    if (context[0], context[1], context[3], context[4]) != (
                        disposition,
                        allowed_amount,
                        notice_text,
                        notice_sha256,
                    ):
                        raise MetaOutboundAttemptStoreError("Meta outbound-attempt quota context changed")
                    return MetaOutboundAttemptDecision(
                        kind="duplicate_suppressed" if status == "accepted" else "needs_owner_action",
                        event_id=event_id,
                        surface=surface,
                        purpose=purpose,
                        image_quota_disposition=disposition,
                        image_quota_allowed_amount=allowed_amount,
                        image_quota_phase=context[2],
                        image_quota_notice_text=context[3],
                        image_quota_notice_sha256=context[4],
                        attempt_sequence=sequence,
                        binding_id=binding_id,
                    )
                now = time.time()
                transaction.set(
                    reference,
                    {
                        "schema_version": 2,
                        "event_id": event_id,
                        "purpose": purpose,
                        "image_quota_disposition": disposition,
                        "image_quota_allowed_amount": allowed_amount,
                        "image_quota_phase": "reserved",
                        "image_quota_notice_text": notice_text,
                        "image_quota_notice_sha256": notice_sha256,
                        "surface": surface,
                        "status": "sending",
                        "attempt_sequence": 0,
                        "owner_hash": _owner_hash(token),
                        "created_at": now,
                        "updated_at": now,
                        "safe_reason": "quota_reserved",
                        "provider_message_id_sha256": "",
                        "binding_id_sha256": binding_digest,
                    },
                )
                return MetaOutboundAttemptDecision(
                    kind="quota_reserved",
                    event_id=event_id,
                    surface=surface,
                    purpose=purpose,
                    image_quota_disposition=disposition,
                    image_quota_allowed_amount=allowed_amount,
                    image_quota_phase="reserved",
                    image_quota_notice_text=notice_text,
                    image_quota_notice_sha256=notice_sha256,
                    attempt_token=token,
                    binding_id=binding_id,
                )

            return run_firestore_transaction(db, _reserve)
        except MetaOutboundAttemptStoreError:
            raise
        except Exception as exc:
            last_error = exc
    raise MetaOutboundAttemptStoreError("Meta image-quota reservation transaction failed") from last_error


async def reserve_image_quota_notice(
    *,
    event_id: str,
    surface: MetaEvidenceSurface | str | None,
    binding_id: str,
    disposition: ImageQuotaDisposition | str,
    allowed_amount: int,
    notice_text: str = "",
) -> MetaOutboundAttemptDecision:
    """Publish one image-quota intent before the non-idempotent mutation."""

    safe_event_id = _validate_event_id(event_id)
    safe_surface = _validate_surface(surface)
    safe_binding_id = str(binding_id or "").strip()
    safe_disposition, safe_allowed, _, safe_notice, safe_notice_sha256 = _validate_quota_context(
        "image_quota_notice",
        disposition,
        allowed_amount,
        notice_text=notice_text,
    )
    db = _db_or_bypass()
    if db is not None and not safe_binding_id:
        from config import is_production_runtime

        if is_production_runtime():
            raise MetaOutboundAttemptStoreError("Meta outbound binding identity is required")
    if db is None:
        return MetaOutboundAttemptDecision(
            kind="nonproduction_bypass",
            event_id=safe_event_id,
            surface=safe_surface,
            purpose="image_quota_notice",
            image_quota_disposition=safe_disposition,
            image_quota_allowed_amount=safe_allowed,
            image_quota_notice_text=safe_notice,
            image_quota_notice_sha256=safe_notice_sha256,
            binding_id=safe_binding_id,
        )
    return await asyncio.to_thread(
        _reserve_image_quota_sync,
        db,
        event_id=safe_event_id,
        surface=safe_surface,
        binding_id=safe_binding_id,
        disposition=safe_disposition,
        allowed_amount=safe_allowed,
        notice_text=safe_notice,
        notice_sha256=safe_notice_sha256,
        token=secrets.token_urlsafe(32),
    )


def _confirm_quota_consumed_sync(db: Any, decision: MetaOutboundAttemptDecision) -> bool:
    reference = _ref(db, decision.event_id, decision.purpose)
    fence_reference, binding_digest = _binding_authority(db, decision.binding_id)
    last_error: Exception | None = None
    for _attempt in range(_MAX_TRANSACTION_ATTEMPTS):
        try:

            def _confirm(transaction: Any) -> bool:
                snapshot = reference.get(transaction=transaction)
                current = snapshot.to_dict() if snapshot.exists else None
                if not isinstance(current, dict):
                    raise MetaOutboundAttemptStoreError("Meta image-quota reservation disappeared")
                status, context, _ = _validate_stored_authority(
                    current,
                    event_id=decision.event_id,
                    surface=decision.surface,
                    purpose=decision.purpose,
                    binding_digest=binding_digest,
                )
                if (
                    status != "sending"
                    or context
                    != (
                        decision.image_quota_disposition,
                        decision.image_quota_allowed_amount,
                        "reserved",
                        decision.image_quota_notice_text,
                        decision.image_quota_notice_sha256,
                    )
                    or str(current.get("owner_hash") or "") != _owner_hash(decision.attempt_token)
                ):
                    raise MetaOutboundAttemptStoreError("Meta image-quota reservation ownership changed")
                fenced = bool(fence_reference is not None and fence_reference.get(transaction=transaction).exists)
                current.update(
                    {
                        "status": "needs_owner_action" if fenced else "sending",
                        "image_quota_phase": "consumed",
                        "owner_hash": "",
                        "updated_at": time.time(),
                        "safe_reason": ("authorization_deletion_fenced_after_quota" if fenced else "quota_consumed"),
                    }
                )
                transaction.set(reference, current)
                return not fenced

            return run_firestore_transaction(db, _confirm)
        except MetaOutboundAttemptStoreError:
            raise
        except Exception as exc:
            last_error = exc
    raise MetaOutboundAttemptStoreError("Meta image-quota confirmation transaction failed") from last_error


async def confirm_image_quota_consumed(decision: MetaOutboundAttemptDecision) -> bool:
    """Durably record the one quota mutation before any provider call."""

    if decision.kind == "nonproduction_bypass":
        return True
    if (
        decision.kind != "quota_reserved"
        or decision.purpose != "image_quota_notice"
        or decision.image_quota_phase != "reserved"
        or not decision.attempt_token
    ):
        raise MetaOutboundAttemptStoreError("Meta image-quota reservation cannot be confirmed")
    db = _db_or_bypass()
    if db is None:
        raise MetaOutboundAttemptStoreError("Shared Meta outbound-attempt store disappeared")
    return await asyncio.to_thread(_confirm_quota_consumed_sync, db, decision)


def _finalize_allowed_quota_sync(
    db: Any,
    *,
    event_id: str,
    surface: MetaEvidenceSurface,
    binding_id: str,
    allowed_amount: int,
) -> bool:
    purpose: MetaOutboundPurpose = "image_quota_notice"
    reference = _ref(db, event_id, purpose)
    fence_reference, binding_digest = _binding_authority(db, binding_id)
    last_error: Exception | None = None
    for _attempt in range(_MAX_TRANSACTION_ATTEMPTS):
        try:

            def _finalize(transaction: Any) -> bool:
                fenced = bool(fence_reference is not None and fence_reference.get(transaction=transaction).exists)
                snapshot = reference.get(transaction=transaction)
                current = snapshot.to_dict() if snapshot.exists else None
                if not isinstance(current, dict):
                    raise MetaOutboundAttemptStoreError("Meta allowed-quota authority disappeared")
                status, context, _ = _validate_stored_authority(
                    current,
                    event_id=event_id,
                    surface=surface,
                    purpose=purpose,
                    binding_digest=binding_digest,
                )
                if context != ("allowed", allowed_amount, "consumed", "", ""):
                    raise MetaOutboundAttemptStoreError("Meta allowed-quota context changed")
                if status == "accepted":
                    return True
                if status == "needs_owner_action":
                    return False
                if status != "sending":
                    raise MetaOutboundAttemptStoreError("Meta allowed-quota state changed")
                current.update(
                    {
                        "status": "needs_owner_action" if fenced else "accepted",
                        "owner_hash": "",
                        "updated_at": time.time(),
                        "safe_reason": ("authorization_deletion_fenced" if fenced else "quota_allowed_without_notice"),
                        "provider_message_id_sha256": "",
                    }
                )
                transaction.set(reference, current)
                return not fenced

            return run_firestore_transaction(db, _finalize)
        except MetaOutboundAttemptStoreError:
            raise
        except Exception as exc:
            last_error = exc
    raise MetaOutboundAttemptStoreError("Meta allowed-quota finalization transaction failed") from last_error


async def finalize_allowed_image_quota(
    *,
    event_id: str,
    surface: MetaEvidenceSurface | str | None,
    binding_id: str,
    allowed_amount: int,
) -> bool:
    """Terminally record a consumed quota slot that requires no notice."""

    safe_event_id = _validate_event_id(event_id)
    safe_surface = _validate_surface(surface)
    safe_binding_id = str(binding_id or "").strip()
    _, safe_allowed, _, _, _ = _validate_quota_context("image_quota_notice", "allowed", allowed_amount)
    db = _db_or_bypass()
    if db is not None and not safe_binding_id:
        from config import is_production_runtime

        if is_production_runtime():
            raise MetaOutboundAttemptStoreError("Meta outbound binding identity is required")
    if db is None:
        return True
    return await asyncio.to_thread(
        _finalize_allowed_quota_sync,
        db,
        event_id=safe_event_id,
        surface=safe_surface,
        binding_id=safe_binding_id,
        allowed_amount=safe_allowed,
    )


def _begin_sync(
    db: Any,
    *,
    event_id: str,
    surface: MetaEvidenceSurface,
    token: str,
    binding_id: str,
    purpose: MetaOutboundPurpose,
    image_quota_disposition: str,
    image_quota_allowed_amount: int,
    image_quota_notice_text: str,
    image_quota_notice_sha256: str,
) -> MetaOutboundAttemptDecision:
    reference = _ref(db, event_id, purpose)
    fence_reference, binding_digest = _binding_authority(db, binding_id)

    def _begin(transaction: Any) -> MetaOutboundAttemptDecision:
        fenced = bool(fence_reference is not None and fence_reference.get(transaction=transaction).exists)
        snapshot = reference.get(transaction=transaction)
        current = snapshot.to_dict() if snapshot.exists else {}
        current = current if isinstance(current, dict) else {}
        status: str = ""
        stored_context = ("", 0, "", "", "")
        if snapshot.exists:
            stored_status, stored_context, _ = _validate_stored_authority(
                current,
                event_id=event_id,
                surface=surface,
                purpose=purpose,
                binding_digest=binding_digest,
            )
            status = stored_status
            if (stored_context[0], stored_context[1], stored_context[3], stored_context[4]) != (
                image_quota_disposition,
                image_quota_allowed_amount,
                image_quota_notice_text,
                image_quota_notice_sha256,
            ):
                raise MetaOutboundAttemptStoreError("Meta outbound-attempt quota context changed")
        if status != "accepted":
            for predecessor in _PURPOSE_PREDECESSORS[purpose]:
                predecessor_snapshot = _ref(db, event_id, predecessor).get(transaction=transaction)
                if not predecessor_snapshot.exists:
                    continue
                predecessor_current = predecessor_snapshot.to_dict()
                if not isinstance(predecessor_current, dict):
                    raise MetaOutboundAttemptStoreError("Meta outbound-attempt predecessor is invalid")
                predecessor_status, _, _ = _validate_stored_authority(
                    predecessor_current,
                    event_id=event_id,
                    surface=surface,
                    purpose=predecessor,
                    binding_digest=binding_digest,
                )
                rollout_primary_barrier = (
                    predecessor == "primary_reply"
                    and purpose in {"session_greeting", "gender_ack"}
                    and predecessor_status == "accepted"
                )
                if predecessor_status in {"sending", "needs_owner_action"} or rollout_primary_barrier:
                    return MetaOutboundAttemptDecision(
                        kind="needs_owner_action",
                        event_id=event_id,
                        surface=surface,
                        purpose=purpose,
                        image_quota_disposition=image_quota_disposition,
                        image_quota_allowed_amount=image_quota_allowed_amount,
                        image_quota_phase=stored_context[2],
                        image_quota_notice_text=image_quota_notice_text,
                        image_quota_notice_sha256=image_quota_notice_sha256,
                        attempt_sequence=int(current.get("attempt_sequence") or 0),
                        binding_id=binding_id,
                    )
        quota_phase = stored_context[2]
        if fenced:
            if (
                snapshot.exists
                and purpose == "image_quota_notice"
                and status == "sending"
                and quota_phase in {"reserved", "consumed"}
            ):
                current.update(
                    {
                        "status": "needs_owner_action",
                        "owner_hash": "",
                        "updated_at": time.time(),
                        "safe_reason": "authorization_deletion_fenced",
                    }
                )
                transaction.set(reference, current)
            return MetaOutboundAttemptDecision(
                kind="needs_owner_action",
                event_id=event_id,
                surface=surface,
                purpose=purpose,
                image_quota_disposition=image_quota_disposition,
                image_quota_allowed_amount=image_quota_allowed_amount,
                image_quota_phase=quota_phase,
                image_quota_notice_text=image_quota_notice_text,
                image_quota_notice_sha256=image_quota_notice_sha256,
                attempt_sequence=int(current.get("attempt_sequence") or 0),
                binding_id=binding_id,
            )
        if status == "accepted":
            return MetaOutboundAttemptDecision(
                kind="duplicate_suppressed",
                event_id=event_id,
                surface=surface,
                purpose=purpose,
                image_quota_disposition=image_quota_disposition,
                image_quota_allowed_amount=image_quota_allowed_amount,
                image_quota_phase=quota_phase,
                image_quota_notice_text=image_quota_notice_text,
                image_quota_notice_sha256=image_quota_notice_sha256,
                attempt_sequence=int(current.get("attempt_sequence") or 0),
                binding_id=binding_id,
            )
        if status == "needs_owner_action" or (
            status == "sending" and not (purpose == "image_quota_notice" and quota_phase == "consumed")
        ):
            return MetaOutboundAttemptDecision(
                kind="needs_owner_action",
                event_id=event_id,
                surface=surface,
                purpose=purpose,
                image_quota_disposition=image_quota_disposition,
                image_quota_allowed_amount=image_quota_allowed_amount,
                image_quota_phase=quota_phase,
                image_quota_notice_text=image_quota_notice_text,
                image_quota_notice_sha256=image_quota_notice_sha256,
                attempt_sequence=int(current.get("attempt_sequence") or 0),
                binding_id=binding_id,
            )
        if status == "" and purpose == "image_quota_notice":
            raise MetaOutboundAttemptStoreError("Image-quota notice must be durably reserved before send")
        if status not in {"", "sending", "definitive_failure"}:
            raise MetaOutboundAttemptStoreError("Meta outbound-attempt state is invalid")
        sequence = int(current.get("attempt_sequence") or 0) + 1
        now = time.time()
        transaction.set(
            reference,
            {
                "schema_version": 2,
                "event_id": event_id,
                "purpose": purpose,
                "image_quota_disposition": image_quota_disposition,
                "image_quota_allowed_amount": image_quota_allowed_amount,
                "image_quota_phase": "provider" if purpose == "image_quota_notice" else "",
                "image_quota_notice_text": image_quota_notice_text,
                "image_quota_notice_sha256": image_quota_notice_sha256,
                "surface": surface,
                "status": "sending",
                "attempt_sequence": sequence,
                "owner_hash": _owner_hash(token),
                "created_at": float(current.get("created_at") or now),
                "updated_at": now,
                "safe_reason": "none",
                "provider_message_id_sha256": "",
                "binding_id_sha256": binding_digest,
            },
        )
        return MetaOutboundAttemptDecision(
            kind="send",
            event_id=event_id,
            surface=surface,
            purpose=purpose,
            image_quota_disposition=image_quota_disposition,
            image_quota_allowed_amount=image_quota_allowed_amount,
            image_quota_phase="provider" if purpose == "image_quota_notice" else "",
            image_quota_notice_text=image_quota_notice_text,
            image_quota_notice_sha256=image_quota_notice_sha256,
            attempt_token=token,
            attempt_sequence=sequence,
            binding_id=binding_id,
        )

    last_error: Exception | None = None
    for _attempt in range(_MAX_TRANSACTION_ATTEMPTS):
        try:
            return run_firestore_transaction(db, _begin)
        except MetaOutboundAttemptStoreError:
            raise
        except Exception as exc:
            last_error = exc
    raise MetaOutboundAttemptStoreError("Meta outbound-attempt begin transaction failed") from last_error


async def begin_meta_outbound_attempt(
    *,
    event_id: str,
    surface: MetaEvidenceSurface | str | None,
    binding_id: str = "",
    purpose: MetaOutboundPurpose | str = "primary_reply",
    image_quota_disposition: ImageQuotaDisposition | str = "",
    image_quota_allowed_amount: int = 0,
    image_quota_notice_text: str = "",
) -> MetaOutboundAttemptDecision:
    """Reserve one provider call or return a safe non-send decision."""

    safe_event_id = _validate_event_id(event_id)
    safe_surface = _validate_surface(surface)
    safe_purpose = _validate_purpose(purpose)
    quota_disposition, quota_allowed_amount, _, quota_notice_text, quota_notice_sha256 = _validate_quota_context(
        safe_purpose,
        image_quota_disposition,
        image_quota_allowed_amount,
        notice_text=image_quota_notice_text,
    )
    if safe_purpose == "image_quota_notice" and quota_disposition == "allowed":
        raise ValueError("Allowed image quota has no provider notice")
    safe_binding_id = str(binding_id or "").strip()
    db = _db_or_bypass()
    if db is not None and not safe_binding_id:
        from config import is_production_runtime

        if is_production_runtime():
            raise MetaOutboundAttemptStoreError("Meta outbound binding identity is required")
    if db is None:
        return MetaOutboundAttemptDecision(
            kind="nonproduction_bypass",
            event_id=safe_event_id,
            surface=safe_surface,
            purpose=safe_purpose,
            image_quota_disposition=quota_disposition,
            image_quota_allowed_amount=quota_allowed_amount,
            image_quota_notice_text=quota_notice_text,
            image_quota_notice_sha256=quota_notice_sha256,
            binding_id=safe_binding_id,
        )
    token = secrets.token_urlsafe(32)
    return await asyncio.to_thread(
        _begin_sync,
        db,
        event_id=safe_event_id,
        surface=safe_surface,
        token=token,
        binding_id=safe_binding_id,
        purpose=safe_purpose,
        image_quota_disposition=quota_disposition,
        image_quota_allowed_amount=quota_allowed_amount,
        image_quota_notice_text=quota_notice_text,
        image_quota_notice_sha256=quota_notice_sha256,
    )


async def _binding_is_fenced(binding_id: str) -> bool:
    if not binding_id:
        return False
    db = _db_or_bypass()
    if db is None:
        return False
    from services.meta_inbound_deletion_fence import firestore_binding_deletion_fence_ref

    reference = firestore_binding_deletion_fence_ref(db, binding_id)
    try:
        return bool((await asyncio.to_thread(reference.get)).exists)
    except Exception as exc:
        raise MetaOutboundAttemptStoreError("Meta outbound fence cannot be verified") from exc


def _finish_sync(
    db: Any,
    *,
    decision: MetaOutboundAttemptDecision,
    status: Literal["accepted", "definitive_failure", "needs_owner_action"],
    safe_reason: str,
    provider_message_id: str = "",
) -> None:
    reference = _ref(db, decision.event_id, decision.purpose)
    _, binding_digest = _binding_authority(db, decision.binding_id)
    last_error: Exception | None = None
    for _attempt in range(_MAX_TRANSACTION_ATTEMPTS):
        try:

            def _finish(transaction: Any) -> None:
                snapshot = reference.get(transaction=transaction)
                current = snapshot.to_dict() if snapshot.exists else {}
                current = current if isinstance(current, dict) else {}
                if snapshot.exists:
                    _, stored_context, _ = _validate_stored_authority(
                        current,
                        event_id=decision.event_id,
                        surface=decision.surface,
                        purpose=decision.purpose,
                        binding_digest=binding_digest,
                    )
                    if stored_context != (
                        decision.image_quota_disposition,
                        decision.image_quota_allowed_amount,
                        decision.image_quota_phase,
                        decision.image_quota_notice_text,
                        decision.image_quota_notice_sha256,
                    ):
                        raise MetaOutboundAttemptStoreError("Meta outbound-attempt quota context changed")
                if (
                    str(current.get("status") or "") != "sending"
                    or int(current.get("attempt_sequence") or 0) != decision.attempt_sequence
                    or str(current.get("owner_hash") or "") != _owner_hash(decision.attempt_token)
                ):
                    raise MetaOutboundAttemptStoreError("Meta outbound-attempt ownership changed")
                current.update(
                    {
                        "status": status,
                        "updated_at": time.time(),
                        "safe_reason": safe_reason,
                        "owner_hash": "",
                        "provider_message_id_sha256": (
                            _provider_id_hash(provider_message_id) if provider_message_id else ""
                        ),
                    }
                )
                transaction.set(reference, current)

            run_firestore_transaction(db, _finish)
            return
        except MetaOutboundAttemptStoreError:
            raise
        except Exception as exc:
            last_error = exc
    raise MetaOutboundAttemptStoreError("Meta outbound-attempt completion transaction failed") from last_error


async def finish_meta_outbound_attempt(
    decision: MetaOutboundAttemptDecision,
    *,
    status: Literal["accepted", "definitive_failure", "needs_owner_action"],
    safe_reason: str,
    provider_message_id: str = "",
) -> None:
    """Finalize the exact attempt owner without storing provider identifiers."""

    if decision.kind == "nonproduction_bypass":
        return
    if decision.kind != "send" or not decision.attempt_token:
        raise MetaOutboundAttemptStoreError("Meta outbound-attempt decision cannot be finalized")
    db = _db_or_bypass()
    if db is None:
        raise MetaOutboundAttemptStoreError("Shared Meta outbound-attempt store disappeared")
    await asyncio.to_thread(
        _finish_sync,
        db,
        decision=decision,
        status=status,
        safe_reason=str(safe_reason or "unknown")[:64],
        provider_message_id=str(provider_message_id or "").strip(),
    )


def duplicate_suppressed_result() -> dict[str, Any]:
    return {
        "success": False,
        "retryable": False,
        "duplicate_suppressed": True,
        "reason": "meta_outbound_duplicate_suppressed",
    }


def needs_owner_action_result() -> dict[str, Any]:
    return {
        "success": False,
        "retryable": False,
        "needs_owner_action": True,
        "reason": "meta_outbound_ambiguous_needs_owner_action",
    }


def _returned_rejection_is_definitive(result: Any) -> bool:
    """Return whether a result proves that Meta did not accept the send.

    HTTP 429/408/5xx are retryable, not owner-action. Only a non-throttle 4xx
    proves the provider rejected the request.
    """

    from services.omnichannel.classify import returned_rejection_is_definitive

    return returned_rejection_is_definitive(result)


async def execute_guarded_meta_send(
    *,
    event_id: str,
    surface: MetaEvidenceSurface | str | None,
    binding_id: str = "",
    purpose: MetaOutboundPurpose | str = "primary_reply",
    image_quota_disposition: ImageQuotaDisposition | str = "",
    image_quota_allowed_amount: int = 0,
    image_quota_notice_text: str = "",
    send: Any,
) -> Any:
    """Execute one Meta send with crash-safe, fail-closed duplicate semantics."""

    decision = await begin_meta_outbound_attempt(
        event_id=event_id,
        surface=surface,
        binding_id=binding_id,
        purpose=purpose,
        image_quota_disposition=image_quota_disposition,
        image_quota_allowed_amount=image_quota_allowed_amount,
        image_quota_notice_text=image_quota_notice_text,
    )
    if decision.kind == "duplicate_suppressed":
        return duplicate_suppressed_result()
    if decision.kind == "needs_owner_action":
        return needs_owner_action_result()
    if decision.kind == "send" and await _binding_is_fenced(decision.binding_id):
        try:
            await finish_meta_outbound_attempt(
                decision,
                status="needs_owner_action",
                safe_reason="authorization_deletion_fenced",
            )
        except BaseException:
            pass
        return needs_owner_action_result()
    try:
        result = await send()
    except BaseException as exc:
        if decision.kind == "send":
            from services.meta_session_invalidated import mark_if_session_invalidated
            from services.omnichannel.meta_errors import finish_status_for_send_exception

            mark_if_session_invalidated(exc, binding_id=str(decision.binding_id or binding_id or ""))
            status, safe_reason = finish_status_for_send_exception(exc)
            try:
                await asyncio.shield(
                    finish_meta_outbound_attempt(
                        decision,
                        status=status,
                        safe_reason=safe_reason,
                    )
                )
            except BaseException:
                pass
        raise

    from services.ai_reply_delivery import classify_send_result

    evidence = classify_send_result(result)
    provider_message_id = str(evidence.get("provider_message_id") or "").strip()
    if evidence.get("success") is True and provider_message_id:
        if decision.kind == "send":
            try:
                await finish_meta_outbound_attempt(
                    decision,
                    status="accepted",
                    safe_reason="provider_accepted",
                    provider_message_id=provider_message_id,
                )
            except BaseException:
                return needs_owner_action_result()
        return result

    # A nominal success without a provider id is ambiguous: Meta may have
    # accepted it while the evidence was lost.  The same is true for returned
    # 5xx/timeout-like failures.  Only an explicit 4xx proves non-acceptance.
    nominal_success = isinstance(result, dict) and result.get("success") is True
    meta_missing_message_id = (
        isinstance(result, dict)
        and result.get("provider") == "meta"
        and result.get("error") == "meta_send_missing_message_id"
    )
    if decision.kind == "send":
        if nominal_success or meta_missing_message_id or not _returned_rejection_is_definitive(result):
            try:
                await finish_meta_outbound_attempt(
                    decision,
                    status="needs_owner_action",
                    safe_reason=(
                        "accepted_without_provider_id"
                        if nominal_success or meta_missing_message_id
                        else "provider_result_ambiguous"
                    ),
                )
            except BaseException:
                pass
            return needs_owner_action_result()
        try:
            await finish_meta_outbound_attempt(
                decision,
                status="definitive_failure",
                safe_reason="provider_rejected",
            )
        except BaseException:
            return needs_owner_action_result()
    return result
