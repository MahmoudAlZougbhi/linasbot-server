"""Stripe billing webhook (token-pack checkout.session.completed)."""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException, Request, Response

from modules.core import app
from services.stripe_checkout_service import stripe_checkout_service
from services.token_package_catalog import get_package
from services.token_wallet_service import token_wallet_service


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
        from services.membership.iap_message_grant import (
            apply_verified_stripe_message_checkout,
            stripe_checkout_kind,
        )

        kind = stripe_checkout_kind(metadata)
        if kind == "message_pack":
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
        if kind != "token_pack":
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
