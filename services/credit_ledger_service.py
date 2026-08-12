"""Internal Linas credit ledger with reserve / capture / release for expensive jobs.

Postgres SoT when LINAS_BILLING_BACKEND=postgres (default); file when explicitly set.
"""


from __future__ import annotations

import json
import threading
import time
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Literal

from services.billing_backend import billing_uses_postgres
from services.entitlements_service import entitlements_store
from storage.persistent_storage import _DATA_ROOT

LedgerOp = Literal[
    "grant_included",
    "grant_pack",
    "reverse_pack",
    "reserve",
    "capture",
    "release",
    "debit",
    "admin_adjust",
]


@dataclass
class LedgerEntry:
    id: str
    tenant_id: str
    user_id: str | None
    op: LedgerOp
    credits: int
    balance_after: int
    operation_type: str
    model_provider: str | None
    provider_cost_usd: float | None
    request_id: str | None
    created_at: float
    meta: dict[str, Any]


class CreditLedgerService:
    def __init__(self, root: Path | None = None) -> None:
        self._lock = threading.RLock()
        self._root = root or (Path(_DATA_ROOT) / "credit_ledger")
        self._root.mkdir(parents=True, exist_ok=True)

    def _balance_path(self, tenant_id: str) -> Path:
        return self._root / f"{tenant_id}.balance.json"

    def _log_path(self, tenant_id: str) -> Path:
        return self._root / f"{tenant_id}.jsonl"

    def get_balance(self, tenant_id: str) -> int:
        if billing_uses_postgres():
            from services.credit_ledger_pg_ops import pg_get_balance

            return pg_get_balance(tenant_id)
        ent = entitlements_store.get(tenant_id)
        path = self._balance_path(tenant_id)
        with self._lock:
            if path.is_file():
                data = json.loads(path.read_text(encoding="utf-8"))
                return int(data.get("available") or 0)
        return int(ent.included_credits + ent.extra_credits)

    def get_reserved(self, tenant_id: str) -> int:
        if billing_uses_postgres():
            from services.credit_ledger_pg_ops import pg_get_reserved

            return pg_get_reserved(tenant_id)
        path = self._balance_path(tenant_id)
        with self._lock:
            if not path.is_file():
                return 0
            data = json.loads(path.read_text(encoding="utf-8"))
            return int(data.get("reserved") or 0)

    def _set_balance(self, tenant_id: str, available: int, reserved: int) -> None:
        self._balance_path(tenant_id).write_text(
            json.dumps({"available": available, "reserved": reserved, "updated_at": time.time()}),
            encoding="utf-8",
        )

    def _append(self, entry: LedgerEntry) -> None:
        with self._log_path(entry.tenant_id).open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(asdict(entry)) + "\n")

    def ensure_period_grant(self, tenant_id: str) -> None:
        if billing_uses_postgres():
            from services.credit_ledger_pg_ops import pg_ensure_period_grant

            pg_ensure_period_grant(tenant_id)
            return
        ent = entitlements_store.get(tenant_id)
        path = self._balance_path(tenant_id)
        with self._lock:
            if path.is_file():
                return
            total = int(ent.included_credits + ent.extra_credits)
            self._set_balance(tenant_id, total, 0)
            self._append(
                LedgerEntry(
                    id=uuid.uuid4().hex,
                    tenant_id=tenant_id,
                    user_id=None,
                    op="grant_included",
                    credits=total,
                    balance_after=total,
                    operation_type="period_grant",
                    model_provider=None,
                    provider_cost_usd=None,
                    request_id=None,
                    created_at=time.time(),
                    meta={"plan_id": ent.plan_id},
                )
            )

    def reserve(
        self,
        *,
        tenant_id: str,
        user_id: str | None,
        credits: int,
        operation_type: str,
        request_id: str,
    ) -> str:
        if credits <= 0:
            raise ValueError("credits must be positive")
        if billing_uses_postgres():
            from services.credit_ledger_pg_ops import pg_reserve

            return pg_reserve(
                tenant_id=tenant_id,
                user_id=user_id,
                credits=credits,
                operation_type=operation_type,
                request_id=request_id,
            )
        self.ensure_period_grant(tenant_id)
        with self._lock:
            data = json.loads(self._balance_path(tenant_id).read_text(encoding="utf-8"))
            available = int(data["available"])
            reserved = int(data["reserved"])
            if available < credits:
                raise PermissionError("Insufficient credits")
            available -= credits
            reserved += credits
            self._set_balance(tenant_id, available, reserved)
            reservation_id = uuid.uuid4().hex
            self._append(
                LedgerEntry(
                    id=reservation_id,
                    tenant_id=tenant_id,
                    user_id=user_id,
                    op="reserve",
                    credits=credits,
                    balance_after=available,
                    operation_type=operation_type,
                    model_provider=None,
                    provider_cost_usd=None,
                    request_id=request_id,
                    created_at=time.time(),
                    meta={"reservation_id": reservation_id},
                )
            )
            return reservation_id

    def _reservation_state(self, tenant_id: str, reservation_id: str) -> tuple[int, str | None]:
        credits = 0
        terminal: str | None = None
        path = self._log_path(tenant_id)
        if not path.is_file():
            return 0, None
        for line in path.read_text(encoding="utf-8").splitlines():
            row = json.loads(line)
            if row.get("tenant_id") != tenant_id:
                continue
            if row.get("id") == reservation_id and row.get("op") == "reserve":
                credits = int(row["credits"])
            if row.get("request_id") == reservation_id and row.get("op") in {"capture", "release"}:
                terminal = str(row["op"])
        return credits, terminal

    def capture(
        self,
        *,
        tenant_id: str,
        reservation_id: str,
        provider_cost_usd: float | None,
        model_provider: str | None,
    ) -> dict[str, Any]:
        if billing_uses_postgres():
            from services.credit_ledger_pg_ops import pg_capture

            return pg_capture(
                tenant_id=tenant_id,
                reservation_id=reservation_id,
                provider_cost_usd=provider_cost_usd,
                model_provider=model_provider,
            )
        with self._lock:
            credits, terminal = self._reservation_state(tenant_id, reservation_id)
            if credits <= 0:
                raise ValueError("Unknown reservation")
            if terminal == "capture":
                return {"duplicate": True, "op": "capture"}
            if terminal == "release":
                raise PermissionError("Reservation already released")
            data = json.loads(self._balance_path(tenant_id).read_text(encoding="utf-8"))
            reserved = max(0, int(data["reserved"]) - credits)
            self._set_balance(tenant_id, int(data["available"]), reserved)
            self._append(
                LedgerEntry(
                    id=uuid.uuid4().hex,
                    tenant_id=tenant_id,
                    user_id=None,
                    op="capture",
                    credits=credits,
                    balance_after=int(data["available"]),
                    operation_type="capture",
                    model_provider=model_provider,
                    provider_cost_usd=provider_cost_usd,
                    request_id=reservation_id,
                    created_at=time.time(),
                    meta={},
                )
            )
            return {"duplicate": False, "op": "capture", "credits": credits}

    def release(self, *, tenant_id: str, reservation_id: str) -> dict[str, Any]:
        if billing_uses_postgres():
            from services.credit_ledger_pg_ops import pg_release

            return pg_release(tenant_id=tenant_id, reservation_id=reservation_id)
        with self._lock:
            credits, terminal = self._reservation_state(tenant_id, reservation_id)
            if credits <= 0:
                return {"duplicate": False, "op": "release", "skipped": True}
            if terminal == "release":
                return {"duplicate": True, "op": "release"}
            if terminal == "capture":
                return {"duplicate": True, "op": "capture", "skipped": True}
            data = json.loads(self._balance_path(tenant_id).read_text(encoding="utf-8"))
            available = int(data["available"]) + credits
            reserved = max(0, int(data["reserved"]) - credits)
            self._set_balance(tenant_id, available, reserved)
            self._append(
                LedgerEntry(
                    id=uuid.uuid4().hex,
                    tenant_id=tenant_id,
                    user_id=None,
                    op="release",
                    credits=credits,
                    balance_after=available,
                    operation_type="release",
                    model_provider=None,
                    provider_cost_usd=None,
                    request_id=reservation_id,
                    created_at=time.time(),
                    meta={},
                )
            )
            return {"duplicate": False, "op": "release", "credits": credits}

    def _find_ops_by_request_id(self, tenant_id: str, request_id: str) -> list[dict[str, Any]]:
        path = self._log_path(tenant_id)
        if not path.is_file():
            return []
        found: list[dict[str, Any]] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            if row.get("tenant_id") == tenant_id and row.get("request_id") == request_id:
                found.append(row)
        return found

    def grant_pack(
        self,
        *,
        tenant_id: str,
        credits: int,
        request_id: str,
        source: str,
        meta: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Idempotent credit pack grant keyed by ``request_id`` (Apple transaction id)."""
        if credits <= 0:
            raise ValueError("credits must be positive")
        rid = str(request_id or "").strip()
        if not rid:
            raise ValueError("request_id required")
        if billing_uses_postgres():
            from services.credit_ledger_pg_ops import pg_grant_pack

            return pg_grant_pack(tenant_id=tenant_id, credits=credits, request_id=rid, source=source, meta=meta)
        self.ensure_period_grant(tenant_id)
        with self._lock:
            prior = self._find_ops_by_request_id(tenant_id, rid)
            if any(r.get("op") == "grant_pack" for r in prior):
                return {"duplicate": True, "op": "grant_pack", "credits": credits, "request_id": rid}
            data = json.loads(self._balance_path(tenant_id).read_text(encoding="utf-8"))
            available = int(data["available"]) + int(credits)
            reserved = int(data["reserved"])
            self._set_balance(tenant_id, available, reserved)
            entry_id = uuid.uuid4().hex
            self._append(
                LedgerEntry(
                    id=entry_id,
                    tenant_id=tenant_id,
                    user_id=None,
                    op="grant_pack",
                    credits=int(credits),
                    balance_after=available,
                    operation_type="pack_grant",
                    model_provider=None,
                    provider_cost_usd=None,
                    request_id=rid,
                    created_at=time.time(),
                    meta={"source": source, **(meta or {})},
                )
            )
            ent = entitlements_store.get(tenant_id)
            ent.extra_credits = int(ent.extra_credits) + int(credits)
            entitlements_store.save(ent)
            return {
                "duplicate": False,
                "op": "grant_pack",
                "credits": int(credits),
                "request_id": rid,
                "ledger_entry_id": entry_id,
                "balance_after": available,
            }

    def reverse_pack(
        self,
        *,
        tenant_id: str,
        request_id: str,
        credits: int,
        meta: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Idempotent reverse of a prior grant_pack."""
        if credits <= 0:
            raise ValueError("credits must be positive")
        rid = str(request_id or "").strip()
        if not rid:
            raise ValueError("request_id required")
        if billing_uses_postgres():
            from services.credit_ledger_pg_ops import pg_reverse_pack

            return pg_reverse_pack(tenant_id=tenant_id, request_id=rid, credits=credits, meta=meta)
        self.ensure_period_grant(tenant_id)
        with self._lock:
            prior = self._find_ops_by_request_id(tenant_id, rid)
            if any(r.get("op") == "reverse_pack" for r in prior):
                return {"duplicate": True, "op": "reverse_pack", "credits": credits, "request_id": rid}
            data = json.loads(self._balance_path(tenant_id).read_text(encoding="utf-8"))
            available = int(data["available"])
            reserved = int(data["reserved"])
            reduce_by = min(available, int(credits))
            debt = int(credits) - reduce_by
            available = available - reduce_by
            self._set_balance(tenant_id, available, reserved)
            entry_id = uuid.uuid4().hex
            self._append(
                LedgerEntry(
                    id=entry_id,
                    tenant_id=tenant_id,
                    user_id=None,
                    op="reverse_pack",
                    credits=int(credits),
                    balance_after=available,
                    operation_type="pack_reverse",
                    model_provider=None,
                    provider_cost_usd=None,
                    request_id=rid,
                    created_at=time.time(),
                    meta={"debt": debt, "reduced": reduce_by, **(meta or {})},
                )
            )
            ent = entitlements_store.get(tenant_id)
            ent.extra_credits = max(0, int(ent.extra_credits) - int(credits))
            entitlements_store.save(ent)
            return {
                "duplicate": False,
                "op": "reverse_pack",
                "credits": int(credits),
                "request_id": rid,
                "ledger_entry_id": entry_id,
                "balance_after": available,
                "debt": debt,
                "reduced": reduce_by,
            }


credit_ledger_service = CreditLedgerService()
