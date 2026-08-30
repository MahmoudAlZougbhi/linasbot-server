"""Local ingress probes so /api/ready is not 200 while nginx still 502s webhooks.

Loopback POST is skipped when the listener port is closed (unit tests / TestClient).
Production API already listens on 8003 while serving /api/ready; asyncio can accept
the nested unsigned webhook while this probe awaits.

DigitalOcean TLS-terminates and forwards to nginx :80 with X-Forwarded-Proto=https.
A loopback POST without that header hits the public HTTP→HTTPS 301, which is not
an upstream failure. Direct TLS clients use :443.
"""

from __future__ import annotations

import socket
from typing import Any

import httpx

_DIRECT = "http://127.0.0.1:8003"
_NGINX_HTTP = "http://127.0.0.1"
_NGINX_TLS = "https://127.0.0.1"
_HOST = "linasaibot.com"
_ACCEPT = frozenset({400, 401, 403})
_LB_HEADERS = {
    "Host": _HOST,
    "Content-Type": "application/json",
    "X-Forwarded-Proto": "https",
}
_TLS_HEADERS = {"Host": _HOST, "Content-Type": "application/json"}


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
    """Return a readiness fragment; missing local listeners are skipped, not failed."""

    checks: dict[str, Any] = {}
    overall = True
    http_targets: list[tuple[str, str, dict[str, str]]] = []
    tls_targets: list[tuple[str, str]] = []
    if _port_open(8003):
        http_targets.append(("meta_direct", f"{_DIRECT}/webhook/meta-messaging", _TLS_HEADERS))
        http_targets.append(("tiktok_direct", f"{_DIRECT}/webhook/tiktok", _TLS_HEADERS))
    if _port_open(80):
        http_targets.append(("meta_nginx", f"{_NGINX_HTTP}/webhook/meta-messaging", _LB_HEADERS))
        http_targets.append(("tiktok_nginx", f"{_NGINX_HTTP}/webhook/tiktok", _LB_HEADERS))
    if _port_open(443):
        tls_targets.append(("meta_nginx_tls", f"{_NGINX_TLS}/webhook/meta-messaging"))
        tls_targets.append(("tiktok_nginx_tls", f"{_NGINX_TLS}/webhook/tiktok"))
    if not http_targets and not tls_targets:
        return {"ok": True, "skipped": True, "reason": "no_local_ingress_ports"}

    timeout = httpx.Timeout(0.8, connect=0.2)

    async def _run(
        client: httpx.AsyncClient,
        name: str,
        url: str,
        headers: dict[str, str],
    ) -> None:
        nonlocal overall
        try:
            response = await client.post(url, content=b"{}", headers=headers)
            ok = _probe_ok(response.status_code)
            checks[name] = {"ok": ok, "http": response.status_code}
            if not ok:
                overall = False
        except Exception as exc:
            checks[name] = {"ok": False, "error": type(exc).__name__}
            overall = False

    if http_targets:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=False) as client:
            for name, url, headers in http_targets:
                await _run(client, name, url, headers)
    if tls_targets:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=False, verify=False) as client:
            for name, url in tls_targets:
                await _run(client, name, url, _TLS_HEADERS)
    return {"ok": overall, "probes": checks}
