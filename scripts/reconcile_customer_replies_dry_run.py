#!/usr/bin/env python3
"""Dry-run report for customer reply reconciliation (no mutations)."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Dry-run customer reply reconciliation report")
    parser.add_argument(
        "--older-than-seconds",
        type=float,
        default=60.0,
        help="Only include inbound events older than this threshold (default: 60)",
    )
    parser.add_argument(
        "--claim-ttl-seconds",
        type=float,
        default=120.0,
        help="Treat ai_turn claims older than this as stale (default: 120)",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Execute reconciliation actions (default: dry-run only)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit machine-readable JSON report",
    )
    return parser


async def _main_async(args: argparse.Namespace) -> int:
    from services.customer_reply_reconcile_worker import reconcile_customer_replies

    result = await reconcile_customer_replies(
        dry_run=not args.execute,
        older_than_seconds=args.older_than_seconds,
        claim_ttl_seconds=args.claim_ttl_seconds,
    )
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0

    summary = result.get("summary") or {}
    print("Customer Reply Reconciliation Report")
    print("=" * 40)
    print(f"mode={'EXECUTE' if args.execute else 'DRY_RUN'}")
    print(f"examined={summary.get('examined', 0)}")
    print(f"stuck_events_count={summary.get('stuck_events_count', 0)}")
    print(f"stale_claims_count={summary.get('stale_claims_count', 0)}")
    print(f"charged_without_delivery_count={summary.get('charged_without_delivery_count', 0)}")
    print(f"by_classification={summary.get('by_classification')}")
    print(f"by_action={summary.get('by_action')}")
    rows = result.get("planned_actions") or result.get("actions") or []
    print("-" * 40)
    for row in rows[:50]:
        print(
            f"{row.get('inbound_event_id')} "
            f"class={row.get('classification')} "
            f"action={row.get('action')} "
            f"reason={row.get('reason')}"
        )
    if len(rows) > 50:
        print(f"... {len(rows) - 50} more rows")
    return 0


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()
    return asyncio.run(_main_async(args))


if __name__ == "__main__":
    raise SystemExit(main())
