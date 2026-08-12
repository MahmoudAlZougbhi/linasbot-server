#!/usr/bin/env python3
"""Verify file vs Postgres counts for billing/auth/credits/entitlements.

Read-only parity probe after import_billing_auth_to_postgres.py.
Does not change LINAS_BILLING_BACKEND / LINAS_AUTH_TOKEN_BACKEND.

Usage:
  python scripts/ha/verify_billing_auth_parity.py
  python scripts/ha/verify_billing_auth_parity.py --strict  # exit 1 on any mismatch
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _data_root() -> Path:
    from storage.persistent_storage import _DATA_ROOT

    return Path(_DATA_ROOT)


def _count_glob(path: Path, pattern: str) -> int:
    if not path.is_dir():
        return 0
    return sum(1 for _ in path.glob(pattern))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--strict", action="store_true", help="Exit 1 if any file count > PG count")
    args = parser.parse_args(argv)
    root = _data_root()

    from sqlalchemy import func, select

    from db.models.billing_auth import (
        AdminCreditIdempotencyRow,
        AuthEmailTokenRow,
        MobileRefreshTokenRow,
        StripeProcessedEventRow,
        TokenWalletRow,
    )
    from db.models.credit_entitlements import (
        CreditBalanceRow,
        CreditLedgerEntryRow,
        EntitlementProcessedEventRow,
        TenantEntitlementRow,
    )
    from db.session import WhatsAppDatabaseUnavailable, whatsapp_session

    ents_dir = root / "entitlements"
    ents_n = 0
    if ents_dir.is_dir():
        for path in ents_dir.glob("*.json"):
            if path.is_file():
                ents_n += 1
    file_counts = {
        "wallets": _count_glob(root / "billing" / "wallets", "*.json"),
        "stripe_events": _count_glob(root / "billing" / "stripe_events", "*.json"),
        "admin_credit": _count_glob(root / "billing" / "admin_credit_idempotency", "*.json"),
        "mobile_refresh": _count_glob(root / "auth" / "mobile_refresh", "*.json"),
        "auth_email": _count_glob(root / "auth" / "email_tokens", "*.json"),
        "credit_balances": _count_glob(root / "credit_ledger", "*.balance.json"),
        "entitlements": ents_n,
        "entitlement_events": _count_glob(root / "entitlements" / "processed_events", "*.json"),
    }
    # credit ledger entry lines
    entries = 0
    ledger_dir = root / "credit_ledger"
    if ledger_dir.is_dir():
        for path in ledger_dir.glob("*.jsonl"):
            entries += sum(1 for line in path.read_text(encoding="utf-8").splitlines() if line.strip())
    file_counts["credit_entries"] = entries

    try:
        with whatsapp_session(require=True) as session:
            pg_counts = {
                "wallets": session.scalar(select(func.count()).select_from(TokenWalletRow)) or 0,
                "stripe_events": session.scalar(select(func.count()).select_from(StripeProcessedEventRow)) or 0,
                "admin_credit": session.scalar(select(func.count()).select_from(AdminCreditIdempotencyRow)) or 0,
                "mobile_refresh": session.scalar(select(func.count()).select_from(MobileRefreshTokenRow)) or 0,
                "auth_email": session.scalar(select(func.count()).select_from(AuthEmailTokenRow)) or 0,
                "credit_balances": session.scalar(select(func.count()).select_from(CreditBalanceRow)) or 0,
                "credit_entries": session.scalar(select(func.count()).select_from(CreditLedgerEntryRow)) or 0,
                "entitlements": session.scalar(select(func.count()).select_from(TenantEntitlementRow)) or 0,
                "entitlement_events": session.scalar(select(func.count()).select_from(EntitlementProcessedEventRow))
                or 0,
            }
    except WhatsAppDatabaseUnavailable as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    print(json.dumps({"file": file_counts, "postgres": pg_counts}, indent=2, sort_keys=True))
    mismatches = []
    for key, file_n in file_counts.items():
        pg_n = int(pg_counts.get(key) or 0)
        if file_n > pg_n:
            mismatches.append(f"{key}: file={file_n} pg={pg_n}")
    if mismatches:
        print("mismatches (file ahead of pg):", "; ".join(mismatches), file=sys.stderr)
        if args.strict:
            return 1
    else:
        print("parity_ok: postgres counts >= file counts for all keys")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
