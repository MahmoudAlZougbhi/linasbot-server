"""Claim-before-effect for ASSN notificationUUID idempotency.

Insert ``processing`` immediately after UUID extract, before any financial
effect. Concurrent workers hitting the same PK get ``duplicate=True``.

``failed`` rows may be re-driven (crash recovery): reclaim sets status back
to ``processing``. ``applied`` / ``ignored`` / in-flight ``processing``
are duplicates and must not re-apply effects.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from sqlalchemy import update
from sqlalchemy.exc import IntegrityError

from db.models.apple_billing import AppleNotificationEventRow
from db.session import whatsapp_session

logger = logging.getLogger(__name__)

_TERMINAL_OR_INFLIGHT = frozenset({"applied", "ignored", "processing"})


def claim_notification(
    *,
    notification_uuid: str,
    notification_type: str,
    subtype: str | None,
    environment: str,
    signed_payload_sha256: str,
    related_transaction_id: str | None = None,
) -> dict[str, Any]:
    """INSERT processing row; on conflict treat applied/ignored/processing as duplicate.

    Returns:
      ``{"duplicate": False, "claimed": True, ...}`` on success, or
      ``{"duplicate": True, "processing_status": ..., "result": ...}`` when
      another worker already owns / finished the UUID.

    ``failed`` rows may be re-driven: CAS update ``failed`` → ``processing``.
    """
    uuid = str(notification_uuid or "").strip()
    if not uuid:
        raise ValueError("notification_uuid required")
    now = time.time()
    ntype = str(notification_type or "").strip().upper()
    env = str(environment or "Unknown")

    with whatsapp_session() as session:
        existing = session.get(AppleNotificationEventRow, uuid)
        if existing is not None:
            if existing.processing_status == "failed":
                # Crash recovery: failed may be re-driven (CAS so only one winner).
                res = session.execute(
                    update(AppleNotificationEventRow)
                    .where(
                        AppleNotificationEventRow.notification_uuid == uuid,
                        AppleNotificationEventRow.processing_status == "failed",
                    )
                    .values(
                        processing_status="processing",
                        last_seen_at=now,
                        notification_type=ntype or existing.notification_type,
                        subtype=subtype if subtype is not None else existing.subtype,
                        environment=env,
                        signed_payload_sha256=signed_payload_sha256,
                        related_transaction_id=related_transaction_id
                        or existing.related_transaction_id,
                        result={},
                    )
                )
                if int(res.rowcount or 0) == 1:
                    logger.info("apple_assn_reclaim_failed uuid=%s type=%s", uuid, ntype)
                    return {
                        "duplicate": False,
                        "claimed": True,
                        "retried": True,
                        "notification_uuid": uuid,
                    }
                session.refresh(existing)
                return {
                    "duplicate": True,
                    "claimed": False,
                    "processing_status": existing.processing_status,
                    "result": dict(existing.result or {}),
                    "notification_uuid": uuid,
                }
            if existing.processing_status in _TERMINAL_OR_INFLIGHT:
                logger.info(
                    "apple_assn_claim_duplicate uuid=%s status=%s type=%s",
                    uuid,
                    existing.processing_status,
                    ntype,
                )
                return {
                    "duplicate": True,
                    "claimed": False,
                    "processing_status": existing.processing_status,
                    "result": dict(existing.result or {}),
                    "notification_uuid": uuid,
                }

        try:
            with session.begin_nested():
                session.add(
                    AppleNotificationEventRow(
                        notification_uuid=uuid,
                        notification_type=ntype,
                        subtype=subtype,
                        environment=env,
                        signed_payload_sha256=signed_payload_sha256,
                        processing_status="processing",
                        first_seen_at=now,
                        last_seen_at=now,
                        result={},
                        related_transaction_id=related_transaction_id,
                    )
                )
                session.flush()
        except IntegrityError:
            session.expire_all()
            row = session.get(AppleNotificationEventRow, uuid)
            status = row.processing_status if row is not None else "processing"
            if row is not None and row.processing_status == "failed":
                res = session.execute(
                    update(AppleNotificationEventRow)
                    .where(
                        AppleNotificationEventRow.notification_uuid == uuid,
                        AppleNotificationEventRow.processing_status == "failed",
                    )
                    .values(
                        processing_status="processing",
                        last_seen_at=now,
                        result={},
                    )
                )
                if int(res.rowcount or 0) == 1:
                    return {
                        "duplicate": False,
                        "claimed": True,
                        "retried": True,
                        "notification_uuid": uuid,
                    }
            logger.info(
                "apple_assn_claim_integrity uuid=%s status=%s",
                uuid,
                status,
            )
            return {
                "duplicate": True,
                "claimed": False,
                "processing_status": status,
                "result": dict(row.result or {}) if row is not None else {},
                "notification_uuid": uuid,
            }

    return {
        "duplicate": False,
        "claimed": True,
        "retried": False,
        "notification_uuid": uuid,
    }


def finalize_notification(
    *,
    notification_uuid: str,
    processing_status: str,
    result: dict[str, Any],
    related_transaction_id: str | None = None,
    notification_type: str | None = None,
    subtype: str | None = None,
) -> dict[str, Any]:
    """Update claim row to applied / ignored / failed after effects (or on error)."""
    uuid = str(notification_uuid or "").strip()
    status = str(processing_status or "").strip().lower()
    if status not in {"applied", "ignored", "failed"}:
        raise ValueError(f"invalid finalize status: {processing_status}")
    now = time.time()
    with whatsapp_session() as session:
        row = session.get(AppleNotificationEventRow, uuid)
        if row is None:
            # Should not happen if claim ran first; insert terminal row for durability.
            session.add(
                AppleNotificationEventRow(
                    notification_uuid=uuid,
                    notification_type=str(notification_type or "UNKNOWN"),
                    subtype=subtype,
                    environment="Unknown",
                    signed_payload_sha256="",
                    processing_status=status,
                    first_seen_at=now,
                    last_seen_at=now,
                    result=result,
                    related_transaction_id=related_transaction_id,
                )
            )
            return {"ok": True, "created": True, "processing_status": status}
        # Do not overwrite a terminal applied/ignored finished by another worker.
        if row.processing_status in {"applied", "ignored"} and status == "failed":
            return {
                "ok": True,
                "skipped": True,
                "processing_status": row.processing_status,
                "result": dict(row.result or {}),
            }
        row.processing_status = status
        row.last_seen_at = now
        row.result = result
        if related_transaction_id:
            row.related_transaction_id = related_transaction_id
        if notification_type:
            row.notification_type = str(notification_type).strip().upper()
        if subtype is not None:
            row.subtype = subtype
        return {"ok": True, "processing_status": status}
