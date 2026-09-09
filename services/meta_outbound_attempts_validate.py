"""Validators, hashes, and stored identity/authority checks for Meta outbound attempts."""

from __future__ import annotations

import asyncio
import hashlib
import time
import unicodedata
from typing import Any

from services.firestore_transaction_compat import run_firestore_transaction
from services.meta_controlled_evidence import MetaEvidenceSurface
from services.meta_outbound_attempts_types import (
    _ALLOWED_QUOTA_DISPOSITIONS,
    _ALLOWED_QUOTA_PHASES,
    _ALLOWED_STATUSES,
    _ALLOWED_SURFACES,
    _APP_DOCUMENT,
    _COLLECTION,
    _EVENT_ID_RE,
    _IMAGE_QUOTA_NOTICE_DOMAIN,
    _MAX_IMAGE_QUOTA_NOTICE_BYTES,
    _MAX_TRANSACTION_ATTEMPTS,
    _PURPOSE_DOCUMENT_DOMAIN,
    _SHA256_RE,
    ImageQuotaDisposition,
    ImageQuotaPhase,
    MetaOutboundAttemptReceipt,
    MetaOutboundAttemptStatus,
    MetaOutboundAttemptStoreError,
    MetaOutboundPurpose,
    _validate_purpose,
)


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
