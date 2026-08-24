#!/usr/bin/env python3
"""Idempotent WhatsApp Cloud pilot entitlement grant (audited, no secrets printed)."""

from __future__ import annotations

import argparse
import sys


def main() -> int:
    parser = argparse.ArgumentParser(description="Grant WhatsApp Cloud pilot entitlement")
    parser.add_argument("--tenant-id", required=True)
    parser.add_argument("--reason", required=True)
    parser.add_argument("--granted-by", default="production_ops")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    tenant_id = str(args.tenant_id).strip().lower()
    reason = str(args.reason).strip()
    if not tenant_id or not reason:
        print("[wa-pilot-grant] tenant_id and reason are required", file=sys.stderr)
        return 2

    from db.session import WhatsAppDatabaseUnavailable, whatsapp_session
    from services.whatsapp_cloud.repository import WhatsAppCloudRepository

    try:
        with whatsapp_session(require=True) as session:
            repo = WhatsAppCloudRepository(session)
            existing = repo.get_active_pilot(tenant_id)
            if existing is not None:
                print(
                    f"[wa-pilot-grant] already_active=true tenant_id={tenant_id} "
                    f"granted_at={existing.granted_at.isoformat()}"
                )
                return 0
            if args.dry_run:
                print(f"[wa-pilot-grant] dry_run=true would_grant tenant_id={tenant_id}")
                return 0
            row = repo.grant_pilot(
                tenant_id=tenant_id,
                granted_by_user_id=str(args.granted_by),
                reason=reason,
            )
            repo.add_audit(
                tenant_id=tenant_id,
                actor_user_id=str(args.granted_by),
                event_type="pilot_granted",
                detail={"reason": reason, "source": "prod_grant_whatsapp_pilot.py"},
            )
            print(f"[wa-pilot-grant] granted=true tenant_id={row.tenant_id} status={row.status}")
            return 0
    except WhatsAppDatabaseUnavailable:
        print("[wa-pilot-grant] WHATSAPP_DB_UNAVAILABLE", file=sys.stderr)
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
