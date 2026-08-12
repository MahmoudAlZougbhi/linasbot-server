"""Postgres token wallet + ledger persistence."""

from __future__ import annotations

import json
import time
import uuid
from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from db.models.billing_auth import TokenWalletLedgerRow, TokenWalletRow
from services.token_wallet_file_store import TokenWalletFileStore


def _row_to_dict(row: TokenWalletRow) -> dict[str, Any]:
    return {
        "tenant_id": row.tenant_id,
        "input_remaining": int(row.input_remaining or 0),
        "output_remaining": int(row.output_remaining or 0),
        "lifetime_input_credited": int(row.lifetime_input_credited or 0),
        "lifetime_output_credited": int(row.lifetime_output_credited or 0),
        "lifetime_input_debited": int(row.lifetime_input_debited or 0),
        "lifetime_output_debited": int(row.lifetime_output_debited or 0),
        "lifetime_spent_usd": float(row.lifetime_spent_usd or 0.0),
        "balance_tokens": int(row.balance_tokens or 0),
        "lifetime_credited": int(row.lifetime_credited or 0),
        "lifetime_debited": int(row.lifetime_debited or 0),
        "schema_version": int(row.schema_version or 2),
        "migrated_from_legacy": bool(row.migrated_from_legacy),
        "migration_note": row.migration_note,
        "legacy_balance_tokens_before_migration": row.legacy_balance_tokens_before_migration,
        "updated_at": float(row.updated_at or time.time()),
    }


def _apply_payload_to_row(row: TokenWalletRow, data: dict[str, Any]) -> None:
    normalized = TokenWalletFileStore().normalize_wallet_payload(data)
    row.input_remaining = normalized["input_remaining"]
    row.output_remaining = normalized["output_remaining"]
    row.lifetime_input_credited = int(normalized.get("lifetime_input_credited") or 0)
    row.lifetime_output_credited = int(normalized.get("lifetime_output_credited") or 0)
    row.lifetime_input_debited = int(normalized.get("lifetime_input_debited") or 0)
    row.lifetime_output_debited = int(normalized.get("lifetime_output_debited") or 0)
    row.lifetime_spent_usd = float(normalized.get("lifetime_spent_usd") or 0.0)
    row.balance_tokens = normalized["balance_tokens"]
    row.lifetime_credited = normalized["lifetime_credited"]
    row.lifetime_debited = normalized["lifetime_debited"]
    row.schema_version = 2
    row.migrated_from_legacy = bool(normalized.get("migrated_from_legacy"))
    row.migration_note = normalized.get("migration_note")
    row.legacy_balance_tokens_before_migration = normalized.get("legacy_balance_tokens_before_migration")
    row.updated_at = normalized["updated_at"]


def read_wallet(session: Session, tenant_id: str) -> dict[str, Any]:
    row = session.get(TokenWalletRow, tenant_id)
    if row is None:
        return TokenWalletFileStore().empty_wallet(tenant_id)
    return _row_to_dict(row)


def write_wallet(session: Session, tenant_id: str, data: dict[str, Any]) -> dict[str, Any]:
    row = session.get(TokenWalletRow, tenant_id)
    if row is None:
        row = TokenWalletRow(tenant_id=tenant_id)
        session.add(row)
    _apply_payload_to_row(row, data)
    session.flush()
    return _row_to_dict(row)


def append_ledger(session: Session, entry: dict[str, Any]) -> None:
    entry_id = str(entry.get("id") or uuid.uuid4())
    created_at = float(entry.get("ts") or entry.get("created_at") or time.time())
    tenant_id = str(entry.get("tenant_id") or "unknown")
    session.add(
        TokenWalletLedgerRow(
            id=entry_id,
            tenant_id=tenant_id,
            created_at=created_at,
            payload=dict(entry),
        )
    )
    session.flush()


def recent_ledger(session: Session, tenant_id: str, *, limit: int = 50) -> list[dict[str, Any]]:
    rows = session.scalars(
        select(TokenWalletLedgerRow)
        .where(TokenWalletLedgerRow.tenant_id == tenant_id)
        .order_by(desc(TokenWalletLedgerRow.created_at))
        .limit(max(1, limit))
    ).all()
    return [dict(row.payload or {}) for row in rows]


def upsert_wallet_from_file_dict(session: Session, data: dict[str, Any]) -> None:
    tenant_id = str(data.get("tenant_id") or "").strip().lower()
    if not tenant_id:
        return
    write_wallet(session, tenant_id, data)


def import_ledger_lines(session: Session, tenant_id: str, lines: list[str]) -> int:
    imported = 0
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except Exception:
            continue
        if not isinstance(entry, dict):
            continue
        entry_id = str(entry.get("id") or uuid.uuid4())
        existing = session.get(TokenWalletLedgerRow, entry_id)
        if existing is not None:
            continue
        append_ledger(session, {**entry, "tenant_id": tenant_id, "id": entry_id})
        imported += 1
    return imported
