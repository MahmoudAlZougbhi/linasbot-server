#!/usr/bin/env python3
"""Backfill Meta comment permission verification before permission-hardening deploy.

Run after Alembic upgrade `20260826_meta_comment_perm` and before any node receives
the new application build on the load balancer. Intended to run from the protected
HA deploy path (not ad-hoc manual SSH).

Safe to run twice; only updates bindings still in unknown/unbound verification state.
Never prints tokens, secrets, or comment content.

Exit codes:
  0 — backfill complete and no active binding remains unknown
  2 — dry-run ok, or apply finished but unknown active bindings remain (block LB)
  1 — unexpected failure
"""

from __future__ import annotations

import argparse
import json
import sys


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report pending unknown bindings without writing.",
    )
    args = parser.parse_args()

    try:
        from services.meta_app_registry import get_meta_app_registry
        from services.meta_comment_permission_verification import (
            bootstrap_unknown_comment_permissions,
            count_active_bindings_with_unknown_comment_permission,
        )

        registry = get_meta_app_registry()
        pending_before = count_active_bindings_with_unknown_comment_permission(registry=registry)
        if args.dry_run:
            print(
                json.dumps(
                    {"dry_run": True, "pending_unknown_active": pending_before},
                    sort_keys=True,
                )
            )
            return 0

        result = bootstrap_unknown_comment_permissions(actor_id="pre_lb_backfill")
        pending_after = count_active_bindings_with_unknown_comment_permission(registry=registry)
        payload = {
            "dry_run": False,
            "pending_unknown_active_before": pending_before,
            "pending_unknown_active_after": pending_after,
            **result,
        }
        print(json.dumps(payload, sort_keys=True))
        if pending_after > 0:
            return 2
        return 0
    except Exception as exc:
        print(json.dumps({"error": type(exc).__name__}, sort_keys=True), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
