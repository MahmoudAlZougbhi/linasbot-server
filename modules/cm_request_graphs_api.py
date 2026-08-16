"""Request definition graph preview/publish APIs (session tenant only)."""

from __future__ import annotations

from typing import Any

from fastapi import Body, HTTPException, Request

from modules.api_security import require_session
from modules.core import app
from services.request_graphs.service import delete_graph, list_active_graphs, preview_graph, publish_graph


@app.post("/api/cm/request-graphs/preview")
async def request_graph_preview(request: Request, body: dict[str, Any] = Body(default={})) -> Any:
    session = require_session(request)
    _ = session.tenant_id
    preview = preview_graph(
        title=str(body.get("title") or ""),
        source_text=str(body.get("source_text") or ""),
        destination=str(body.get("destination") or "appointment"),
        linked_entities=list(body.get("linked_entities") or []),
    )
    return {"success": True, "preview": preview}


@app.post("/api/cm/request-graphs/publish")
async def request_graph_publish(request: Request, body: dict[str, Any] = Body(default={})) -> Any:
    session = require_session(request)
    from db.session import whatsapp_session

    source_item_id = str(body.get("source_item_id") or "").strip()
    if not source_item_id:
        raise HTTPException(status_code=400, detail="source_item_id_required")
    try:
        with whatsapp_session(require=True) as db:
            result = publish_graph(
                db,
                tenant_id=session.tenant_id,
                source_item_id=source_item_id,
                title=str(body.get("title") or ""),
                source_text=str(body.get("source_text") or ""),
                destination=str(body.get("destination") or "appointment"),
                linked_entities=list(body.get("linked_entities") or []),
                confirm=bool(body.get("confirm")),
            )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=type(exc).__name__) from exc
    return {"success": True, "graph": result}


@app.get("/api/cm/request-graphs")
async def request_graph_list(request: Request) -> Any:
    session = require_session(request)
    from db.session import whatsapp_session

    with whatsapp_session(require=True) as db:
        rows = list_active_graphs(db, tenant_id=session.tenant_id)
    return {"success": True, "graphs": rows}


@app.post("/api/cm/request-graphs/delete")
async def request_graph_delete(request: Request, body: dict[str, Any] = Body(default={})) -> Any:
    session = require_session(request)
    from db.session import whatsapp_session

    definition_id = str(body.get("definition_id") or "").strip()
    if not definition_id:
        raise HTTPException(status_code=400, detail="definition_id_required")
    with whatsapp_session(require=True) as db:
        result = delete_graph(db, tenant_id=session.tenant_id, definition_id=definition_id)
    return {"success": True, **result}
