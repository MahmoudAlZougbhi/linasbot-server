"""Begin/finish Firestore transactions for one Meta outbound provider attempt."""

from __future__ import annotations

import time
from typing import Any, Literal

from services.firestore_transaction_compat import run_firestore_transaction
from services.meta_controlled_evidence import MetaEvidenceSurface
from services.meta_outbound_attempts_types import (
    _MAX_TRANSACTION_ATTEMPTS,
    MetaOutboundAttemptDecision,
    MetaOutboundAttemptStoreError,
    MetaOutboundPurpose,
)
from services.meta_outbound_attempts_validate import (
    _binding_authority,
    _owner_hash,
    _provider_id_hash,
    _ref,
    _validate_stored_authority,
)
from services.meta_outbound_purposes import PURPOSE_PREDECESSORS as _PURPOSE_PREDECESSORS


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
