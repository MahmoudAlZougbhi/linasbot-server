"""Sync compiled request graphs after CM publish when the customer DB is present."""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def sync_request_graphs_after_publish(*, tenant_id: str, sections: dict[str, Any]) -> None:
    """Compile request rules into graphs.

    Skip only when this process has no customer DB URL or the graph tables are
    not migrated yet. Other errors propagate so publish does not hide graph failures.
    """
    from sqlalchemy import inspect

    from db.session import WhatsAppDatabaseUnavailable, database_url, whatsapp_session
    from services.request_graphs.service import sync_graphs_from_request_rules

    if not database_url():
        logger.info("request_graph_sync_skipped_no_db tenant_id=%s", tenant_id)
        return
    rules = list((sections.get("requests_appointments") or {}).get("rules") or [])
    try:
        with whatsapp_session(require=True) as db:
            bind = db.get_bind()
            if bind is None or "request_definition_graphs" not in inspect(bind).get_table_names():
                logger.info("request_graph_sync_skipped_unmigrated tenant_id=%s", tenant_id)
                return
            sync_graphs_from_request_rules(db, tenant_id=tenant_id, rules=rules)
    except WhatsAppDatabaseUnavailable:
        logger.info("request_graph_sync_skipped_db_unavailable tenant_id=%s", tenant_id)
        return
