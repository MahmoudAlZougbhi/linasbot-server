"""Tenant prepaid token wallet: balance, ledger, atomic debit/credit.

Unlimited tenants (Lina production by default) bypass metering.
New SaaS registrants must hold a positive balance for AI replies.
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


class InsufficientTokenBalance(Exception):
    """Raised when a metered tenant cannot cover an AI token debit."""

    def __init__(self, tenant_id: str, balance: int, required: int) -> None:
        self.tenant_id = tenant_id
        self.balance = balance
        self.required = required
        super().__init__(f"Insufficient token balance for tenant={tenant_id} balance={balance} required={required}")


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
    balance_tokens: int
    lifetime_credited: int
    lifetime_debited: int
    lifetime_spent_usd: float
    unlimited: bool
    updated_at: float

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "tenant_id": self.tenant_id,
            "balance_tokens": self.balance_tokens,
            "lifetime_credited": self.lifetime_credited,
            "lifetime_debited": self.lifetime_debited,
            "lifetime_spent_usd": round(self.lifetime_spent_usd, 6),
            "tokens_used": self.lifetime_debited,
            "tokens_remaining": self.balance_tokens,
            "unlimited": self.unlimited,
            "updated_at": self.updated_at,
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
            "balance_tokens": 0,
            "lifetime_credited": 0,
            "lifetime_debited": 0,
            "lifetime_spent_usd": 0.0,
            "updated_at": time.time(),
        }

    def _read(self, tenant_id: str) -> dict[str, Any]:
        path = self._wallet_path(tenant_id)
        if not path.exists():
            return self._empty(tenant_id)
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                return self._empty(tenant_id)
            data.setdefault("tenant_id", tenant_id)
            data.setdefault("balance_tokens", 0)
            data.setdefault("lifetime_credited", 0)
            data.setdefault("lifetime_debited", 0)
            data.setdefault("lifetime_spent_usd", 0.0)
            return data
        except Exception:
            return self._empty(tenant_id)

    def _write(self, tenant_id: str, data: dict[str, Any]) -> None:
        path = self._wallet_path(tenant_id)
        tmp = path.with_suffix(".tmp")
        payload = dict(data)
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
            balance_tokens=int(data.get("balance_tokens") or 0),
            lifetime_credited=int(data.get("lifetime_credited") or 0),
            lifetime_debited=int(data.get("lifetime_debited") or 0),
            lifetime_spent_usd=float(data.get("lifetime_spent_usd") or 0.0),
            unlimited=unlimited,
            updated_at=float(data.get("updated_at") or time.time()),
        )

    def ensure_ai_allowed(self, tenant_id: str, *, require_at_least: int = 1) -> WalletSnapshot:
        """Fail closed when metered tenant has insufficient balance."""
        snap = self.get_wallet(tenant_id)
        if snap.unlimited:
            return snap
        if snap.balance_tokens < max(1, int(require_at_least)):
            raise InsufficientTokenBalance(snap.tenant_id, snap.balance_tokens, max(1, int(require_at_least)))
        return snap

    def credit(
        self,
        tenant_id: str,
        tokens: int,
        *,
        amount_usd: float = 0.0,
        reason: str,
        reference: str | None = None,
        package_id: str | None = None,
        actor: str | None = None,
    ) -> WalletSnapshot:
        tid = (tenant_id or "").strip().lower()
        if not tid:
            raise ValueError("tenant_id required")
        add = int(tokens)
        if add <= 0:
            raise ValueError("tokens must be positive")
        with self._lock:
            data = self._read(tid)
            data["balance_tokens"] = int(data.get("balance_tokens") or 0) + add
            data["lifetime_credited"] = int(data.get("lifetime_credited") or 0) + add
            if amount_usd and amount_usd > 0:
                data["lifetime_spent_usd"] = float(data.get("lifetime_spent_usd") or 0.0) + float(amount_usd)
            self._write(tid, data)
            self._append_ledger(
                {
                    "id": str(uuid.uuid4()),
                    "ts": time.time(),
                    "tenant_id": tid,
                    "type": "credit",
                    "tokens": add,
                    "amount_usd": float(amount_usd or 0.0),
                    "reason": reason,
                    "reference": reference,
                    "package_id": package_id,
                    "actor": actor,
                    "balance_after": data["balance_tokens"],
                }
            )
        return self.get_wallet(tid)

    def debit(
        self,
        tenant_id: str,
        tokens: int,
        *,
        cost_usd: float = 0.0,
        reason: str = "ai_usage",
        reference: str | None = None,
        model: str | None = None,
    ) -> WalletSnapshot:
        """
        Atomically decrement balance. Unlimited tenants no-op successfully.
        Never allows negative balance (fail closed).
        """
        tid = (tenant_id or "").strip().lower() or "linas"
        use = max(0, int(tokens))
        if use <= 0:
            return self.get_wallet(tid)
        if is_unlimited_tenant(tid):
            with self._lock:
                data = self._read(tid)
                data["lifetime_debited"] = int(data.get("lifetime_debited") or 0) + use
                self._write(tid, data)
                self._append_ledger(
                    {
                        "id": str(uuid.uuid4()),
                        "ts": time.time(),
                        "tenant_id": tid,
                        "type": "debit_unlimited",
                        "tokens": use,
                        "cost_usd": float(cost_usd or 0.0),
                        "reason": reason,
                        "reference": reference,
                        "model": model,
                        "balance_after": data.get("balance_tokens", 0),
                    }
                )
            return self.get_wallet(tid)

        with self._lock:
            data = self._read(tid)
            balance = int(data.get("balance_tokens") or 0)
            if balance < use:
                raise InsufficientTokenBalance(tid, balance, use)
            data["balance_tokens"] = balance - use
            data["lifetime_debited"] = int(data.get("lifetime_debited") or 0) + use
            self._write(tid, data)
            self._append_ledger(
                {
                    "id": str(uuid.uuid4()),
                    "ts": time.time(),
                    "tenant_id": tid,
                    "type": "debit",
                    "tokens": use,
                    "cost_usd": float(cost_usd or 0.0),
                    "reason": reason,
                    "reference": reference,
                    "model": model,
                    "balance_after": data["balance_tokens"],
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
