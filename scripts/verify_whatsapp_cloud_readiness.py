#!/usr/bin/env python3
"""Read-only WhatsApp Cloud rollout readiness probe against the live site.

Does not prove Phase 1 flags, pilot rows, or a successful Connect — only public
routing, bridge reachability, and /api/ready signals operators expect before pilot.
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request

DEFAULT_BASE = "https://www.linasaibot.com"

BRIDGE_PATH = "/integrations/whatsapp/embedded-signup"
READY_PATH = "/api/ready"
HEALTH_PATH = "/api/health"


def _get(url: str, *, timeout: float) -> tuple[int, dict[str, object] | None, str]:
    request = urllib.request.Request(url, headers={"User-Agent": "linas-wa-readiness/1"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read(65536).decode("utf-8", "replace")
            parsed: dict[str, object] | None = None
            if raw.strip().startswith("{"):
                try:
                    loaded = json.loads(raw)
                    if isinstance(loaded, dict):
                        parsed = loaded
                except json.JSONDecodeError:
                    pass
            return int(response.status), parsed, raw
    except urllib.error.HTTPError as exc:
        body = exc.read(4096).decode("utf-8", "replace")
        return int(exc.code), None, body[:200]
    except urllib.error.URLError as exc:
        raise RuntimeError(f"request failed: {exc}") from exc


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify live WhatsApp Cloud readiness signals")
    parser.add_argument("--base", default=DEFAULT_BASE, help="Site base URL")
    parser.add_argument("--timeout", type=float, default=15.0)
    args = parser.parse_args()
    base = args.base.rstrip("/")

    failures: list[str] = []
    notes: list[str] = []

    health_status, _, _ = _get(f"{base}{HEALTH_PATH}", timeout=args.timeout)
    if health_status != 200:
        failures.append(f"health HTTP {health_status}")
    else:
        notes.append("health=200")

    ready_status, ready, _ = _get(f"{base}{READY_PATH}", timeout=args.timeout)
    if ready_status != 200 or ready is None:
        failures.append(f"ready HTTP {ready_status} or non-JSON")
    else:
        if ready.get("ok") is not True:
            failures.append("ready.ok is not true")
        checks = ready.get("checks")
        if not isinstance(checks, dict):
            failures.append("ready.checks missing")
        else:
            wa_creds = checks.get("whatsapp_cloud_credentials")
            if isinstance(wa_creds, dict) and wa_creds.get("configured") is True:
                notes.append("whatsapp_cloud_credentials.configured=true")
            else:
                failures.append("whatsapp_cloud_credentials not configured")

            wa_ai = checks.get("whatsapp_inbound_ai")
            if isinstance(wa_ai, dict):
                notes.append(f"whatsapp_inbound_ai.enabled={wa_ai.get('enabled')!r}")

            tiktok = checks.get("tiktok_business")
            if isinstance(tiktok, dict):
                keys = tiktok.get("config_keys_present")
                if isinstance(keys, dict) and keys.get("LINAS_WHATSAPP_DATABASE_URL") is True:
                    notes.append("LINAS_WHATSAPP_DATABASE_URL=present")
                else:
                    failures.append("LINAS_WHATSAPP_DATABASE_URL not reported present")

    bridge_status, _, bridge_body = _get(
        f"{base}{BRIDGE_PATH}?state=readiness-probe",
        timeout=args.timeout,
    )
    if bridge_status != 200:
        failures.append(f"embedded-signup bridge HTTP {bridge_status}")
    else:
        bridge_lower = bridge_body.lower()
        if "coexistence" not in bridge_lower and "whatsapp business app" not in bridge_lower:
            failures.append("embedded-signup bridge missing coexistence copy")
        else:
            notes.append("embedded-signup bridge=200 (coexistence copy present)")

    print(f"base={base}")
    for line in notes:
        print(f"  OK  {line}")
    for line in failures:
        print(f"  FAIL  {line}", file=sys.stderr)

    if failures:
        print(
            "\nNext: apply Phase 1 flags (two-node guarded), grant pilot for tenant linas, "
            "then Connect from mobile. See docs/WHATSAPP_CLOUD_SETUP_AND_APP_REVIEW_VIDEO.md",
            file=sys.stderr,
        )
        return 1

    print(
        "\nPublic readiness signals OK. Still required before Connect: "
        "Phase 1 WHATSAPP_CLOUD_* flags on server + pilot row for tenant linas."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
