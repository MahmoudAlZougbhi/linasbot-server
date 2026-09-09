"""WhatsApp Cloud bind isolation helpers — fail closed on scan errors."""

from __future__ import annotations

from db.session import whatsapp_db_configured, whatsapp_session
from services.whatsapp_cloud.observability import emit_wa_event
from services.whatsapp_cloud.repository import WhatsAppCloudRepository


class LegacyIsolationScanError(RuntimeError):
    """Cloud bind scan could not complete — callers must fail closed."""


def _normalize_digits(value: str) -> str:
    return "".join(ch for ch in str(value or "") if ch.isdigit())


def cloud_bound_display_digits() -> set[str]:
    """Return active Cloud display digits.

    When WhatsApp DB is not configured, returns empty set (no Cloud binds).
    On DB/scan failure raises LegacyIsolationScanError (fail closed — never empty-on-error).
    """
    if not whatsapp_db_configured():
        return set()
    try:
        with whatsapp_session() as session:
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
        raise LegacyIsolationScanError("Cloud bind scan failed; refusing to treat as empty (fail closed)") from exc


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
