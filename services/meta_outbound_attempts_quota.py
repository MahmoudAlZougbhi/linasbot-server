"""Image-quota reserve, confirm, finalize, and receipt reconcile for Meta outbound attempts."""

from __future__ import annotations

import asyncio
import secrets
import time
from typing import Any

from services.firestore_transaction_compat import run_firestore_transaction
from services.meta_controlled_evidence import MetaEvidenceSurface
from services.meta_outbound_attempts_types import (
    _MAX_TRANSACTION_ATTEMPTS,
    ImageQuotaDisposition,
    MetaOutboundAttemptDecision,
    MetaOutboundAttemptReceipt,
    MetaOutboundAttemptStoreError,
    MetaOutboundPurpose,
)
from services.meta_outbound_attempts_validate import (
    _binding_authority,
    _db_or_bypass,
    _owner_hash,
    _ref,
    _validate_event_id,
    _validate_quota_context,
    _validate_stored_authority,
    _validate_surface,
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
