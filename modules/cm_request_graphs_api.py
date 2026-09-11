"""Request definition graph preview/publish APIs (session tenant only)."""

from __future__ import annotations

from typing import Any

from fastapi import Body, HTTPException, Request
from fastapi.responses import JSONResponse

from modules.api_security import require_permission, require_session
from modules.core import app
from services.cm.storage import ConflictError
from services.request_graphs.cm_sync import DraftMatchRequired, delete_with_optional_draft, publish_with_optional_draft
from services.request_graphs.db_guard import RequestGraphsDbError, request_graphs_session
from services.request_graphs.service import list_active_graphs, preview_graph


def _http_db(exc: RequestGraphsDbError) -> HTTPException:
    return HTTPException(status_code=503, detail={"code": exc.code, "message": exc.message})


def _actor(session: Any) -> str:
    return str(getattr(session, "user_id", None) or getattr(session, "email", None) or "unknown")


def _conflict(exc: ConflictError) -> JSONResponse:
    current = exc.current
    etag = str(getattr(current, "etag", "") or "")
    return JSONResponse(
        status_code=409,
        content={
            "success": False,
            "error": "CONFLICT",
            "message": exc.message,
            "current_etag": etag or None,
        },
        headers={"ETag": etag} if etag else {},
    )


@app.post("/api/cm/request-graphs/preview")
async def request_graph_preview(request: Request, body: dict[str, Any] = Body(default={})) -> Any:
    session = require_session(request)
    from services.membership.daily_edits import DailyEditLimitError
    from services.membership.edit_http import guarded_edit, limit_response

    try:
        with guarded_edit(tenant_id=session.tenant_id, kind="request-graph:preview", payload=body):
            preview = preview_graph(
                title=str(body.get("title") or ""),
                source_text=str(body.get("source_text") or ""),
                destination=str(body.get("destination") or "appointment"),
                linked_entities=list(body.get("linked_entities") or []),
            )
    except DailyEditLimitError as exc:
        return limit_response(exc)
    return {"success": True, "preview": preview}


@app.post("/api/cm/request-graphs/publish")
async def request_graph_publish(request: Request, body: dict[str, Any] = Body(default={})) -> Any:
    session = require_permission(request, "contentManagers")
    source_item_id = str(body.get("source_item_id") or "").strip()
    if not source_item_id:
        raise HTTPException(
            status_code=400,
            detail={"code": "source_item_id_required", "message": "source_item_id_required"},
        )
    from services.membership.daily_edits import DailyEditLimitError
    from services.membership.edit_http import guarded_edit, limit_response

    try:
        with guarded_edit(tenant_id=session.tenant_id, kind="request-graph:publish", payload=body):
            with request_graphs_session() as db:
                result = publish_with_optional_draft(
                    db,
                    tenant_id=session.tenant_id,
                    body=body,
                    updated_by=_actor(session),
                )
    except DailyEditLimitError as exc:
        return limit_response(exc)
    except DraftMatchRequired as exc:
        raise HTTPException(status_code=428, detail={"code": exc.code, "message": str(exc)}) from exc
    except ConflictError as exc:
        return _conflict(exc)
    except RequestGraphsDbError as exc:
        raise _http_db(exc) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail={"code": "REQUEST_GRAPH_PUBLISH_INVALID", "message": str(exc) or type(exc).__name__},
        ) from exc
    return {"success": True, **result}


@app.get("/api/cm/request-graphs")
async def request_graph_list(request: Request) -> Any:
    session = require_session(request)
    try:
        with request_graphs_session() as db:
            rows = list_active_graphs(db, tenant_id=session.tenant_id)
    except RequestGraphsDbError as exc:
        raise _http_db(exc) from exc
    return {"success": True, "graphs": rows}


@app.post("/api/cm/request-graphs/delete")
async def request_graph_delete(request: Request, body: dict[str, Any] = Body(default={})) -> Any:
    session = require_permission(request, "contentManagers")
    definition_id = str(body.get("definition_id") or "").strip()
    if not definition_id:
        raise HTTPException(
            status_code=400,
            detail={"code": "definition_id_required", "message": "definition_id_required"},
        )
    from services.membership.daily_edits import DailyEditLimitError
    from services.membership.edit_http import guarded_edit, limit_response

    try:
        with guarded_edit(tenant_id=session.tenant_id, kind="request-graph:delete", payload=body):
            with request_graphs_session() as db:
                result = delete_with_optional_draft(
                    db,
                    tenant_id=session.tenant_id,
                    body=body,
                    updated_by=_actor(session),
                )
    except DailyEditLimitError as exc:
        return limit_response(exc)
    except DraftMatchRequired as exc:
        raise HTTPException(status_code=428, detail={"code": exc.code, "message": str(exc)}) from exc
    except ConflictError as exc:
        return _conflict(exc)
    except RequestGraphsDbError as exc:
        raise _http_db(exc) from exc
    return {"success": True, **result}
