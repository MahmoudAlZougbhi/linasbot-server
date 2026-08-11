"""PostgreSQL access for platform domains that use SQLAlchemy as SoT."""

from __future__ import annotations

from db.session import (
    WhatsAppDatabaseUnavailable,
    database_url,
    get_engine,
    ping_whatsapp_db,
    reset_engine_for_tests,
    whatsapp_db_configured,
    whatsapp_session,
)

__all__ = [
    "WhatsAppDatabaseUnavailable",
    "database_url",
    "get_engine",
    "ping_whatsapp_db",
    "reset_engine_for_tests",
    "whatsapp_db_configured",
    "whatsapp_session",
]
