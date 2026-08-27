"""PostgreSQL is required for WhatsApp SoT — no silent file fallback."""

from __future__ import annotations

import pytest

from db.session import WhatsAppDatabaseUnavailable, get_engine, reset_engine_for_tests
from services.scale.retry_backoff import retry_delay_seconds


def test_missing_database_url_fails_closed(monkeypatch) -> None:
    monkeypatch.delenv("LINAS_WHATSAPP_DATABASE_URL", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    reset_engine_for_tests()
    with pytest.raises(WhatsAppDatabaseUnavailable):
        get_engine(require=True)


def test_postgres_disconnect_does_not_retry_storm() -> None:
    first = retry_delay_seconds(attempts=1, error="psycopg OperationalError: connection refused")
    second = retry_delay_seconds(attempts=4, error="server closed the connection")
    assert first >= 5.0
    assert second >= 5.0
    assert second <= 30.0
