"""File-backed token wallet persistence (extracted from TokenWalletService)."""

from __future__ import annotations

import json
import time
import uuid
from pathlib import Path
from typing import Any

from services.token_wallet_models import (
    LEGACY_INPUT_SHARE,
    MIGRATION_NOTE,
)
from storage.persistent_storage import _DATA_ROOT


class TokenWalletFileStore:
    def __init__(self, store_dir: Path | None = None) -> None:
        self._store_dir = store_dir or (Path(_DATA_ROOT) / "billing" / "wallets")
        self._store_dir.mkdir(parents=True, exist_ok=True)
        self._ledger_dir = self._store_dir / "ledger"
        self._ledger_dir.mkdir(parents=True, exist_ok=True)

    def wallet_path(self, tenant_id: str) -> Path:
        safe = (tenant_id or "unknown").strip().lower().replace("/", "_")
        return self._store_dir / f"{safe}.json"

    def empty_wallet(self, tenant_id: str) -> dict[str, Any]:
        return {
            "tenant_id": tenant_id,
            "input_remaining": 0,
            "output_remaining": 0,
            "lifetime_input_credited": 0,
            "lifetime_output_credited": 0,
            "lifetime_input_debited": 0,
            "lifetime_output_debited": 0,
            "lifetime_spent_usd": 0.0,
            "balance_tokens": 0,
            "lifetime_credited": 0,
            "lifetime_debited": 0,
            "updated_at": time.time(),
            "schema_version": 2,
        }

    def migrate_legacy_if_needed(self, tenant_id: str, data: dict[str, Any]) -> dict[str, Any]:
        if data.get("schema_version") == 2 and "input_remaining" in data and "output_remaining" in data:
            data["balance_tokens"] = int(data.get("input_remaining") or 0) + int(data.get("output_remaining") or 0)
            data["lifetime_credited"] = int(data.get("lifetime_input_credited") or 0) + int(
                data.get("lifetime_output_credited") or 0
            )
            data["lifetime_debited"] = int(data.get("lifetime_input_debited") or 0) + int(
                data.get("lifetime_output_debited") or 0
            )
            return data

        legacy_balance = int(data.get("balance_tokens") or 0)
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

        return {
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

    def normalize_wallet_payload(self, data: dict[str, Any]) -> dict[str, Any]:
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
        return payload

    def read(self, tenant_id: str) -> dict[str, Any]:
        path = self.wallet_path(tenant_id)
        if not path.exists():
            return self.empty_wallet(tenant_id)
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                return self.empty_wallet(tenant_id)
            data.setdefault("tenant_id", tenant_id)
            return self.migrate_legacy_if_needed(tenant_id, data)
        except Exception:
            return self.empty_wallet(tenant_id)

    def write(self, tenant_id: str, data: dict[str, Any]) -> None:
        path = self.wallet_path(tenant_id)
        tmp = path.with_suffix(".tmp")
        payload = self.normalize_wallet_payload(data)
        tmp.write_text(json.dumps(payload), encoding="utf-8")
        tmp.replace(path)

    def append_ledger(self, entry: dict[str, Any]) -> None:
        tenant_id = str(entry.get("tenant_id") or "unknown")
        path = self._ledger_dir / f"{tenant_id}.jsonl"
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry) + "\n")

    def persist_legacy_migration(self, tenant_id: str, migrated: dict[str, Any]) -> None:
        self.write(tenant_id, migrated)
        self.append_ledger(
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

    def recent_ledger(self, tenant_id: str, *, limit: int = 50) -> list[dict[str, Any]]:
        path = self._ledger_dir / f"{tenant_id}.jsonl"
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

    def iter_wallet_files(self) -> list[Path]:
        return sorted(self._store_dir.glob("*.json"))

    def iter_ledger_files(self) -> list[Path]:
        return sorted(self._ledger_dir.glob("*.jsonl"))
