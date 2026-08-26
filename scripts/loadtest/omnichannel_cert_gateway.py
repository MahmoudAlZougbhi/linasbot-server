"""Loopback HTTP ingress for isolated omnichannel certification."""

from __future__ import annotations

import json
import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.loadtest.omnichannel_cert_guards import (  # noqa: E402
    TEST_TENANT_PREFIX,
    assert_staging_cert_allowed,
)
from services.omnichannel.accept import InboundAcceptError, accept_and_enqueue  # noqa: E402
from services.omnichannel.contract import NormalizedInbound  # noqa: E402


class _Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, _format: str, *_args) -> None:  # noqa: A003
        return

    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b"{}"
        try:
            body = json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError:
            self._send(400, {"ok": False, "error": "invalid_json"})
            return
        tenant_id = str(body.get("tenant_id") or "")
        if not tenant_id.startswith(TEST_TENANT_PREFIX):
            self._send(403, {"ok": False, "error": "test_tenant_prefix_required"})
            return
        event = NormalizedInbound(
            provider_event_id=str(body.get("provider_event_id") or "")[:128],
            tenant_id=tenant_id,
            account_id=str(body.get("account_id") or "acct")[:128],
            channel=body.get("channel") or "instagram",  # type: ignore[arg-type]
            surface=body.get("surface") or "dm",  # type: ignore[arg-type]
            conversation_key=str(body.get("conversation_key") or "")[:255],
            provider_timestamp=float(body.get("provider_timestamp") or 0),
            payload_hash=str(body.get("payload_hash") or body.get("provider_event_id") or ""),
            payload=dict(body.get("payload") or {"text": "cert"}),
        )
        try:
            inbound_id, created = accept_and_enqueue(event)
        except InboundAcceptError:
            self._send(503, {"ok": False, "error": "enqueue_failed"})
            return
        self._send(200, {"ok": True, "id": inbound_id, "created": created})

    def do_GET(self) -> None:  # noqa: N802
        self._send(200, {"ok": True, "role": "omnichannel-cert-gateway"})

    def _send(self, status: int, payload: dict) -> None:
        raw = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)


def main() -> int:
    host = (os.getenv("LINAS_OMNI_CERT_BIND") or "127.0.0.1").strip()
    port = int(os.getenv("LINAS_OMNI_CERT_PORT") or "18080")
    assert_staging_cert_allowed(
        target_url=f"http://{host}:{port}/inbound",
        tenant_id=os.getenv("LINAS_OMNI_CERT_TENANT") or "omni-cert-local",
        events_per_minute=1,
        duration_seconds=1,
    )
    server = ThreadingHTTPServer((host, port), _Handler)
    server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
