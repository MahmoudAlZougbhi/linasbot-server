"""Tenant prepaid token wallet with separate input + output balances.

Policy (fail closed):
  - Pre-flight: AI may start only when input_remaining >= 1 AND output_remaining >= 1
    (both buckets must have remaining allowance).
  - Post-call debit: prompt_tokens → input bucket, completion_tokens → output bucket.
  - Never go negative; raise InsufficientTokenBalance if either bucket cannot cover.

Legacy single-balance wallets are migrated once on read:
    remaining balance_tokens is split 80% input / 20% output (same historical prepaid
    assumption), with an explicit migration note on the wallet record.

Persistence via LINAS_BILLING_BACKEND=file|postgres (default file).
Models/helpers: token_wallet_models (LOC split).
"""

from __future__ import annotations

import threading
import time
import uuid
from pathlib import Path
from typing import Any

from services.billing_backend import billing_uses_postgres
from services.token_wallet_file_store import TokenWalletFileStore
from services.token_wallet_models import (  # noqa: F401
    DEFAULT_UNLIMITED_TENANTS,
    LEGACY_INPUT_SHARE,
    LEGACY_OUTPUT_SHARE,
    MIGRATION_NOTE,
    InsufficientTokenBalance,
    WalletSnapshot,
    is_unlimited_tenant,
    normalize_wallet_tenant_id,
    unlimited_tenant_ids,
)


class TokenWalletService:
    def __init__(self, store_dir: Path | None = None, *, file_store: TokenWalletFileStore | None = None) -> None:
        self._lock = threading.RLock()
        self._file = file_store or TokenWalletFileStore(store_dir)

    def _read(self, tenant_id: str) -> dict[str, Any]:
        if billing_uses_postgres():
            from db.session import whatsapp_session
            from services.token_wallet_pg_store import read_wallet

            with whatsapp_session() as session:
                data = read_wallet(session, tenant_id)
        else:
            with self._lock:
                data = self._file.read(tenant_id)

        migrated = self._file.migrate_legacy_if_needed(tenant_id, data)
        if migrated.get("migrated_from_legacy") and data.get("schema_version") != 2:
            self._persist_wallet(tenant_id, migrated, migration_ledger=True)
            return migrated
        return migrated

    def _persist_wallet(self, tenant_id: str, data: dict[str, Any], *, migration_ledger: bool = False) -> None:
        if billing_uses_postgres():
            from db.session import whatsapp_session
            from services.token_wallet_pg_store import append_ledger, write_wallet

            with whatsapp_session() as session:
                write_wallet(session, tenant_id, data)
                if migration_ledger:
                    append_ledger(
                        session,
                        {
                            "id": str(uuid.uuid4()),
                            "ts": time.time(),
                            "tenant_id": tenant_id,
                            "type": "migration_legacy_split",
                            "input_tokens": data["input_remaining"],
                            "output_tokens": data["output_remaining"],
                            "reason": "legacy_balance_80_20_split",
                            "note": MIGRATION_NOTE,
                            "legacy_balance_tokens": data.get("legacy_balance_tokens_before_migration"),
                        },
                    )
        else:
            with self._lock:
                self._file.write(tenant_id, data)
                if migration_ledger:
                    self._file.persist_legacy_migration(tenant_id, data)

    def _write(self, tenant_id: str, data: dict[str, Any]) -> None:
        self._persist_wallet(tenant_id, data)

    def _append_ledger(self, entry: dict[str, Any]) -> None:
        if billing_uses_postgres():
            from db.session import whatsapp_session
            from services.token_wallet_pg_store import append_ledger

            with whatsapp_session() as session:
                append_ledger(session, entry)
        else:
            with self._lock:
                self._file.append_ledger(entry)

    def get_wallet(self, tenant_id: str) -> WalletSnapshot:
        tid = normalize_wallet_tenant_id(tenant_id)
        unlimited = is_unlimited_tenant(tid)
        data = self._read(tid)
        return WalletSnapshot(
            tenant_id=tid,
            input_remaining=int(data.get("input_remaining") or 0),
            output_remaining=int(data.get("output_remaining") or 0),
            lifetime_input_credited=int(data.get("lifetime_input_credited") or 0),
            lifetime_output_credited=int(data.get("lifetime_output_credited") or 0),
            lifetime_input_debited=int(data.get("lifetime_input_debited") or 0),
            lifetime_output_debited=int(data.get("lifetime_output_debited") or 0),
            lifetime_spent_usd=float(data.get("lifetime_spent_usd") or 0.0),
            unlimited=unlimited,
            updated_at=float(data.get("updated_at") or time.time()),
            migrated_from_legacy=bool(data.get("migrated_from_legacy")),
        )

    def ensure_ai_allowed(self, tenant_id: str, *, require_at_least: int = 1) -> WalletSnapshot:
        snap = self.get_wallet(tenant_id)
        if snap.unlimited:
            return snap
        need = max(1, int(require_at_least))
        if snap.input_remaining < need:
            raise InsufficientTokenBalance(
                snap.tenant_id,
                snap.input_remaining,
                need,
                bucket="input",
                input_remaining=snap.input_remaining,
                output_remaining=snap.output_remaining,
            )
        if snap.output_remaining < need:
            raise InsufficientTokenBalance(
                snap.tenant_id,
                snap.output_remaining,
                need,
                bucket="output",
                input_remaining=snap.input_remaining,
                output_remaining=snap.output_remaining,
            )
        return snap

    def credit(
        self,
        tenant_id: str,
        tokens: int | None = None,
        *,
        input_tokens: int | None = None,
        output_tokens: int | None = None,
        amount_usd: float = 0.0,
        reason: str,
        reference: str | None = None,
        package_id: str | None = None,
        actor: str | None = None,
    ) -> WalletSnapshot:
        tid = normalize_wallet_tenant_id(tenant_id)

        if input_tokens is not None or output_tokens is not None:
            add_in = max(0, int(input_tokens or 0))
            add_out = max(0, int(output_tokens or 0))
        else:
            total = int(tokens or 0)
            if total <= 0:
                raise ValueError("tokens must be positive")
            add_in = int(round(total * LEGACY_INPUT_SHARE))
            add_out = max(0, total - add_in)

        if add_in <= 0 and add_out <= 0:
            raise ValueError("input_tokens or output_tokens must be positive")

        if billing_uses_postgres():
            from db.session import whatsapp_session
            from services.token_wallet_pg_store import append_ledger, read_wallet, write_wallet

            with whatsapp_session() as session:
                data = read_wallet(session, tid)
                data = self._file.migrate_legacy_if_needed(tid, data)
                before_in = int(data.get("input_remaining") or 0)
                before_out = int(data.get("output_remaining") or 0)
                data["input_remaining"] = before_in + add_in
                data["output_remaining"] = before_out + add_out
                data["lifetime_input_credited"] = int(data.get("lifetime_input_credited") or 0) + add_in
                data["lifetime_output_credited"] = int(data.get("lifetime_output_credited") or 0) + add_out
                if amount_usd and amount_usd > 0:
                    data["lifetime_spent_usd"] = float(data.get("lifetime_spent_usd") or 0.0) + float(amount_usd)
                write_wallet(session, tid, data)
                append_ledger(
                    session,
                    {
                        "id": str(uuid.uuid4()),
                        "ts": time.time(),
                        "tenant_id": tid,
                        "type": "credit",
                        "input_tokens": add_in,
                        "output_tokens": add_out,
                        "tokens": add_in + add_out,
                        "amount_usd": float(amount_usd or 0.0),
                        "reason": reason,
                        "reference": reference,
                        "package_id": package_id,
                        "actor": actor,
                        "input_remaining_before": before_in,
                        "output_remaining_before": before_out,
                        "balance_before": before_in + before_out,
                        "input_remaining_after": data["input_remaining"],
                        "output_remaining_after": data["output_remaining"],
                        "balance_after": data["input_remaining"] + data["output_remaining"],
                    },
                )
        else:
            with self._lock:
                data = self._file.read(tid)
                data = self._file.migrate_legacy_if_needed(tid, data)
                before_in = int(data.get("input_remaining") or 0)
                before_out = int(data.get("output_remaining") or 0)
                data["input_remaining"] = before_in + add_in
                data["output_remaining"] = before_out + add_out
                data["lifetime_input_credited"] = int(data.get("lifetime_input_credited") or 0) + add_in
                data["lifetime_output_credited"] = int(data.get("lifetime_output_credited") or 0) + add_out
                if amount_usd and amount_usd > 0:
                    data["lifetime_spent_usd"] = float(data.get("lifetime_spent_usd") or 0.0) + float(amount_usd)
                self._file.write(tid, data)
                self._file.append_ledger(
                    {
                        "id": str(uuid.uuid4()),
                        "ts": time.time(),
                        "tenant_id": tid,
                        "type": "credit",
                        "input_tokens": add_in,
                        "output_tokens": add_out,
                        "tokens": add_in + add_out,
                        "amount_usd": float(amount_usd or 0.0),
                        "reason": reason,
                        "reference": reference,
                        "package_id": package_id,
                        "actor": actor,
                        "input_remaining_before": before_in,
                        "output_remaining_before": before_out,
                        "balance_before": before_in + before_out,
                        "input_remaining_after": data["input_remaining"],
                        "output_remaining_after": data["output_remaining"],
                        "balance_after": data["input_remaining"] + data["output_remaining"],
                    }
                )
        return self.get_wallet(tid)

    def debit(
        self,
        tenant_id: str,
        tokens: int | None = None,
        *,
        prompt_tokens: int | None = None,
        completion_tokens: int | None = None,
        cost_usd: float = 0.0,
        input_cost_usd: float = 0.0,
        output_cost_usd: float = 0.0,
        reason: str = "ai_usage",
        reference: str | None = None,
        model: str | None = None,
    ) -> WalletSnapshot:
        tid = normalize_wallet_tenant_id(tenant_id)

        if prompt_tokens is not None or completion_tokens is not None:
            use_in = max(0, int(prompt_tokens or 0))
            use_out = max(0, int(completion_tokens or 0))
        elif tokens is not None:
            total = max(0, int(tokens))
            use_in = int(round(total * LEGACY_INPUT_SHARE))
            use_out = max(0, total - use_in)
        else:
            use_in = 0
            use_out = 0

        if use_in <= 0 and use_out <= 0:
            return self.get_wallet(tid)

        entry_type = "debit_unlimited" if is_unlimited_tenant(tid) else "debit"

        def _apply(data: dict[str, Any]) -> dict[str, Any]:
            if not is_unlimited_tenant(tid):
                input_bal = int(data.get("input_remaining") or 0)
                output_bal = int(data.get("output_remaining") or 0)
                if use_in > input_bal:
                    raise InsufficientTokenBalance(
                        tid,
                        input_bal,
                        use_in,
                        bucket="input",
                        input_remaining=input_bal,
                        output_remaining=output_bal,
                    )
                if use_out > output_bal:
                    raise InsufficientTokenBalance(
                        tid,
                        output_bal,
                        use_out,
                        bucket="output",
                        input_remaining=input_bal,
                        output_remaining=output_bal,
                    )
                data["input_remaining"] = input_bal - use_in
                data["output_remaining"] = output_bal - use_out
            data["lifetime_input_debited"] = int(data.get("lifetime_input_debited") or 0) + use_in
            data["lifetime_output_debited"] = int(data.get("lifetime_output_debited") or 0) + use_out
            return data

        ledger_entry = {
            "id": str(uuid.uuid4()),
            "ts": time.time(),
            "tenant_id": tid,
            "type": entry_type,
            "input_tokens": use_in,
            "output_tokens": use_out,
            "tokens": use_in + use_out,
            "cost_usd": float(cost_usd or 0.0),
            "input_cost_usd": float(input_cost_usd or 0.0),
            "output_cost_usd": float(output_cost_usd or 0.0),
            "reason": reason,
            "reference": reference,
            "model": model,
        }

        if billing_uses_postgres():
            from db.session import whatsapp_session
            from services.token_wallet_pg_store import append_ledger, read_wallet, write_wallet

            with whatsapp_session() as session:
                data = read_wallet(session, tid)
                data = self._file.migrate_legacy_if_needed(tid, data)
                data = _apply(data)
                ledger_entry["input_remaining_after"] = data.get("input_remaining", 0)
                ledger_entry["output_remaining_after"] = data.get("output_remaining", 0)
                ledger_entry["balance_after"] = int(data.get("input_remaining") or 0) + int(
                    data.get("output_remaining") or 0
                )
                write_wallet(session, tid, data)
                append_ledger(session, ledger_entry)
        else:
            with self._lock:
                data = self._file.read(tid)
                data = self._file.migrate_legacy_if_needed(tid, data)
                data = _apply(data)
                ledger_entry["input_remaining_after"] = data.get("input_remaining", 0)
                ledger_entry["output_remaining_after"] = data.get("output_remaining", 0)
                ledger_entry["balance_after"] = int(data.get("input_remaining") or 0) + int(
                    data.get("output_remaining") or 0
                )
                self._file.write(tid, data)
                self._file.append_ledger(ledger_entry)

        return self.get_wallet(tid)

    def recent_ledger(self, tenant_id: str, *, limit: int = 50) -> list[dict[str, Any]]:
        tid = normalize_wallet_tenant_id(tenant_id)
        if billing_uses_postgres():
            from db.session import whatsapp_session
            from services.token_wallet_pg_store import recent_ledger

            with whatsapp_session() as session:
                return recent_ledger(session, tid, limit=limit)
        return self._file.recent_ledger(tid, limit=limit)


token_wallet_service = TokenWalletService()
