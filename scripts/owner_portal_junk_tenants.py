"""Dry-run list of junk portal tenants. It changes nothing unless confirmation matches.

Never selects linas, platform, testuser, or a tenant with messages, credits, or a published brain.
"""

from __future__ import annotations

import argparse
import json
from typing import Any

from services.team.tenant_identity import PROTECTED_TENANTS, is_junk_identity


def candidate_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    chosen: list[dict[str, Any]] = []
    for row in rows:
        tenant_id = str(row.get("tenant_id") or "")
        if tenant_id.strip().lower() in PROTECTED_TENANTS:
            continue
        if not is_junk_identity(
            tenant_id=tenant_id,
            business_name=str(row.get("business_name") or ""),
            email=str(row.get("email") or ""),
        ):
            continue
        if int(row.get("messages_remaining") or 0) or int(row.get("historical_credit_remaining") or 0):
            continue
        if int(row.get("messages_used") or 0) or int(row.get("credits_used") or 0):
            continue
        if row.get("published_brain"):
            continue
        chosen.append(
            {
                "tenant_id": tenant_id,
                "business_name": row.get("business_name") or "",
                "email": row.get("email") or "",
                "created_at": row.get("created_at") or "",
                "messages_remaining": int(row.get("messages_remaining") or 0),
                "historical_credit_remaining": int(row.get("historical_credit_remaining") or 0),
            }
        )
    return chosen


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--confirm", action="store_true")
    parser.add_argument("--tenant-ids", default="")
    parser.add_argument("--rows-json", default="")
    args = parser.parse_args(argv)
    rows = json.loads(args.rows_json) if args.rows_json else []
    chosen = candidate_rows(rows)
    print(json.dumps({"dry_run": not args.confirm, "candidates": chosen}, ensure_ascii=False))
    if not args.confirm:
        return 0
    echoed = [item.strip() for item in args.tenant_ids.split(",") if item.strip()]
    if echoed != [row["tenant_id"] for row in chosen]:
        print("confirmation did not match the candidate ids; nothing changed")
        return 2
    print("confirmed archive list only; this script does not delete rows")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
