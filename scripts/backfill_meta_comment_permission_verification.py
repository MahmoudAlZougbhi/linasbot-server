#!/usr/bin/env python3
"""Backfill Meta comment permission verification before permission-hardening deploy.

Run after Alembic upgrade `20260826_meta_comment_perm` and before any node receives
the new application build on the load balancer.

Safe to run twice; only updates bindings still in unknown/unbound verification state.
Never prints tokens, secrets, or comment content.
"""

from __future__ import annotations

import argparse
import json


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report how many bindings would be updated without writing.",
    )
    args = parser.parse_args()

    from services.meta_app_registry import get_meta_app_registry
    from services.meta_comment_permission_verification import (
        bootstrap_unknown_comment_permissions,
        effective_comment_permission_status,
    )

    registry = get_meta_app_registry()
    if args.dry_run:
        pending = 0
        for binding in registry.list_bindings(include_inactive=False, include_superseded=False):
            if binding.status != "active":
                continue
            try:
                credential = registry.get_credential(binding)
            except Exception:
                continue
            if effective_comment_permission_status(binding, credential) == "unknown":
                pending += 1
        print(json.dumps({"dry_run": True, "pending": pending}, sort_keys=True))
        return 0

    result = bootstrap_unknown_comment_permissions(actor_id="pre_lb_backfill")
    print(json.dumps({"dry_run": False, **result}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
