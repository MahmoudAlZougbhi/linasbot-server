"""Mobile tenant services CRUD — priced service options."""

from __future__ import annotations

from contextlib import AbstractContextManager
from typing import Any

from fastapi import HTTPException, Query, Request
from sqlalchemy.orm import Session

from db.session import WhatsAppDatabaseUnavailable, whatsapp_session
from modules.api_security import require_session
from modules.core import app
from services.dashboard_session_service import SessionRecord
from services.service_catalog.catalog_service import ServiceCatalogError, ServiceCatalogService
from services.service_catalog.schemas import ServiceWriteBody


def _session_tenant(session: SessionRecord) -> str:
    tenant_id = str(session.tenant_id or "").strip()
    if not tenant_id:
        raise HTTPException(status_code=403, detail="Tenant context required")
    return tenant_id


def _http(exc: ServiceCatalogError) -> HTTPException:
    return HTTPException(status_code=exc.http_status, detail={"code": exc.code, "message": exc.message})


def _db_session() -> AbstractContextManager[Session]:
    try:
        return whatsapp_session()
    except WhatsAppDatabaseUnavailable as exc:
        raise HTTPException(
            status_code=503,
            detail={"code": "SERVICES_DB_UNAVAILABLE", "message": str(exc)},
        ) from exc


@app.get("/api/mobile/services")
async def mobile_list_services(
    request: Request,
    limit: int = Query(default=200, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> Any:
    session = require_session(request)
    tenant_id = _session_tenant(session)
    with _db_session() as db:
        svc = ServiceCatalogService(db)
        payload = svc.list_services(tenant_id=tenant_id, limit=limit, offset=offset)
    return {"success": True, **payload}


@app.post("/api/mobile/services")
async def mobile_create_service(request: Request, body: ServiceWriteBody) -> Any:
    session = require_session(request)
    tenant_id = _session_tenant(session)
    with _db_session() as db:
        svc = ServiceCatalogService(db)
        try:
            service = svc.create_service(tenant_id=tenant_id, body=body)
        except ServiceCatalogError as exc:
            raise _http(exc) from exc
    return {"success": True, "service": service}


@app.get("/api/mobile/services/{service_id}")
async def mobile_get_service(service_id: str, request: Request) -> Any:
    session = require_session(request)
    tenant_id = _session_tenant(session)
    with _db_session() as db:
        svc = ServiceCatalogService(db)
        try:
            service = svc.get_service(tenant_id=tenant_id, service_id=service_id)
        except ServiceCatalogError as exc:
            raise _http(exc) from exc
    return {"success": True, "service": service}


@app.put("/api/mobile/services/{service_id}")
async def mobile_update_service(
    service_id: str,
    request: Request,
    body: ServiceWriteBody,
) -> Any:
    session = require_session(request)
    tenant_id = _session_tenant(session)
    with _db_session() as db:
        svc = ServiceCatalogService(db)
        try:
            service = svc.update_service(tenant_id=tenant_id, service_id=service_id, body=body)
        except ServiceCatalogError as exc:
            raise _http(exc) from exc
    return {"success": True, "service": service}


@app.delete("/api/mobile/services/{service_id}")
async def mobile_delete_service(service_id: str, request: Request) -> Any:
    session = require_session(request)
    tenant_id = _session_tenant(session)
    with _db_session() as db:
        svc = ServiceCatalogService(db)
        try:
            svc.delete_service(tenant_id=tenant_id, service_id=service_id)
        except ServiceCatalogError as exc:
            raise _http(exc) from exc
    return {"success": True, "deleted": True, "service_id": service_id}
