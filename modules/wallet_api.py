"""Token wallet + prepaid package APIs (catalog, checkout, webhook, admin credit)."""

from __future__ import annotations

import hashlib
import json
import os
import threading
import time
from pathlib import Path
from typing import Any

from fastapi import HTTPException, Request, Response
from pydantic import BaseModel, Field

from modules.api_security import require_permission, require_session
from modules.core import app
from services.mail_service import public_app_base_url
from services.stripe_checkout_service import stripe_checkout_service, stripe_configured
from services.token_package_catalog import catalog_public_payload, get_package
from services.token_wallet_service import is_unlimited_tenant, token_wallet_service
from services.wallet_spend_analytics import build_wallet_spend_analytics
from storage.persistent_storage import _DATA_ROOT

_ADMIN_CREDIT_IDEMP_LOCK = threading.RLock()
_ADMIN_CREDIT_IDEMP_DIR = Path(_DATA_ROOT) / "billing" / "admin_credit_idempotency"


class CheckoutRequest(BaseModel):
    package_id: str


class AdminCreditRequest(BaseModel):
    tenant_id: str | None = None
    tokens: int | None = Field(default=None, gt=0)
    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)
    amount_usd: float = 0.0
    reason: str = "admin_credit"
    reference: str | None = None
    idempotency_key: str | None = Field(default=None, min_length=8, max_length=128)


def _admin_credit_allowed(session_tenant: str, session_role: str) -> bool:
    """platform_owner always; otherwise allowlisted/unlimited tenant admins only."""
    role = (session_role or "").strip().lower()
    if role == "platform_owner":
        return True
    if role != "admin":
        return False
    if is_unlimited_tenant(session_tenant):
        return True
    allow = {
        part.strip().lower()
        for part in (os.getenv("TOKEN_WALLET_ADMIN_CREDIT_TENANT_IDS") or "linas").split(",")
        if part.strip()
    }
    return session_tenant.strip().lower() in allow


def _owner_admin_credit_allowed(session_tenant: str, session_role: str) -> bool:
    """Backward-compatible alias for tests/callers."""
    return _admin_credit_allowed(session_tenant, session_role)


def assert_admin_credit_target_allowed(
    *,
    session_tenant: str,
    session_role: str,
    target_tenant: str,
) -> None:
    """Same-tenant for allowlisted admins; cross-tenant only for platform_owner."""
    if not _admin_credit_allowed(session_tenant, session_role):
        raise HTTPException(status_code=403, detail="Admin credit forbidden for this tenant")
    target = (target_tenant or "").strip().lower()
    actor_tenant = (session_tenant or "").strip().lower()
    if not target:
        raise HTTPException(status_code=400, detail="tenant_id required")
    if target != actor_tenant and (session_role or "").strip().lower() != "platform_owner":
        raise HTTPException(status_code=403, detail="Cross-tenant credit forbidden")


def _admin_credit_idempotency_path(key: str) -> Path:
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()[:40]
    return _ADMIN_CREDIT_IDEMP_DIR / f"{digest}.json"


def _load_admin_credit_idempotent(key: str) -> dict[str, Any] | None:
    path = _admin_credit_idempotency_path(key)
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return data if isinstance(data, dict) else None


def _store_admin_credit_idempotent(key: str, payload: dict[str, Any]) -> None:
    _ADMIN_CREDIT_IDEMP_DIR.mkdir(parents=True, exist_ok=True)
    path = _admin_credit_idempotency_path(key)
    with _ADMIN_CREDIT_IDEMP_LOCK:
        path.write_text(
            json.dumps({"idempotency_key": key, "ts": time.time(), "response": payload}),
            encoding="utf-8",
        )


@app.get("/api/billing/packages")
async def list_packages() -> Any:
    """Public catalog of prepaid token packages."""
    return catalog_public_payload()


@app.get("/api/billing/wallet")
async def get_wallet(request: Request) -> Any:
    session = require_session(request)
    snap = token_wallet_service.get_wallet(session.tenant_id)
    ledger = token_wallet_service.recent_ledger(session.tenant_id, limit=40)
    catalog = catalog_public_payload()
    return {
        "success": True,
        "wallet": snap.to_public_dict(),
        "ledger": ledger,
        "stripe_configured": stripe_configured(),
        "packages": catalog["packages"],
        "summary": catalog.get("summary"),
        "interaction_logs_path": "/activity-flow",
    }


@app.get("/api/billing/wallet/analytics")
async def get_wallet_analytics(request: Request) -> Any:
    """Spend analytics from Interaction Logs (FB/IG/Testing Lab + top chats)."""
    session = require_session(request)
    return build_wallet_spend_analytics(session.tenant_id)


@app.post("/api/billing/checkout")
async def create_checkout(body: CheckoutRequest, request: Request) -> Any:
    session = require_session(request)
    if is_unlimited_tenant(session.tenant_id):
        return {
            "success": False,
            "error": "This workspace has unlimited AI usage and does not need token packs.",
        }
    pack = get_package(body.package_id)
    if pack is None:
        raise HTTPException(status_code=404, detail="Unknown package")
    if not stripe_configured():
        return {
            "success": False,
            "error": "Card checkout is not enabled yet. Configure STRIPE_SECRET_KEY on the server, or ask an owner to credit tokens.",
            "stripe_configured": False,
            "package": pack.to_public_dict(),
        }
    base = public_app_base_url()
    try:
        session_out = stripe_checkout_service.create_checkout_session(
            tenant_id=session.tenant_id,
            package_id=pack.id,
            tokens=pack.tokens,
            input_tokens=pack.input_tokens,
            output_tokens=pack.output_tokens,
            amount_usd=pack.sell_price_usd,
            success_url=f"{base}/wallet?checkout=success",
            cancel_url=f"{base}/wallet?checkout=cancel",
            customer_email=session.email,
        )
    except Exception as exc:
        print(f"[wallet_api] checkout error: {exc}", flush=True)
        return {"success": False, "error": "Unable to start checkout"}
    return {
        "success": True,
        "checkout_url": session_out.get("url"),
        "session_id": session_out.get("id"),
        "package": pack.to_public_dict(),
    }


@app.post("/api/billing/admin-credit")
async def admin_credit(body: AdminCreditRequest, request: Request) -> Any:
    session = require_permission(request, "settings")
    target = (body.tenant_id or session.tenant_id).strip().lower()
    assert_admin_credit_target_allowed(
        session_tenant=session.tenant_id,
        session_role=session.role,
        target_tenant=target,
    )

    idem_key = (body.idempotency_key or body.reference or "").strip() or None
    if idem_key:
        cached = _load_admin_credit_idempotent(idem_key)
        if cached and isinstance(cached.get("response"), dict):
            out = dict(cached["response"])
            out["duplicate"] = True
            return out

    reason = body.reason or "admin_credit"
    amount_usd = float(body.amount_usd or 0.0)
    before = token_wallet_service.get_wallet(target)
    snap = token_wallet_service.credit(
        target,
        tokens=int(body.tokens) if body.tokens is not None else None,
        input_tokens=body.input_tokens,
        output_tokens=body.output_tokens,
        amount_usd=amount_usd,
        reason=reason,
        reference=body.reference,
        actor=session.user_id,
    )
    audit = {
        "actor": session.user_id,
        "tenant_id": target,
        "amount_usd": amount_usd,
        "reason": reason,
        "reference": body.reference,
        "before": {
            "input_remaining": before.input_remaining,
            "output_remaining": before.output_remaining,
            "balance_tokens": before.balance_tokens,
        },
        "after": {
            "input_remaining": snap.input_remaining,
            "output_remaining": snap.output_remaining,
            "balance_tokens": snap.balance_tokens,
        },
    }
    payload = {"success": True, "wallet": snap.to_public_dict(), "audit": audit, "duplicate": False}
    if idem_key:
        _store_admin_credit_idempotent(idem_key, payload)
    return payload


@app.post("/api/billing/stripe/webhook")
async def stripe_webhook(request: Request) -> Any:
    """Stripe webhook — credits wallet on verified checkout.session.completed."""
    payload = await request.body()
    sig = request.headers.get("stripe-signature")
    try:
        event = stripe_checkout_service.construct_event(payload, sig)
    except Exception as exc:
        print(f"[wallet_api] stripe webhook reject: {type(exc).__name__}", flush=True)
        raise HTTPException(status_code=400, detail="Invalid webhook") from exc

    event_id = str(event.get("id") or "")
    if not event_id:
        raise HTTPException(status_code=400, detail="Missing event id")
    if stripe_checkout_service.already_processed(event_id):
        return {"success": True, "duplicate": True}

    etype = str(event.get("type") or "")
    data_object = (event.get("data") or {}).get("object") or {}
    if etype == "checkout.session.completed":
        metadata = data_object.get("metadata") or {}
        if str(metadata.get("product") or "") != "linas_token_pack":
            stripe_checkout_service.mark_processed(event_id, {"skipped": "not_token_pack"})
            return {"success": True, "skipped": True}
        payment_status = str(data_object.get("payment_status") or "")
        if payment_status and payment_status != "paid":
            # Wait for paid; do not credit unpaid sessions.
            return Response(status_code=200, content='{"success":true,"pending":true}')
        tenant_id = str(metadata.get("tenant_id") or "").strip().lower()
        package_id = str(metadata.get("package_id") or "")
        try:
            input_tokens = int(metadata.get("input_tokens") or 0)
        except ValueError:
            input_tokens = 0
        try:
            output_tokens = int(metadata.get("output_tokens") or 0)
        except ValueError:
            output_tokens = 0
        try:
            tokens = int(metadata.get("tokens") or 0)
        except ValueError:
            tokens = 0
        try:
            amount_usd = float(metadata.get("amount_usd") or 0)
        except ValueError:
            amount_usd = 0.0
        # Prefer explicit dual allotments; fall back to package catalog; then legacy total.
        if input_tokens <= 0 or output_tokens <= 0:
            pack = get_package(package_id) if package_id else None
            if pack is not None:
                input_tokens = pack.input_tokens
                output_tokens = pack.output_tokens
        if (input_tokens <= 0 or output_tokens <= 0) and tokens > 0:
            # Legacy Stripe metadata without dual fields — split once.
            input_tokens = int(round(tokens * 0.80))
            output_tokens = max(0, tokens - input_tokens)
        if not tenant_id or (input_tokens <= 0 and output_tokens <= 0):
            raise HTTPException(status_code=400, detail="Invalid metadata")
        token_wallet_service.credit(
            tenant_id,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            amount_usd=amount_usd,
            reason="stripe_checkout",
            reference=str(data_object.get("id") or event_id),
            package_id=package_id or None,
            actor="stripe",
        )
        stripe_checkout_service.mark_processed(
            event_id,
            {
                "tenant_id": tenant_id,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "package_id": package_id,
            },
        )
        return {"success": True, "credited": True}

    stripe_checkout_service.mark_processed(event_id, {"type": etype})
    return {"success": True, "ignored": True}
