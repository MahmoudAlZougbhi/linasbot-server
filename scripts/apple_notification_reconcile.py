#!/usr/bin/env python3
"""Manual / scheduled Apple ASSN reconcile entrypoint.

Examples:
  python3 scripts/apple_notification_reconcile.py --original-transaction-id 100000012345
  python3 scripts/apple_notification_reconcile.py --start-ms 1700000000000 --end-ms 1700003600000

Never prints .p8 contents or full JWS payloads.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Reconcile Apple App Store transactions/notifications")
    parser.add_argument("--original-transaction-id", default="", help="Apple originalTransactionId")
    parser.add_argument("--start-ms", type=int, default=0, help="Notification history start (ms)")
    parser.add_argument("--end-ms", type=int, default=0, help="Notification history end (ms)")
    parser.add_argument("--notification-type", default="", help="Optional ASSN type filter")
    args = parser.parse_args(argv)

    from services.apple_app_store_client import (
        AppleIapConfigError,
        apple_app_store_client,
        iap_credentials_configured,
        iap_key_id,
    )
    from services.apple_iap_processor import process_notification_v2, reconcile_original_transaction
    from services.apple_jws import sha256_hex

    if not iap_credentials_configured():
        print(json.dumps({"ok": False, "error": "Apple IAP credentials not configured"}))
        return 2

    print(json.dumps({"ok": True, "key_id": iap_key_id(), "mode": "start"}))

    try:
        if args.original_transaction_id.strip():
            result = reconcile_original_transaction(args.original_transaction_id.strip())
            # Strip any accidental signed blobs from nested results.
            safe = {
                "ok": result.get("ok"),
                "original_transaction_id": result.get("original_transaction_id"),
                "count": len(result.get("results") or []),
                "results": [
                    {
                        "ok": r.get("ok"),
                        "duplicate": r.get("duplicate"),
                        "transaction_id": r.get("transaction_id"),
                        "tenant_id": r.get("tenant_id"),
                        "kind": r.get("kind"),
                        "error": r.get("error"),
                    }
                    for r in (result.get("results") or [])
                    if isinstance(r, dict)
                ],
            }
            print(json.dumps(safe))
            return 0

        if args.start_ms and args.end_ms and args.end_ms > args.start_ms:
            history = apple_app_store_client.get_notification_history(
                args.start_ms,
                args.end_ms,
                notification_type=args.notification_type or None,
            )
            processed = 0
            duplicates = 0
            errors = 0
            for item in history.get("notificationHistory") or []:
                if not isinstance(item, dict):
                    continue
                signed = item.get("signedPayload")
                if not isinstance(signed, str) or not signed.strip():
                    continue
                try:
                    out = process_notification_v2({"signedPayload": signed})
                    processed += 1
                    if out.get("duplicate"):
                        duplicates += 1
                except Exception as exc:  # noqa: BLE001
                    errors += 1
                    print(
                        json.dumps(
                            {
                                "ok": False,
                                "error": type(exc).__name__,
                                "payload_sha256": sha256_hex(signed),
                            }
                        )
                    )
            print(
                json.dumps(
                    {
                        "ok": True,
                        "processed": processed,
                        "duplicates": duplicates,
                        "errors": errors,
                        "has_more": bool(history.get("hasMore")),
                    }
                )
            )
            return 0 if errors == 0 else 1

        print(
            json.dumps(
                {
                    "ok": False,
                    "error": "Provide --original-transaction-id or --start-ms/--end-ms window",
                }
            )
        )
        return 2
    except AppleIapConfigError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}))
        return 2
    except Exception as exc:  # noqa: BLE001
        print(json.dumps({"ok": False, "error": type(exc).__name__}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
