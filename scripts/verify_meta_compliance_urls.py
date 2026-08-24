#!/usr/bin/env python3
"""Verify Meta compliance pages and signed callback rejection on the live site.

HTTP 200 on a callback URL only proves routing — not Meta's signed_request contract.
For the full contract (valid signed_request, wrong signature, confirmation JSON),
run the pytest suite locally or in CI:

  pytest tests/test_meta_compliance.py -q

Live checks (default):
  - Public legal pages return HTML 200
  - Callback health GET returns {"status":"ok"}
  - POST with missing/invalid signed_request returns 400 (no secrets required)
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import hmac
import json
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

DEFAULT_BASE = "https://www.linasaibot.com"

PUBLIC_PAGES: tuple[tuple[str, str], ...] = (
    ("privacy_policy", "/privacy-policy"),
    ("terms", "/terms"),
    ("data_deletion_instructions", "/data-deletion"),
)

CALLBACKS: tuple[tuple[str, str], ...] = (
    ("facebook_data_deletion", "/oauth/meta/data-deletion"),
    ("facebook_deauthorize", "/oauth/meta/deauthorize"),
    ("instagram_data_deletion", "/oauth/instagram/data-deletion"),
    ("instagram_deauthorize", "/oauth/instagram/deauthorize"),
)


def _b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _signed_request(*, secret: str, user_id: str = "999888777") -> str:
    payload = {
        "algorithm": "HMAC-SHA256",
        "issued_at": int(time.time()),
        "user_id": user_id,
    }
    encoded_payload = _b64url(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    signature = hmac.new(secret.encode("utf-8"), encoded_payload.encode("ascii"), hashlib.sha256).digest()
    return f"{_b64url(signature)}.{encoded_payload}"


def _request(
    url: str,
    *,
    method: str = "GET",
    data: dict[str, str] | None = None,
    timeout: float,
) -> tuple[int, str, dict[str, object] | None]:
    body: bytes | None = None
    headers = {"User-Agent": "linas-meta-compliance-verify/2"}
    if data is not None:
        body = urllib.parse.urlencode(data).encode("utf-8")
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    request = urllib.request.Request(url, data=body, method=method, headers=headers)
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
                    parsed = None
            return int(response.status), raw[:200], parsed
    except urllib.error.HTTPError as exc:
        raw = exc.read(65536).decode("utf-8", "replace")
        parsed = None
        if raw.strip().startswith("{"):
            try:
                loaded = json.loads(raw)
                if isinstance(loaded, dict):
                    parsed = loaded
            except json.JSONDecodeError:
                parsed = None
        return int(exc.code), raw[:200], parsed
    except urllib.error.URLError as exc:
        return 0, type(exc.reason).__name__, None


def _run_pytest_contract() -> int:
    completed = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/test_meta_compliance.py", "-q", "--tb=line"],
        check=False,
    )
    return int(completed.returncode)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default=DEFAULT_BASE)
    parser.add_argument("--timeout", type=float, default=15.0)
    parser.add_argument(
        "--pytest-contract",
        action="store_true",
        help="Run tests/test_meta_compliance.py (valid signed_request + Meta JSON contract).",
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    base = args.base_url.rstrip("/")

    if args.pytest_contract:
        code = _run_pytest_contract()
        if code == 0 and not args.json:
            print("[compliance-verify] PYTEST_CONTRACT_PASS")
        elif code != 0 and not args.json:
            print("[compliance-verify] PYTEST_CONTRACT_FAIL")
        return code

    results: list[dict[str, object]] = []
    failed = 0

    for name, path in PUBLIC_PAGES:
        url = f"{base}{path}"
        status, _snippet, _parsed = _request(url, timeout=args.timeout)
        ok = status == 200
        failed += 0 if ok else 1
        item = {"check": name, "kind": "public_page", "url": url, "status": status, "ok": ok}
        results.append(item)
        if not args.json:
            print(f"[compliance-verify] {'PASS' if ok else 'FAIL'} public {name} status={status}")

    for name, path in CALLBACKS:
        url = f"{base}{path}"
        get_status, _snippet, parsed = _request(url, timeout=args.timeout)
        health_ok = get_status == 200 and parsed == {"status": "ok"}
        if not health_ok:
            failed += 1
        results.append(
            {
                "check": f"{name}_health",
                "kind": "callback_health",
                "url": url,
                "status": get_status,
                "ok": health_ok,
            }
        )
        if not args.json:
            print(f"[compliance-verify] {'PASS' if health_ok else 'FAIL'} health {name} status={get_status}")

        missing_status, _body, _ = _request(url, method="POST", data={}, timeout=args.timeout)
        missing_ok = missing_status == 400
        if not missing_ok:
            failed += 1
        results.append(
            {
                "check": f"{name}_reject_missing",
                "kind": "signed_reject",
                "url": url,
                "status": missing_status,
                "ok": missing_ok,
            }
        )
        if not args.json:
            print(
                f"[compliance-verify] {'PASS' if missing_ok else 'FAIL'} reject_missing {name} status={missing_status}"
            )

        bad = _signed_request(secret="linas-compliance-probe-invalid-secret")
        bad_status, _body, bad_json = _request(
            url,
            method="POST",
            data={"signed_request": bad},
            timeout=args.timeout,
        )
        bad_ok = bad_status == 400
        if not bad_ok:
            failed += 1
        results.append(
            {
                "check": f"{name}_reject_bad_signature",
                "kind": "signed_reject",
                "url": url,
                "status": bad_status,
                "ok": bad_ok,
                "detail": bad_json.get("detail") if isinstance(bad_json, dict) else None,
            }
        )
        if not args.json:
            print(f"[compliance-verify] {'PASS' if bad_ok else 'FAIL'} reject_bad_sig {name} status={bad_status}")

    if args.json:
        print(
            json.dumps(
                {
                    "base": base,
                    "failed": failed,
                    "results": results,
                    "pytest_contract_command": "pytest tests/test_meta_compliance.py -q",
                },
                sort_keys=True,
            )
        )
    elif failed:
        print(f"[compliance-verify] LIVE_CHECKS_FAILED count={failed}")
        print("[compliance-verify] Run: python scripts/verify_meta_compliance_urls.py --pytest-contract")
        return 1

    if not args.json:
        print("[compliance-verify] LIVE_CHECKS_PASS")
        print("[compliance-verify] Next: python scripts/verify_meta_compliance_urls.py --pytest-contract")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
