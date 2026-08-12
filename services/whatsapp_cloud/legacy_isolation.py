"""Legacy MontyMobile / BSP isolation — fail closed on dual ownership."""

from __future__ import annotations

import os
from typing import Any

from db.session import whatsapp_db_configured, whatsapp_session
from services.whatsapp_cloud.observability import emit_wa_event
from services.whatsapp_cloud.repository import WhatsAppCloudRepository


class LegacyIsolationScanError(RuntimeError):
    """Cloud bind scan could not complete — callers must fail closed."""


def _normalize_digits(value: str) -> str:
    return "".join(ch for ch in str(value or "") if ch.isdigit())


def monty_source_number_digits() -> str:
    return _normalize_digits(os.getenv("MONTYMOBILE_SOURCE_NUMBER") or "")


def cloud_bound_display_digits() -> set[str]:
    """Return active Cloud display digits.

    When WhatsApp DB is not configured, returns empty set (no Cloud binds).
    On DB/scan failure raises LegacyIsolationScanError (fail closed — never empty-on-error).
    """
    if not whatsapp_db_configured():
        return set()
    try:
        with whatsapp_session() as session:
            # Scan active connections — small pilot scale; indexed later if needed.
            from sqlalchemy import select

            from db.models.whatsapp_cloud import WhatsAppConnection
            from services.whatsapp_cloud.repository import ACTIVE_LIFECYCLES

            rows = session.scalars(
                select(WhatsAppConnection).where(WhatsAppConnection.lifecycle_status.in_(tuple(ACTIVE_LIFECYCLES)))
            ).all()
            out: set[str] = set()
            for row in rows:
                digits = _normalize_digits(row.display_phone_number)
                if digits:
                    out.add(digits)
                if row.display_phone_last4:
                    out.add(row.display_phone_last4)
            return out
    except LegacyIsolationScanError:
        raise
    except Exception as exc:
        emit_wa_event("legacy_isolation_scan_failed", error=type(exc).__name__)
        raise LegacyIsolationScanError(
            "Cloud bind scan failed; refusing to treat as empty (fail closed)"
        ) from exc


def assert_no_monty_cloud_dual_bind() -> dict[str, Any]:
    """Fail closed at startup if the same number appears in Monty env and Cloud binding."""

    monty = monty_source_number_digits()
    if not monty:
        return {"ok": True, "overlap": False}
    try:
        cloud = cloud_bound_display_digits()
    except LegacyIsolationScanError as exc:
        emit_wa_event("legacy_isolation_assert_scan_failed", error=type(exc).__name__)
        raise RuntimeError(
            "Fail closed: cannot verify Monty/Cloud isolation (Cloud bind scan failed)."
        ) from exc
    # Compare full digits and last4.
    overlap = False
    if monty in cloud:
        overlap = True
    last4 = monty[-4:] if len(monty) >= 4 else ""
    if last4 and last4 in cloud and any(d.endswith(last4) and len(d) >= 8 for d in cloud):
        overlap = True
    if overlap:
        emit_wa_event("monty_cloud_dual_bind_detected", monty_last4=last4)
        raise RuntimeError(
            "Fail closed: MONTYMOBILE_SOURCE_NUMBER overlaps an active WhatsApp Cloud binding. "
            "Disable legacy Monty for that number before enabling Cloud coexistence."
        )
    return {"ok": True, "overlap": False}


def cloud_blocks_monty_send(to_number: str) -> bool:
    """True when outbound must not use Monty because destination is Cloud-bound display number.

    Outbound from Monty to an arbitrary customer is still legacy; this guard blocks
    Monty from sending *as* a Cloud-bound business number / for Cloud-owned assets.

    On Cloud bind scan failure, returns True (fail closed — block Monty send).
    """

    digits = _normalize_digits(to_number)
    monty = monty_source_number_digits()
    if monty and digits and digits == monty:
        # Sending as the Monty source that is also Cloud-bound is forbidden.
        try:
            cloud = cloud_bound_display_digits()
        except LegacyIsolationScanError:
            return True
        if monty in cloud or (len(monty) >= 4 and monty[-4:] in cloud):
            return True
    return False


def is_phone_number_id_cloud_bound(phone_number_id: str) -> bool:
    if not whatsapp_db_configured():
        return False
    try:
        with whatsapp_session() as session:
            repo = WhatsAppCloudRepository(session)
            return repo.find_active_by_phone_number_id(str(phone_number_id or "").strip()) is not None
    except Exception as exc:
        emit_wa_event("legacy_isolation_pnid_lookup_failed", error=type(exc).__name__)
        raise LegacyIsolationScanError(
            "phone_number_id Cloud bind lookup failed; refusing False (fail closed)"
        ) from exc
