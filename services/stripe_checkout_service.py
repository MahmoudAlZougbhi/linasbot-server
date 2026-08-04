"""Stripe Checkout for prepaid token packages (env-gated).

When STRIPE_SECRET_KEY is unset, checkout endpoints report payments unavailable —
no fake charges. Webhook credits wallet only after verified ``checkout.session.completed``.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import threading
import time
from pathlib import Path
from typing import Any

from storage.persistent_storage import _DATA_ROOT

logger = logging.getLogger(__name__)


def stripe_configured() -> bool:
    return bool((os.getenv("STRIPE_SECRET_KEY") or "").strip())


def stripe_webhook_secret() -> str:
    return (os.getenv("STRIPE_WEBHOOK_SECRET") or "").strip()


class StripeCheckoutService:
    def __init__(self, processed_dir: Path | None = None) -> None:
        self._lock = threading.RLock()
        self._processed_dir = processed_dir or (Path(_DATA_ROOT) / "billing" / "stripe_events")
        self._processed_dir.mkdir(parents=True, exist_ok=True)

    def _event_path(self, event_id: str) -> Path:
        digest = hashlib.sha256(event_id.encode("utf-8")).hexdigest()[:32]
        return self._processed_dir / f"{digest}.json"

    def already_processed(self, event_id: str) -> bool:
        return self._event_path(event_id).exists()

    def mark_processed(self, event_id: str, payload: dict[str, Any]) -> None:
        path = self._event_path(event_id)
        with self._lock:
            path.write_text(
                json.dumps({"event_id": event_id, "ts": time.time(), "meta": payload}),
                encoding="utf-8",
            )

    def create_checkout_session(
        self,
        *,
        tenant_id: str,
        package_id: str,
        tokens: int,
        amount_usd: float,
        success_url: str,
        cancel_url: str,
        customer_email: str | None = None,
        input_tokens: int | None = None,
        output_tokens: int | None = None,
    ) -> dict[str, Any]:
        secret = (os.getenv("STRIPE_SECRET_KEY") or "").strip()
        if not secret:
            raise RuntimeError("Stripe is not configured (set STRIPE_SECRET_KEY)")

        try:
            import stripe  # type: ignore
        except ImportError as exc:
            raise RuntimeError("stripe package not installed") from exc

        stripe.api_key = secret
        amount_cents = int(round(float(amount_usd) * 100))
        if amount_cents < 50:
            # Stripe minimum is typically $0.50 — packs should be above this.
            raise ValueError("Package price below Stripe minimum charge")

        inn = int(input_tokens or 0)
        out = int(output_tokens or 0)
        if inn > 0 and out > 0:
            product_name = f"Linas AI pack ({inn:,} input + {out:,} output)"
            product_desc = f"Prepaid input and output AI tokens for tenant {tenant_id}"
        else:
            product_name = f"Linas AI token pack ({tokens:,} tokens)"
            product_desc = f"Prepaid AI tokens for tenant {tenant_id}"

        create_kwargs: dict[str, Any] = {
            "mode": "payment",
            "success_url": success_url,
            "cancel_url": cancel_url,
            "line_items": [
                {
                    "quantity": 1,
                    "price_data": {
                        "currency": "usd",
                        "unit_amount": amount_cents,
                        "product_data": {
                            "name": product_name,
                            "description": product_desc,
                        },
                    },
                }
            ],
            "metadata": {
                "tenant_id": tenant_id,
                "package_id": package_id,
                "tokens": str(tokens),
                "input_tokens": str(inn),
                "output_tokens": str(out),
                "amount_usd": f"{float(amount_usd):.2f}",
                "product": "linas_token_pack",
            },
        }
        if customer_email:
            create_kwargs["customer_email"] = customer_email
        session = stripe.checkout.Session.create(**create_kwargs)  # type: ignore[arg-type]
        return {
            "id": session["id"],
            "url": session.get("url"),
            "payment_status": session.get("payment_status"),
        }

    def construct_event(self, payload: bytes, sig_header: str | None) -> dict[str, Any]:
        secret = stripe_webhook_secret()
        if not secret:
            raise RuntimeError("STRIPE_WEBHOOK_SECRET is not configured")
        try:
            import stripe  # type: ignore
        except ImportError as exc:
            raise RuntimeError("stripe package not installed") from exc

        event = stripe.Webhook.construct_event(payload, sig_header, secret)
        if hasattr(event, "to_dict"):
            return event.to_dict()  # type: ignore[no-any-return]
        return dict(event)  # type: ignore[arg-type]


stripe_checkout_service = StripeCheckoutService()
