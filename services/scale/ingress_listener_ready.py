"""Local ingress probes so /api/ready is not 200 while nginx still 502s webhooks.

Loopback POST is skipped when the listener port is closed (unit tests / TestClient).
Production API already listens on 8003 while serving /api/ready; asyncio can accept
the nested unsigned webhook while this probe awaits.
"""

from __future__ import annotations

import socket
from typing import Any

import httpx

_DIRECT = "http://127.0.0.1:8003"
_NGINX = "http://127.0.0.1"
_HOST = "linasaibot.com"


def _port_open(port: int) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.15):
            return True
    except OSError:
        return False


def _probe_ok(status: int) -> bool:
    # 401/400/403: listener accepted the route. 502/504: nginx has no upstream.
    return status in {400, 401, 403} and status not in {502, 504}


async def probe_local_ingress_listeners() -> dict[str, Any]:
    """Return a readiness fragment; missing local listeners are skipped, not failed."""

    checks: dict[str, Any] = {}
    overall = True
    targets: list[tuple[str, str, int]] = []
    if _port_open(8003):
        targets.append(("meta_direct", f"{_DIRECT}/webhook/meta-messaging", 8003))
        targets.append(("tiktok_direct", f"{_DIRECT}/webhook/tiktok", 8003))
    if _port_open(80):
        targets.append(("meta_nginx", f"{_NGINX}/webhook/meta-messaging", 80))
        targets.append(("tiktok_nginx", f"{_NGINX}/webhook/tiktok", 80))
    if not targets:
        return {"ok": True, "skipped": True, "reason": "no_local_ingress_ports"}

    timeout = httpx.Timeout(0.8, connect=0.2)
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=False) as client:
        for name, url, _port in targets:
            try:
                response = await client.post(
                    url,
                    content=b"{}",
                    headers={"Host": _HOST, "Content-Type": "application/json"},
                )
                ok = _probe_ok(response.status_code)
                checks[name] = {"ok": ok, "http": response.status_code}
                if not ok:
                    overall = False
            except Exception as exc:
                checks[name] = {"ok": False, "error": type(exc).__name__}
                overall = False
    return {"ok": overall, "probes": checks}
