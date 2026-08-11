#!/usr/bin/env python3
"""Platform-owner CLI for temporary Meta App Review WhatsApp bind (tenant linas).

Token is read ONLY from env META_WHATSAPP_APP_REVIEW_BIND_TOKEN — never argv.
Never prints the token. Does not mutate production unless --apply is passed.

Examples:
  # Dry-run (validate Meta assets + collision check)
  META_WHATSAPP_APP_REVIEW_BIND_TOKEN='…' \\
    python scripts/wa_app_review_temp_bind.py dry-run \\
    --waba-id <WABA> --phone-number-id <PHONE>

  # Apply bind (requires explicit --apply)
  META_WHATSAPP_APP_REVIEW_BIND_TOKEN='…' \\
    python scripts/wa_app_review_temp_bind.py bind --apply \\
    --waba-id <WABA> --phone-number-id <PHONE>

  python scripts/wa_app_review_temp_bind.py status
  python scripts/wa_app_review_temp_bind.py unbind --apply
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _print(payload: dict) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True, default=str))


async def _main() -> int:
    parser = argparse.ArgumentParser(description="Temporary Meta App Review WhatsApp bind for linas")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_status = sub.add_parser("status", help="Show app-review bind status for linas")
    p_status.add_argument("--tenant-id", default="linas")

    p_dry = sub.add_parser("dry-run", help="Validate assets without writing")
    p_dry.add_argument("--tenant-id", default="linas")
    p_dry.add_argument("--waba-id", required=True)
    p_dry.add_argument("--phone-number-id", required=True)
    p_dry.add_argument("--actor", default="cli:app_review")
    p_dry.add_argument("--idempotency-key", default="")

    p_bind = sub.add_parser("bind", help="Create temporary bind (requires --apply)")
    p_bind.add_argument("--tenant-id", default="linas")
    p_bind.add_argument("--waba-id", required=True)
    p_bind.add_argument("--phone-number-id", required=True)
    p_bind.add_argument("--actor", default="cli:app_review")
    p_bind.add_argument("--idempotency-key", default="")
    p_bind.add_argument("--apply", action="store_true", help="Actually write the connection")

    p_unbind = sub.add_parser("unbind", help="Remove temporary bind (requires --apply)")
    p_unbind.add_argument("--tenant-id", default="linas")
    p_unbind.add_argument("--connection-id", default="")
    p_unbind.add_argument("--actor", default="cli:app_review")
    p_unbind.add_argument("--idempotency-key", default="")
    p_unbind.add_argument("--apply", action="store_true", help="Actually revoke the connection")

    args = parser.parse_args()

    from services.whatsapp_cloud.app_review_bind import (
        AppReviewBindError,
        bind_app_review_test_number,
        status_app_review_bind,
        unbind_app_review_test_number,
    )

    try:
        if args.cmd == "status":
            _print(status_app_review_bind(tenant_id=args.tenant_id))
            return 0
        if args.cmd == "dry-run":
            result = await bind_app_review_test_number(
                tenant_id=args.tenant_id,
                waba_id=args.waba_id,
                phone_number_id=args.phone_number_id,
                access_token=None,
                actor_user_id=args.actor,
                idempotency_key=args.idempotency_key or None,
                dry_run=True,
            )
            _print(result.public_dict())
            return 0 if result.success else 2
        if args.cmd == "bind":
            if not args.apply:
                _print(
                    {
                        "success": False,
                        "error": "apply_required",
                        "message": "Pass --apply to mutate. Use dry-run first.",
                    }
                )
                return 2
            result = await bind_app_review_test_number(
                tenant_id=args.tenant_id,
                waba_id=args.waba_id,
                phone_number_id=args.phone_number_id,
                access_token=None,
                actor_user_id=args.actor,
                idempotency_key=args.idempotency_key or None,
                dry_run=False,
            )
            _print(result.public_dict())
            return 0 if result.success else 2
        if args.cmd == "unbind":
            if not args.apply:
                _print(
                    {
                        "success": False,
                        "error": "apply_required",
                        "message": "Pass --apply to revoke the temporary connection.",
                    }
                )
                return 2
            result = unbind_app_review_test_number(
                tenant_id=args.tenant_id,
                actor_user_id=args.actor,
                connection_id=args.connection_id or None,
                idempotency_key=args.idempotency_key or None,
            )
            _print(result.public_dict())
            return 0 if result.success else 2
    except AppReviewBindError as exc:
        _print({"success": False, "error": exc.code, "message": exc.message})
        return 2
    return 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_main()))
