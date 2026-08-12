#!/usr/bin/env python3
"""Import file-backed billing + auth token stores into Postgres (idempotent).

Reads wallets, ledgers, Stripe events, admin credit idempotency, mobile refresh
tokens, and auth email tokens from _DATA_ROOT file paths, upserts into Postgres.
Does not change LINAS_BILLING_BACKEND or LINAS_AUTH_TOKEN_BACKEND.

Usage:
  python scripts/ha/import_billing_auth_to_postgres.py [--dry-run]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _data_root() -> Path:
    from storage.persistent_storage import _DATA_ROOT

    return Path(_DATA_ROOT)


def _import_wallets(session: Session, wallets_dir: Path, dry_run: bool) -> tuple[int, int]:
    from services.token_wallet_file_store import TokenWalletFileStore
    from services.token_wallet_pg_store import import_ledger_lines, upsert_wallet_from_file_dict

    store = TokenWalletFileStore(wallets_dir)
    wallet_count = 0
    ledger_count = 0
    for path in store.iter_wallet_files():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(data, dict):
            continue
        tenant_id = str(data.get("tenant_id") or path.stem).strip().lower()
        if not tenant_id:
            continue
        if dry_run:
            wallet_count += 1
        else:
            upsert_wallet_from_file_dict(session, {**data, "tenant_id": tenant_id})
            wallet_count += 1
        ledger_path = store._ledger_dir / f"{tenant_id}.jsonl"
        if ledger_path.is_file() and not dry_run:
            lines = ledger_path.read_text(encoding="utf-8").splitlines()
            ledger_count += import_ledger_lines(session, tenant_id, lines)
        elif ledger_path.is_file():
            ledger_count += sum(1 for line in ledger_path.read_text(encoding="utf-8").splitlines() if line.strip())
    return wallet_count, ledger_count


def _import_stripe_events(session: Session, events_dir: Path, dry_run: bool) -> int:
    from services.billing_pg_store import import_stripe_event

    count = 0
    if not events_dir.is_dir():
        return 0
    for path in sorted(events_dir.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(data, dict):
            continue
        event_id = str(data.get("event_id") or "").strip()
        if not event_id:
            continue
        created_at = float(data.get("ts") or 0)
        meta = dict(data.get("meta") or {})
        if dry_run:
            count += 1
        elif import_stripe_event(session, event_id, created_at, meta):
            count += 1
    return count


def _import_admin_credit(session: Session, idem_dir: Path, dry_run: bool) -> int:
    from services.billing_pg_store import import_admin_credit_key

    count = 0
    if not idem_dir.is_dir():
        return 0
    for path in sorted(idem_dir.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(data, dict):
            continue
        key = str(data.get("idempotency_key") or "").strip()
        if not key:
            digest = path.stem
            key = digest
        created_at = float(data.get("ts") or 0)
        if dry_run:
            count += 1
        elif import_admin_credit_key(session, key, created_at, data):
            count += 1
    return count


def _import_mobile_refresh(session: Session, refresh_dir: Path, dry_run: bool) -> int:
    from services.auth_token_pg_store import upsert_mobile_refresh

    count = 0
    if not refresh_dir.is_dir():
        return 0
    for path in sorted(refresh_dir.glob("*.json")):
        token_hash = path.stem
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(data, dict):
            continue
        if dry_run:
            count += 1
        else:
            upsert_mobile_refresh(session, token_hash, data)
            count += 1
    return count


def _import_auth_email(session: Session, tokens_dir: Path, dry_run: bool) -> int:
    from services.auth_token_pg_store import upsert_auth_email_token

    count = 0
    if not tokens_dir.is_dir():
        return 0
    for path in sorted(tokens_dir.glob("*.json")):
        token_hash = path.stem
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(data, dict):
            continue
        if dry_run:
            count += 1
        else:
            upsert_auth_email_token(session, token_hash, data)
            count += 1
    return count


def _import_credit_ledger(session: Session, ledger_dir: Path, dry_run: bool) -> tuple[int, int]:
    from services.credit_ledger_pg_store import import_balance, import_entry

    balances = 0
    entries = 0
    if not ledger_dir.is_dir():
        return 0, 0
    for path in sorted(ledger_dir.glob("*.balance.json")):
        tenant_id = path.name.replace(".balance.json", "")
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(data, dict):
            continue
        if dry_run:
            balances += 1
        else:
            import_balance(
                session,
                tenant_id,
                int(data.get("available") or 0),
                int(data.get("reserved") or 0),
                float(data.get("updated_at") or 0),
            )
            balances += 1
        log_path = ledger_dir / f"{tenant_id}.jsonl"
        if log_path.is_file():
            for line in log_path.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                try:
                    entry = json.loads(line)
                except Exception:
                    continue
                if not isinstance(entry, dict):
                    continue
                if dry_run:
                    entries += 1
                elif import_entry(session, entry):
                    entries += 1
    return balances, entries


def _import_entitlements(session: Session, ents_dir: Path, dry_run: bool) -> tuple[int, int]:
    from services.entitlements_pg_store import import_entitlement, import_processed_event

    ents = 0
    events = 0
    if not ents_dir.is_dir():
        return 0, 0
    for path in sorted(ents_dir.glob("*.json")):
        if path.parent.name == "processed_events":
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(data, dict):
            continue
        if dry_run:
            ents += 1
        elif import_entitlement(session, data):
            ents += 1
    processed = ents_dir / "processed_events"
    if processed.is_dir():
        for path in sorted(processed.glob("*.json")):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                continue
            if not isinstance(data, dict):
                continue
            key = str(data.get("event_id") or path.stem).strip()
            tenant_id = str(data.get("tenant_id") or "").strip() or "unknown"
            if dry_run:
                events += 1
            elif import_processed_event(
                session,
                idempotency_key=key,
                tenant_id=tenant_id,
                created_at=float(data.get("ts") or 0),
                meta=data,
            ):
                events += 1
    return ents, events


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="Count records only; no writes")
    args = parser.parse_args(argv)

    root = _data_root()
    wallets_dir = root / "billing" / "wallets"
    stripe_dir = root / "billing" / "stripe_events"
    admin_dir = root / "billing" / "admin_credit_idempotency"
    refresh_dir = root / "auth" / "mobile_refresh"
    email_dir = root / "auth" / "email_tokens"
    credit_dir = root / "credit_ledger"
    ents_dir = root / "entitlements"

    print(f"data_root={root} dry_run={args.dry_run}")

    from db.session import WhatsAppDatabaseUnavailable, whatsapp_session

    try:
        with whatsapp_session(require=True) as session:
            wallets, ledger = _import_wallets(session, wallets_dir, args.dry_run)
            stripe = _import_stripe_events(session, stripe_dir, args.dry_run)
            admin = _import_admin_credit(session, admin_dir, args.dry_run)
            mobile = _import_mobile_refresh(session, refresh_dir, args.dry_run)
            email = _import_auth_email(session, email_dir, args.dry_run)
            credit_balances, credit_entries = _import_credit_ledger(session, credit_dir, args.dry_run)
            ents, ent_events = _import_entitlements(session, ents_dir, args.dry_run)
            if args.dry_run:
                session.rollback()
    except WhatsAppDatabaseUnavailable as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    print(
        f"wallets={wallets} ledger_lines={ledger} stripe_events={stripe} "
        f"admin_credit_keys={admin} mobile_refresh={mobile} auth_email={email} "
        f"credit_balances={credit_balances} credit_entries={credit_entries} "
        f"entitlements={ents} entitlement_events={ent_events}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
