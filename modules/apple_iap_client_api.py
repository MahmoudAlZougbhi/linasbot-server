"""Authenticated Apple IAP client endpoints (verify / restore / token / reconcile)."""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException, Request
from pydantic import BaseModel, Field

from modules.api_security import is_platform_owner, require_session
from modules.core import app
from services.apple_app_store_client import AppleIapConfigError, iap_credentials_configured
from services.apple_iap_effects import get_or_create_app_account_token
from services.apple_iap_processor import (
    AppleIapProcessorError,
    process_signed_transaction,
    reconcile_original_transaction,
)
from services.apple_jws import AppleJwsError
from services.apple_transaction_ledger import get_by_transaction_id


class VerifyBody(BaseModel):
    signed_transaction: str = Field(min_length=20)
    app_account_token: str | None = None


class RestoreBody(BaseModel):
    signed_transactions: list[str] = Field(min_length=1)


class ReconcileBody(BaseModel):
    original_transaction_id: str = Field(min_length=4)


@app.post("/api/entitlements/apple/verify")
async def apple_verify_transaction(body: VerifyBody, request: Request) -> Any:
    session = require_session(request)
    if not iap_credentials_configured():
        raise HTTPException(status_code=503, detail="Apple IAP credentials not configured")
    # Ensure durable appAccountToken exists for this session before verifying.
    expected_token = get_or_create_app_account_token(tenant_id=session.tenant_id, user_id=session.user_id)
    if body.app_account_token and body.app_account_token.strip() != expected_token:
        raise HTTPException(status_code=403, detail="app_account_token mismatch")
    try:
        result = process_signed_transaction(
            signed_transaction_jws=body.signed_transaction,
            tenant_id=session.tenant_id,
            user_id=session.user_id,
            source="client_verify",
        )
    except AppleJwsError as exc:
        raise HTTPException(status_code=401, detail="Invalid Apple signature") from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except (AppleIapProcessorError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"success": True, **result}


@app.post("/api/entitlements/apple/restore")
async def apple_restore_transactions(body: RestoreBody, request: Request) -> Any:
    session = require_session(request)
    if not iap_credentials_configured():
        raise HTTPException(status_code=503, detail="Apple IAP credentials not configured")
    results: list[dict[str, Any]] = []
    for raw in body.signed_transactions:
        try:
            results.append(
                process_signed_transaction(
                    signed_transaction_jws=str(raw),
                    tenant_id=session.tenant_id,
                    user_id=session.user_id,
                    source="client_restore",
                )
            )
        except (AppleJwsError, PermissionError, AppleIapProcessorError, ValueError) as exc:
            results.append({"ok": False, "error": str(exc)})
    return {"success": True, "results": results}


@app.get("/api/entitlements/apple/app-account-token")
async def apple_app_account_token(request: Request) -> Any:
    session = require_session(request)
    token = get_or_create_app_account_token(tenant_id=session.tenant_id, user_id=session.user_id)
    return {"success": True, "app_account_token": token}


@app.post("/api/entitlements/apple/reconcile")
async def apple_reconcile(body: ReconcileBody, request: Request) -> Any:
    session = require_session(request)
    oid = body.original_transaction_id.strip()
    if not is_platform_owner(session):
        row = get_by_transaction_id(oid)
        owned = False
        if row is not None and row.tenant_id == session.tenant_id:
            owned = True
        if not owned:
            from services.apple_transaction_ledger import list_by_original_transaction_id

            rows = list_by_original_transaction_id(oid)
            owned = any(r.tenant_id == session.tenant_id for r in rows)
        if not owned:
            raise HTTPException(status_code=403, detail="original_transaction_id not owned by tenant")
    try:
        result = reconcile_original_transaction(oid)
    except AppleIapConfigError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail="Reconcile failed") from exc
    return {"success": True, **result}
