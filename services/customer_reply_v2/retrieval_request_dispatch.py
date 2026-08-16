"""Luna tools for compiled request definition graphs (tenant-scoped)."""

from __future__ import annotations

from typing import Any

REQUEST_GRAPH_TOOL_NAMES = {"list_request_definitions", "get_request_definition", "list_open_drafts"}


def dispatch_request_graph_tool(name: str, args: dict[str, Any], ctx: Any) -> dict[str, Any]:
    from db.session import WhatsAppDatabaseUnavailable, database_url, whatsapp_session
    from services.request_graphs.service import get_active_graph, list_active_graphs

    if not database_url():
        ctx.audit.append({"tool": name, "ok": False, "class": "db_unavailable"})
        return {"ok": False, "error": "db_unavailable"}
    try:
        with whatsapp_session(require=True) as db:
            if name == "list_open_drafts":
                from services.request_drafts.engine import luna_draft_summary
                from services.request_drafts.repository import DraftRepository

                draft_rows = DraftRepository(db).list_open(
                    tenant_id=ctx.tenant_id, customer_id=str(ctx.customer_id or "")
                )
                summaries = [luna_draft_summary(row) for row in draft_rows]
                ctx.audit.append({"tool": name, "ok": True, "class": "open_drafts", "count": len(summaries)})
                return {"ok": True, "data": {"drafts": summaries}}
            if name == "list_request_definitions":
                graphs = list_active_graphs(db, tenant_id=ctx.tenant_id)
                titles = [
                    {
                        "definition_id": row.get("definition_id"),
                        "title": row.get("title"),
                        "destination": row.get("destination"),
                        "revision": row.get("revision"),
                        "source_item_id": row.get("source_item_id"),
                        "status": row.get("status"),
                    }
                    for row in graphs
                ]
                ctx.audit.append({"tool": name, "ok": True, "class": "request_definitions", "count": len(titles)})
                return {"ok": True, "data": {"definitions": titles}}
            definition_id = str(args.get("definition_id") or "").strip()
            source_item_id = str(args.get("source_item_id") or "").strip()
            graph = get_active_graph(
                db,
                tenant_id=ctx.tenant_id,
                definition_id=definition_id,
                source_item_id=source_item_id,
            )
            if graph is None:
                ctx.audit.append({"tool": name, "ok": False, "class": "not_found"})
                return {"ok": False, "error": "not_found"}
            ctx.audit.append({"tool": name, "ok": True, "class": "request_definition"})
            return {"ok": True, "data": {"graph": graph}}
    except WhatsAppDatabaseUnavailable:
        ctx.audit.append({"tool": name, "ok": False, "class": "db_unavailable"})
        return {"ok": False, "error": "db_unavailable"}


def compiled_graph_content(*, tenant_id: str, source_item_id: str, fallback: str) -> str:
    """Return compiled graph JSON for a selected request rule, or the published notes."""
    import json

    from db.session import WhatsAppDatabaseUnavailable, database_url, whatsapp_session
    from services.request_graphs.service import get_active_graph

    if not source_item_id or not database_url():
        return fallback
    try:
        with whatsapp_session(require=True) as db:
            graph = get_active_graph(db, tenant_id=tenant_id, source_item_id=source_item_id)
            if not graph:
                return fallback
            return json.dumps(graph, ensure_ascii=False)
    except WhatsAppDatabaseUnavailable:
        return fallback
