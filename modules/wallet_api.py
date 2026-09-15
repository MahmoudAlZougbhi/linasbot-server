"""Stripe billing webhook. Live grants go to the credit ledger, not token wallets."""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException, Request, Response

from modules.core import app
from services.stripe_checkout_service import stripe_checkout_service


@app.post("/api/billing/stripe/webhook")
async def stripe_webhook(request: Request) -> Any:
    """Stripe webhook — credit-ledger grants on verified checkout.session.completed."""
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
        from services.billing.membership.iap_message_grant import (
            apply_verified_stripe_message_checkout,
            stripe_checkout_kind,
        )

        kind = stripe_checkout_kind(metadata)
        if kind == "token_pack":
            stripe_checkout_service.mark_processed(event_id, {"skipped": "token_pack_retired"})
            return {"success": True, "skipped": True, "reason": "token_pack_retired"}
        if kind != "message_pack":
            stripe_checkout_service.mark_processed(event_id, {"skipped": "not_message_pack"})
            return {"success": True, "skipped": True}
        payment_status = str(data_object.get("payment_status") or "")
        if payment_status and payment_status != "paid":
            return Response(status_code=200, content='{"success":true,"pending":true}')
        tenant_id = str(metadata.get("tenant_id") or "").strip().lower()
        product_id = str(metadata.get("package_id") or metadata.get("product_id") or "")
        if not tenant_id:
            raise HTTPException(status_code=400, detail="Invalid metadata")
        grant = apply_verified_stripe_message_checkout(
            tenant_id=tenant_id,
            product_id=product_id,
            transaction_id=str(data_object.get("id") or event_id),
        )
        stripe_checkout_service.mark_processed(event_id, {"kind": "message_pack", **grant})
        return {"success": True, "message_grant": grant}

    stripe_checkout_service.mark_processed(event_id, {"type": etype})
    return {"success": True, "ignored": True}
