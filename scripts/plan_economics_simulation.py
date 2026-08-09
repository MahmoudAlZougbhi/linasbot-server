#!/usr/bin/env python3
"""Run Wave 0 subscription economics simulation (read-only).

Usage:
  python scripts/plan_economics_simulation.py
  python scripts/plan_economics_simulation.py --json > reports/plan_economics.json

Does not change plan prices. Does not write production data.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="Linas AI plan economics simulation")
    parser.add_argument("--json", action="store_true", help="Emit full JSON report to stdout")
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Optional path to write JSON report",
    )
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[1]
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))

    from services.plan_economics import build_economics_report

    report = build_economics_report()
    payload = json.dumps(report, indent=2, sort_keys=True)

    if args.out is not None:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(payload + "\n", encoding="utf-8")

    if args.json or args.out is None:
        print(payload)

    if not args.json:
        print("\n=== Summary ===", file=sys.stderr)
        for plan in report["plans"]:
            a = plan["allowance"]
            flag = "OK" if a["margin_ok"] else "FLAG"
            print(
                f"{a['plan_id']}: ${a['price_usd']} | "
                f"dm={a['included_dm_replies']} owner={a['included_owner_messages']} "
                f"img={a['included_images']} vid={a['included_videos']} "
                f"credits={a['included_credits']} | "
                f"margin@100%={a['gross_margin_at_100pct']:.1%} [{flag}]",
                file=sys.stderr,
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
