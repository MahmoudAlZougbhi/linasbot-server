"""Tenant prepaid token wallet with separate input + output balances.

Policy (fail closed):
  - Pre-flight: AI may start only when input_remaining >= 1 AND output_remaining >= 1
    (both buckets must have remaining allowance).
  - Post-call debit: prompt_tokens → input bucket, completion_tokens → output bucket.
  - Never go negative; raise InsufficientTokenBalance if either bucket cannot cover.

Legacy single-balance wallets are migrated once on read:
  remaining balance_tokens is split 80% input / 20% output (same historical prepaid
  assumption), with an explicit migration note on the wallet record.
"""

from __future__ import annotations

import json
import os
import threading
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from storage.persistent_storage import _DATA_ROOT

DEFAULT_UNLIMITED_TENANTS = frozenset({"linas"})

# One-time legacy split (documented; do not invent other ratios).
LEGACY_INPUT_SHARE = 0.80
LEGACY_OUTPUT_SHARE = 0.20
MIGRATION_NOTE = (
    "Migrated from legacy single balance_tokens: remaining split "
    f"{int(LEGACY_INPUT_SHARE * 100)}% input / {int(LEGACY_OUTPUT_SHARE * 100)}% output."
)


class InsufficientTokenBalance(Exception):
    """Raised when a metered tenant cannot cover an AI token debit."""

    def __init__(
        self,
        tenant_id: str,
        balance: int,
        required: int,
        *,
        bucket: str | None = None,
        input_remaining: int | None = None,
        output_remaining: int | None = None,
    ) -> None:
        self.tenant_id = tenant_id
        self.balance = balance
        self.required = required
        self.bucket = bucket
        self.input_remaining = input_remaining
        self.output_remaining = output_remaining
        detail = f"Insufficient token balance for tenant={tenant_id}"
        if bucket:
            detail += f" bucket={bucket}"
        detail += f" balance={balance} required={required}"
        super().__init__(detail)


def unlimited_tenant_ids() -> frozenset[str]:
    raw = (os.getenv("TOKEN_WALLET_UNLIMITED_TENANT_IDS") or "linas").strip()
    ids = {part.strip().lower() for part in raw.split(",") if part.strip()}
    return frozenset(ids or DEFAULT_UNLIMITED_TENANTS)


def is_unlimited_tenant(tenant_id: str | None) -> bool:
    tid = (tenant_id or "").strip().lower() or "linas"
    return tid in unlimited_tenant_ids()


@dataclass
class WalletSnapshot:
    tenant_id: str
    input_remaining: int
    output_remaining: int
    lifetime_input_credited: int
    lifetime_output_credited: int
    lifetime_input_debited: int
    lifetime_output_debited: int
    lifetime_spent_usd: float
    unlimited: bool
    updated_at: float
    migrated_from_legacy: bool = False

    @property
    def balance_tokens(self) -> int:
        return int(self.input_remaining) + int(self.output_remaining)

    @property
    def lifetime_credited(self) -> int:
        return int(self.lifetime_input_credited) + int(self.lifetime_output_credited)

    @property
    def lifetime_debited(self) -> int:
        return int(self.lifetime_input_debited) + int(self.lifetime_output_debited)

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "tenant_id": self.tenant_id,
            "input_remaining": self.input_remaining,
            "output_remaining": self.output_remaining,
            "input_used": self.lifetime_input_debited,
            "output_used": self.lifetime_output_debited,
            "lifetime_input_credited": self.lifetime_input_credited,
            "lifetime_output_credited": self.lifetime_output_credited,
            "lifetime_input_debited": self.lifetime_input_debited,
            "lifetime_output_debited": self.lifetime_output_debited,
            "lifetime_spent_usd": round(self.lifetime_spent_usd, 6),
            # Legacy-compatible totals (sum of both buckets).
            "balance_tokens": self.balance_tokens,
            "lifetime_credited": self.lifetime_credited,
            "lifetime_debited": self.lifetime_debited,
            "tokens_used": self.lifetime_debited,
            "tokens_remaining": self.balance_tokens,
            "unlimited": self.unlimited,
            "updated_at": self.updated_at,
            "migrated_from_legacy": self.migrated_from_legacy,
            "policy": (
                "AI pauses when either the input or output balance is empty. "
                "Each AI call debits prompt tokens from input and completion tokens from output."
            ),
        }


class TokenWalletService:
    def __init__(self, store_dir: Path | None = None) -> None:
        self._lock = threading.RLock()
        self._store_dir = store_dir or (Path(_DATA_ROOT) / "billing" / "wallets")
        self._store_dir.mkdir(parents=True, exist_ok=True)
        self._ledger_dir = self._store_dir / "ledger"
        self._ledger_dir.mkdir(parents=True, exist_ok=True)

    def _wallet_path(self, tenant_id: str) -> Path:
        safe = (tenant_id or "unknown").strip().lower().replace("/", "_")
        return self._store_dir / f"{safe}.json"

    def _empty(self, tenant_id: str) -> dict[str, Any]:
        return {
            "tenant_id": tenant_id,
            "input_remaining": 0,
            "output_remaining": 0,
            "lifetime_input_credited": 0,
            "lifetime_output_credited": 0,
            "lifetime_input_debited": 0,
            "lifetime_output_debited": 0,
            "lifetime_spent_usd": 0.0,
            # Kept as derived convenience for older readers.
            "balance_tokens": 0,
            "lifetime_credited": 0,
            "lifetime_debited": 0,
            "updated_at": time.time(),
            "schema_version": 2,
        }

    def _migrate_legacy_if_needed(self, tenant_id: str, data: dict[str, Any]) -> dict[str, Any]:
        """Split legacy balance_tokens once into input/output buckets (80/20)."""
        if data.get("schema_version") == 2 and "input_remaining" in data and "output_remaining" in data:
            # Keep balance_tokens in sync.
            data["balance_tokens"] = int(data.get("input_remaining") or 0) + int(data.get("output_remaining") or 0)
            data["lifetime_credited"] = int(data.get("lifetime_input_credited") or 0) + int(
                data.get("lifetime_output_credited") or 0
            )
            data["lifetime_debited"] = int(data.get("lifetime_input_debited") or 0) + int(
                data.get("lifetime_output_debited") or 0
            )
            return data

        legacy_balance = int(data.get("balance_tokens") or 0)
        # Already has dual fields from a partial write.
        if "input_remaining" in data and "output_remaining" in data and data.get("schema_version") == 2:
            return data

        input_rem = int(round(legacy_balance * LEGACY_INPUT_SHARE))
        output_rem = max(0, legacy_balance - input_rem)
        legacy_credited = int(data.get("lifetime_credited") or 0)
        legacy_debited = int(data.get("lifetime_debited") or 0)
        input_credited = int(round(legacy_credited * LEGACY_INPUT_SHARE))
        output_credited = max(0, legacy_credited - input_credited)
        input_debited = int(round(legacy_debited * LEGACY_INPUT_SHARE))
        output_debited = max(0, legacy_debited - input_debited)

        migrated = {
            "tenant_id": tenant_id,
            "input_remaining": input_rem,
            "output_remaining": output_rem,
            "lifetime_input_credited": input_credited,
            "lifetime_output_credited": output_credited,
            "lifetime_input_debited": input_debited,
            "lifetime_output_debited": output_debited,
            "lifetime_spent_usd": float(data.get("lifetime_spent_usd") or 0.0),
            "balance_tokens": input_rem + output_rem,
            "lifetime_credited": input_credited + output_credited,
            "lifetime_debited": input_debited + output_debited,
            "updated_at": time.time(),
            "schema_version": 2,
            "migrated_from_legacy": True,
            "migration_note": MIGRATION_NOTE,
            "legacy_balance_tokens_before_migration": legacy_balance,
        }
        return migrated

    def _read(self, tenant_id: str) -> dict[str, Any]:
        path = self._wallet_path(tenant_id)
        if not path.exists():
            return self._empty(tenant_id)
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                return self._empty(tenant_id)
            data.setdefault("tenant_id", tenant_id)
            migrated = self._migrate_legacy_if_needed(tenant_id, data)
            # Persist migration so it happens once.
            if migrated.get("migrated_from_legacy") and data.get("schema_version") != 2:
                self._write(tenant_id, migrated)
                self._append_ledger(
                    {
                        "id": str(uuid.uuid4()),
                        "ts": time.time(),
                        "tenant_id": tenant_id,
                        "type": "migration_legacy_split",
                        "input_tokens": migrated["input_remaining"],
                        "output_tokens": migrated["output_remaining"],
                        "reason": "legacy_balance_80_20_split",
                        "note": MIGRATION_NOTE,
                        "legacy_balance_tokens": migrated.get("legacy_balance_tokens_before_migration"),
                    }
                )
            return migrated
        except Exception:
            return self._empty(tenant_id)

    def _write(self, tenant_id: str, data: dict[str, Any]) -> None:
        path = self._wallet_path(tenant_id)
        tmp = path.with_suffix(".tmp")
        payload = dict(data)
        payload["schema_version"] = 2
        payload["input_remaining"] = int(payload.get("input_remaining") or 0)
        payload["output_remaining"] = int(payload.get("output_remaining") or 0)
        payload["balance_tokens"] = payload["input_remaining"] + payload["output_remaining"]
        payload["lifetime_credited"] = int(payload.get("lifetime_input_credited") or 0) + int(
            payload.get("lifetime_output_credited") or 0
        )
        payload["lifetime_debited"] = int(payload.get("lifetime_input_debited") or 0) + int(
            payload.get("lifetime_output_debited") or 0
        )
        payload["updated_at"] = time.time()
        tmp.write_text(json.dumps(payload), encoding="utf-8")
        tmp.replace(path)

    def _append_ledger(self, entry: dict[str, Any]) -> None:
        tenant_id = str(entry.get("tenant_id") or "unknown")
        path = self._ledger_dir / f"{tenant_id}.jsonl"
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry) + "\n")

    def get_wallet(self, tenant_id: str) -> WalletSnapshot:
        tid = (tenant_id or "").strip().lower() or "linas"
        unlimited = is_unlimited_tenant(tid)
        with self._lock:
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
        """Fail closed when either input or output bucket is empty."""
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
        """
        Credit input and/or output allotments.

        Prefer explicit input_tokens/output_tokens. Legacy ``tokens`` alone is
        split 80/20 for admin credits that still pass a single total.
        """
        tid = (tenant_id or "").strip().lower()
        if not tid:
            raise ValueError("tenant_id required")

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

        with self._lock:
            data = self._read(tid)
            before_in = int(data.get("input_remaining") or 0)
            before_out = int(data.get("output_remaining") or 0)
            data["input_remaining"] = before_in + add_in
            data["output_remaining"] = before_out + add_out
            data["lifetime_input_credited"] = int(data.get("lifetime_input_credited") or 0) + add_in
            data["lifetime_output_credited"] = int(data.get("lifetime_output_credited") or 0) + add_out
            if amount_usd and amount_usd > 0:
                data["lifetime_spent_usd"] = float(data.get("lifetime_spent_usd") or 0.0) + float(amount_usd)
            self._write(tid, data)
            self._append_ledger(
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
        """
        Atomically debit input (prompt) and output (completion) buckets.
        Unlimited tenants record usage without blocking.
        Never allows negative balances (fail closed).
        """
        tid = (tenant_id or "").strip().lower() or "linas"

        if prompt_tokens is not None or completion_tokens is not None:
            use_in = max(0, int(prompt_tokens or 0))
            use_out = max(0, int(completion_tokens or 0))
        elif tokens is not None:
            # Legacy single-total debit: split 80/20 like old metering.
            total = max(0, int(tokens))
            use_in = int(round(total * LEGACY_INPUT_SHARE))
            use_out = max(0, total - use_in)
        else:
            use_in = 0
            use_out = 0

        if use_in <= 0 and use_out <= 0:
            return self.get_wallet(tid)

        if is_unlimited_tenant(tid):
            with self._lock:
                data = self._read(tid)
                data["lifetime_input_debited"] = int(data.get("lifetime_input_debited") or 0) + use_in
                data["lifetime_output_debited"] = int(data.get("lifetime_output_debited") or 0) + use_out
                self._write(tid, data)
                self._append_ledger(
                    {
                        "id": str(uuid.uuid4()),
                        "ts": time.time(),
                        "tenant_id": tid,
                        "type": "debit_unlimited",
                        "input_tokens": use_in,
                        "output_tokens": use_out,
                        "tokens": use_in + use_out,
                        "cost_usd": float(cost_usd or 0.0),
                        "input_cost_usd": float(input_cost_usd or 0.0),
                        "output_cost_usd": float(output_cost_usd or 0.0),
                        "reason": reason,
                        "reference": reference,
                        "model": model,
                        "input_remaining_after": data.get("input_remaining", 0),
                        "output_remaining_after": data.get("output_remaining", 0),
                        "balance_after": int(data.get("input_remaining") or 0) + int(data.get("output_remaining") or 0),
                    }
                )
            return self.get_wallet(tid)

        with self._lock:
            data = self._read(tid)
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
            self._write(tid, data)
            self._append_ledger(
                {
                    "id": str(uuid.uuid4()),
                    "ts": time.time(),
                    "tenant_id": tid,
                    "type": "debit",
                    "input_tokens": use_in,
                    "output_tokens": use_out,
                    "tokens": use_in + use_out,
                    "cost_usd": float(cost_usd or 0.0),
                    "input_cost_usd": float(input_cost_usd or 0.0),
                    "output_cost_usd": float(output_cost_usd or 0.0),
                    "reason": reason,
                    "reference": reference,
                    "model": model,
                    "input_remaining_after": data["input_remaining"],
                    "output_remaining_after": data["output_remaining"],
                    "balance_after": data["input_remaining"] + data["output_remaining"],
                }
            )
        return self.get_wallet(tid)

    def recent_ledger(self, tenant_id: str, *, limit: int = 50) -> list[dict[str, Any]]:
        tid = (tenant_id or "").strip().lower()
        path = self._ledger_dir / f"{tid}.jsonl"
        if not path.exists():
            return []
        lines = path.read_text(encoding="utf-8").splitlines()
        out: list[dict[str, Any]] = []
        for line in lines[-max(1, limit) :]:
            try:
                row = json.loads(line)
                if isinstance(row, dict):
                    out.append(row)
            except Exception:
                continue
        return list(reversed(out))


token_wallet_service = TokenWalletService()
