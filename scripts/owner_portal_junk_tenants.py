"""Dry-run list of junk portal tenants. It changes nothing unless confirmation matches.

Never selects linas, platform, testuser, or a tenant with messages, credits, or a published brain.
"""

from __future__ import annotations

import argparse
import json
from typing import Any

from services.team.tenant_identity import classify_tenant, matched_junk_rule


def _escape(value: object) -> str:
    return str(value or "").replace("\\", "\\\\").replace("\r", "\\r").replace("\n", "\\n").replace("\t", "\\t")


def _report_row(row: dict[str, Any], kind: str) -> dict[str, Any]:
    tenant_id = str(row.get("tenant_id") or "")
    published = row.get("published_brain")
    return {
        "tenant_id": tenant_id,
        "business_name": _escape(row.get("business_name")),
        "email": _escape(row.get("email")),
        "created_at": row.get("created_at") or "",
        "last_login": row.get("last_login") or "",
        "messages_used": int(row.get("messages_used") or 0),
        "credits_used": int(row.get("credits_used") or 0),
        "historical_credit_remaining": int(row.get("historical_credit_remaining") or 0),
        "payments": int(row.get("payments") or 0),
        "published_brain": "y" if published else "n",
        "conversations": int(row.get("conversations") or row.get("flows") or 0),
        "matched_rule": matched_junk_rule(
            tenant_id=tenant_id,
            business_name=str(row.get("business_name") or ""),
            email=str(row.get("email") or ""),
        ),
        "classification": kind,
    }


def candidate_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    chosen: list[dict[str, Any]] = []
    for row in rows:
        kind = classify_tenant(row)
        if kind != "candidate":
            continue
        chosen.append(_report_row(row, kind))
    return chosen


def review_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [_report_row(row, classify_tenant(row)) for row in rows if classify_tenant(row) != "normal"]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--confirm", action="store_true")
    parser.add_argument("--tenant-ids", default="")
    parser.add_argument("--rows-json", default="")
    args = parser.parse_args(argv)
    rows = json.loads(args.rows_json) if args.rows_json else []
    chosen = candidate_rows(rows)
    print(
        json.dumps(
            {"dry_run": not args.confirm, "candidates": chosen, "table": review_rows(rows)},
            ensure_ascii=False,
        )
    )
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
