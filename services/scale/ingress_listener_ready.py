"""Local ingress probes so /api/ready is not 200 while nginx still 502s webhooks.

Loopback POST is skipped when the listener port is closed (unit tests / TestClient).
Production API already listens on 8003 while serving /api/ready; asyncio can accept
the nested unsigned webhook while this probe awaits.

DigitalOcean TLS-terminates and forwards to nginx :80 with X-Forwarded-Proto=https.
A loopback POST without that header hits the public HTTP→HTTPS 301, which is not
an upstream failure. Probing :443 with a self-signed/local cert is unnecessary when
the LB path on :80 with the forwarded-proto header matches production ingress.
"""

from __future__ import annotations

import socket
from typing import Any

import httpx

_DIRECT = "http://127.0.0.1:8003"
_NGINX_HTTP = "http://127.0.0.1"
_HOST = "linasaibot.com"
_ACCEPT = frozenset({400, 401, 403})
_DIRECT_HEADERS = {"Host": _HOST, "Content-Type": "application/json"}
_LB_HEADERS = {
    "Host": _HOST,
    "Content-Type": "application/json",
    "X-Forwarded-Proto": "https",
}


def _port_open(port: int) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.15):
            return True
    except OSError:
        return False


def _probe_ok(status: int) -> bool:
    # 401/400/403: listener accepted the route. 301 is HTTP→HTTPS without LB proto.
    # 502/504: nginx has no upstream.
    return status in _ACCEPT


async def probe_local_ingress_listeners() -> dict[str, Any]:
    """Return a readiness fragment; missing local listeners are skipped, not failed.

    Prefer nginx :80 with X-Forwarded-Proto (DO LB path). Nested POSTs to the
    same process on :8003 can ConnectTimeout while /api/ready holds the
    single worker, which falsely 503s readiness under probe contention.
    """

    checks: dict[str, Any] = {}
    targets: list[tuple[str, str, dict[str, str]]] = []
    nginx_open = _port_open(80)
    direct_open = _port_open(8003)
    if nginx_open:
        targets.append(("meta_nginx", f"{_NGINX_HTTP}/webhook/meta-messaging", _LB_HEADERS))
        targets.append(("tiktok_nginx", f"{_NGINX_HTTP}/webhook/tiktok", _LB_HEADERS))
    elif direct_open:
        targets.append(("meta_direct", f"{_DIRECT}/webhook/meta-messaging", _DIRECT_HEADERS))
        targets.append(("tiktok_direct", f"{_DIRECT}/webhook/tiktok", _DIRECT_HEADERS))
    if not targets:
        return {"ok": True, "skipped": True, "reason": "no_local_ingress_ports"}

    # Short connect budget avoids wedging /api/ready behind nested self-probes;
    # retries below tolerate one path timing out while the other stays healthy.
    timeout = httpx.Timeout(2.5, connect=1.0)

    async with httpx.AsyncClient(timeout=timeout, follow_redirects=False) as client:
        for name, url, headers in targets:
            last: dict[str, Any] | None = None
            ok = False
            for _ in range(3):
                try:
                    response = await client.post(url, content=b"{}", headers=headers)
                    ok = _probe_ok(response.status_code)
                    last = {"ok": ok, "http": response.status_code}
                    if ok:
                        break
                except Exception as exc:
                    last = {"ok": False, "error": type(exc).__name__}
            assert last is not None
            checks[name] = last
    # One accepted nginx/direct probe proves listeners are up; a transient
    # timeout on the sibling path must not 503 the whole ready surface.
    overall = any(isinstance(v, dict) and v.get("ok") is True for v in checks.values())
    return {"ok": overall, "probes": checks}
