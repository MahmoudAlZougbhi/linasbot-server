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
import secrets
from typing import Any, Literal

from services.meta_controlled_evidence import MetaEvidenceSurface
from services.meta_outbound_attempts_quota import (  # noqa: F401
    _confirm_quota_consumed_sync,
    _finalize_allowed_quota_sync,
    _reconcile_image_quota_receipt_sync,
    _reserve_image_quota_sync,
    confirm_image_quota_consumed,
    finalize_allowed_image_quota,
    reconcile_image_quota_receipt,
    reserve_image_quota_notice,
)
from services.meta_outbound_attempts_send import _begin_sync, _finish_sync
from services.meta_outbound_attempts_types import (  # noqa: F401
    _ALLOWED_PURPOSES,
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
    _SEND_PURPOSE,
    _SHA256_RE,
    AttemptDecisionKind,
    ImageQuotaDisposition,
    ImageQuotaPhase,
    MetaOutboundAttemptDecision,
    MetaOutboundAttemptReceipt,
    MetaOutboundAttemptStatus,
    MetaOutboundAttemptStoreError,
    MetaOutboundPurpose,
    _validate_purpose,
    current_meta_outbound_send_purpose,
    meta_outbound_send_purpose,
)
from services.meta_outbound_attempts_validate import (  # noqa: F401
    _attempt_document_id,
    _binding_authority,
    _db_or_bypass,
    _owner_hash,
    _provider_id_hash,
    _read_receipt_sync,
    _ref,
    _validate_event_id,
    _validate_quota_context,
    _validate_stored_authority,
    _validate_stored_identity,
    _validate_surface,
    read_meta_outbound_attempt_receipt,
    reconcile_fenced_image_quota_attempts_for_bindings,
)
from services.meta_outbound_purposes import PURPOSE_PREDECESSORS as _PURPOSE_PREDECESSORS  # noqa: F401


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

            mark_if_session_invalidated(
                exc,
                binding_id=str(decision.binding_id or binding_id or ""),
                require_invalidation_wording=True,
            )
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
