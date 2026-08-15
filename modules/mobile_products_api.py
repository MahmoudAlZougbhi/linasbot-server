"""Mobile AI Products CRUD + CSV import."""

from __future__ import annotations

from typing import Any

from fastapi import Body, HTTPException, Query, Request

from db.session import WhatsAppDatabaseUnavailable, whatsapp_session
from modules.api_security import require_session
from modules.core import app
from services.dashboard_session_service import SessionRecord
from services.products.media import delete_product_media
from services.products.schemas import ProductImportBody, ProductWriteBody
from services.products.service import ProductsError, ProductsService


def _session_tenant(session: SessionRecord) -> str:
    tenant_id = str(session.tenant_id or "").strip()
    if not tenant_id:
        raise HTTPException(status_code=403, detail="Tenant context required")
    return tenant_id


def _http(exc: ProductsError) -> HTTPException:
    return HTTPException(status_code=exc.http_status, detail={"code": exc.code, "message": exc.message})


def _db_session():
    try:
        return whatsapp_session()
    except WhatsAppDatabaseUnavailable as exc:
        raise HTTPException(
            status_code=503,
            detail={"code": "PRODUCTS_DB_UNAVAILABLE", "message": str(exc)},
        ) from exc


@app.get("/api/mobile/products")
async def mobile_list_products(
    request: Request,
    limit: int = Query(default=200, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> Any:
    session = require_session(request)
    tenant_id = _session_tenant(session)
    with _db_session() as db:
        svc = ProductsService(db)
        payload = svc.list_products(tenant_id=tenant_id, limit=limit, offset=offset)
    return {"success": True, **payload}


@app.post("/api/mobile/products")
async def mobile_create_product(request: Request, body: ProductWriteBody) -> Any:
    session = require_session(request)
    tenant_id = _session_tenant(session)
    with _db_session() as db:
        svc = ProductsService(db)
        try:
            product = svc.create_product(tenant_id=tenant_id, body=body)
        except ProductsError as exc:
            raise _http(exc) from exc
    return {"success": True, "product": product}


@app.get("/api/mobile/products/{product_id}")
async def mobile_get_product(product_id: str, request: Request) -> Any:
    session = require_session(request)
    tenant_id = _session_tenant(session)
    with _db_session() as db:
        svc = ProductsService(db)
        try:
            product = svc.get_product(tenant_id=tenant_id, product_id=product_id)
        except ProductsError as exc:
            raise _http(exc) from exc
    return {"success": True, "product": product}


@app.put("/api/mobile/products/{product_id}")
async def mobile_update_product(
    product_id: str,
    request: Request,
    body: ProductWriteBody,
) -> Any:
    session = require_session(request)
    tenant_id = _session_tenant(session)
    with _db_session() as db:
        svc = ProductsService(db)
        try:
            product = svc.update_product(tenant_id=tenant_id, product_id=product_id, body=body)
        except ProductsError as exc:
            raise _http(exc) from exc
    return {"success": True, "product": product}


@app.delete("/api/mobile/products/{product_id}")
async def mobile_delete_product(product_id: str, request: Request) -> Any:
    session = require_session(request)
    tenant_id = _session_tenant(session)
    with _db_session() as db:
        svc = ProductsService(db)
        try:
            media_ids = svc.delete_product(tenant_id=tenant_id, product_id=product_id)
        except ProductsError as exc:
            raise _http(exc) from exc
    for media_id in media_ids:
        delete_product_media(tenant_id=tenant_id, media_id=media_id)
    return {"success": True, "deleted": True, "product_id": product_id}


@app.post("/api/mobile/products/import")
async def mobile_import_products(request: Request, body: ProductImportBody) -> Any:
    session = require_session(request)
    tenant_id = _session_tenant(session)
    with _db_session() as db:
        svc = ProductsService(db)
        try:
            result = svc.import_csv(tenant_id=tenant_id, csv_text=body.csv_text)
        except ProductsError as exc:
            raise _http(exc) from exc
    return {"success": True, **result}
