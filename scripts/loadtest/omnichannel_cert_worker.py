"""Cert-only worker: stub AI/provider at process boundary, then run HA worker."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.loadtest.omnichannel_cert_guards import assert_staging_cert_allowed  # noqa: E402


async def _stub_generate(
    *, channel: str, surface: str, tenant_id: str, payload: dict[str, Any]
) -> tuple[str, str | None, str | None]:
    if channel == "tiktok" and surface == "dm":
        from services.omnichannel.gates import TIKTOK_DM_GATE_REASON, tiktok_dm_live_allowed

        allowed, reason = tiktok_dm_live_allowed(None)
        if not allowed:
            return "", None, reason or TIKTOK_DM_GATE_REASON
    reservation = payload.get("credit_reservation_id")
    reservation_id = str(reservation) if reservation is not None else None
    return "canonical-cert-reply", reservation_id, None


async def _stub_send(snapshot: dict[str, Any]) -> dict[str, Any]:
    fault = (os.getenv("LINAS_OMNI_CERT_FAULT") or "").strip()
    if fault == "429":
        return {
            "http_status": 429,
            "code": "613",
            "submitted": False,
            "headers": {"Retry-After": "1", "X-App-Usage": '{"call_count":90}'},
        }
    if fault == "5xx":
        return {"http_status": 503, "submitted": False, "error": "unavailable"}
    outbox_id = str(snapshot.get("id") or "x")[:12]
    return {"http_status": 200, "submitted": True, "message_id": f"mid_{outbox_id}"}


def main() -> int:
    assert_staging_cert_allowed(
        target_url="http://127.0.0.1:18080/inbound",
        tenant_id=os.getenv("LINAS_OMNI_CERT_TENANT") or "omni-cert-local",
        events_per_minute=1,
        duration_seconds=1,
    )
    from services.omnichannel import deliver, generate

    generate._generate_canonical = _stub_generate  # type: ignore[method-assign]
    deliver._send = _stub_send  # type: ignore[method-assign]
    from services.queues.worker_runtime import main as worker_main

    return worker_main()


if __name__ == "__main__":
    raise SystemExit(main())
