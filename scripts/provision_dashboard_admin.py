#!/usr/bin/env python3
"""
Offline first-admin provisioning for the dashboard.

Not exposed over HTTP. Requires explicit operator execution.

Usage:
  PROVISION_ADMIN_PASSWORD='...' \\
    python scripts/provision_dashboard_admin.py --email owner@example.com

  # Interactive password prompt (preferred on operator workstations):
  python scripts/provision_dashboard_admin.py --email owner@example.com --prompt-password

Never pass the password on the command line (shell history). Do not commit credentials.
"""

from __future__ import annotations

import argparse
import getpass
import json
import os
import sys


def _read_password(prompt: bool) -> str:
    if prompt:
        pw = getpass.getpass("Admin password (input hidden): ")
        pw2 = getpass.getpass("Confirm password: ")
        if pw != pw2:
            raise SystemExit("ERROR: passwords do not match")
        return pw
    env_name = os.getenv("PROVISION_ADMIN_PASSWORD_ENV", "PROVISION_ADMIN_PASSWORD")
    pw = os.getenv(env_name) or ""
    if not pw:
        raise SystemExit(
            f"ERROR: set {env_name} or pass --prompt-password (do not pass the password as a CLI argument)"
        )
    return pw


def main() -> int:
    parser = argparse.ArgumentParser(description="Provision first dashboard admin (offline CLI)")
    parser.add_argument("--email", required=True, help="Admin email")
    parser.add_argument("--name", default=None, help="Display name (optional)")
    parser.add_argument(
        "--prompt-password",
        action="store_true",
        help="Read password interactively (never echoed)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit a redacted JSON audit line on stdout",
    )
    parser.add_argument(
        "--role",
        default="admin",
        choices=["admin", "platform_owner"],
        help="admin (default first-admin) or platform_owner (offline-only elevation)",
    )
    args = parser.parse_args()

    try:
        password = _read_password(prompt=bool(args.prompt_password))
    except SystemExit as e:
        print(str(e), file=sys.stderr)
        return 2

    from services.admin_provisioning_service import audit_line, provision_first_admin

    try:
        result = provision_first_admin(
            email=args.email,
            password=password,
            name=args.name,
            created_by="cli-provision",
            role=str(args.role),
        )
    except ValueError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2
    except Exception as e:
        print(f"ERROR: {type(e).__name__}", file=sys.stderr)
        return 1
    finally:
        # Best-effort scrub of local reference
        password = ""

    record = audit_line(result)
    if args.json:
        print(json.dumps(record, separators=(",", ":")))
    else:
        print(
            f"INFO: status={result.status} email={result.email or '-'} "
            f"user_id={result.user_id or '-'} — {result.message}"
        )

    if result.status == "created":
        return 0
    if result.status == "already_provisioned":
        return 0  # idempotent success
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
