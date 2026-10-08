"""Shared Voyage error counts. Both app hosts read the same Postgres rows."""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import text

logger = logging.getLogger(__name__)

_ALERT_IN_5_MIN = 10
_MEMORY: list[tuple[str, int, datetime]] = []
_ENSURED = False


def reset_metrics_for_tests() -> None:
    global _ENSURED
    _MEMORY.clear()
    _ENSURED = False


def _ensure(session: object) -> None:
    global _ENSURED
    if _ENSURED:
        return
    session.execute(  # type: ignore[attr-defined]
        text(
            """
            CREATE TABLE IF NOT EXISTS owner_portal_voyage_events (
                id BIGSERIAL PRIMARY KEY,
                feature TEXT NOT NULL,
                status INTEGER NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
            """
        )
    )
    _ENSURED = True


def note_voyage(feature: str, status: int, *, retry_after: str = "") -> None:
    code = int(status or 0)
    name = (feature or "unknown").strip() or "unknown"
    if code != 429 and code < 500:
        return
    logger.warning("voyage_http feature=%s status=%s retry_after=%s", name, code, retry_after or "-")
    now = datetime.now(UTC)
    _MEMORY.append((name, code, now))
    try:
        from db.session import whatsapp_session

        with whatsapp_session(require=False) as session:
            if session is None:
                return
            _ensure(session)
            session.execute(
                text(
                    """
                    INSERT INTO owner_portal_voyage_events (feature, status, created_at)
                    VALUES (:feature, :status, :created)
                    """
                ),
                {"feature": name, "status": code, "created": now},
            )
            session.commit()
    except Exception:
        logger.debug("voyage metric stayed in memory", exc_info=True)
    if recent_count(seconds=300) >= _ALERT_IN_5_MIN:
        logger.warning(
            "voyage_429_alert window=5m count=%s watch log line voyage_http",
            recent_count(seconds=300),
        )


def recent_count(*, feature: str = "", seconds: int = 300) -> int:
    cutoff = datetime.now(UTC) - timedelta(seconds=max(1, seconds))
    try:
        from db.session import whatsapp_session

        with whatsapp_session(require=False) as session:
            if session is not None:
                _ensure(session)
                params: dict[str, object] = {"cutoff": cutoff}
                sql = "SELECT COUNT(*) FROM owner_portal_voyage_events WHERE created_at >= :cutoff"
                if feature:
                    sql += " AND feature = :feature"
                    params["feature"] = feature
                return int(session.execute(text(sql), params).scalar() or 0)
    except Exception:
        pass
    return sum(1 for name, _status, when in _MEMORY if when >= cutoff and (not feature or name == feature))
