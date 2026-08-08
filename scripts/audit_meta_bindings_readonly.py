#!/usr/bin/env python3
"""Read-only Meta binding audit. Never prints tokens or app secrets."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from typing import Any

REGISTRY_PATH = Path("/opt/linasbot_data/meta_registry/registry.json")


def _hash(value: str) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def _mask_id(value: str) -> str:
    raw = str(value or "").strip()
    if len(raw) <= 6:
        return "***"
    return f"{raw[:3]}…{raw[-3:]}"


def _load_registry(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError(f"registry not found at {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("registry root is not an object")
    return payload


def audit_registry(path: Path = REGISTRY_PATH) -> list[dict[str, Any]]:
    state = _load_registry(path)
    bindings_raw = state.get("bindings")
    credentials_raw = state.get("credentials")
    if not isinstance(bindings_raw, dict) or not isinstance(credentials_raw, dict):
        raise ValueError("registry structure is invalid")

    rows: list[dict[str, Any]] = []
    for binding_id, raw in bindings_raw.items():
        if not isinstance(raw, dict):
            continue
        credential_id = str(raw.get("credential_id") or "")
        credential = credentials_raw.get(credential_id)
        credential_present = isinstance(credential, dict)
        rows.append(
            {
                "binding_id": binding_id,
                "tenant_id": str(raw.get("tenant_id") or ""),
                "app_key": str(raw.get("app_key") or ""),
                "channel": str(raw.get("channel") or ""),
                "asset_id_masked": _mask_id(str(raw.get("asset_id") or "")),
                "asset_id_hash": _hash(str(raw.get("asset_id") or "")),
                "page_id_masked": _mask_id(str(raw.get("page_id") or "")),
                "page_id_hash": _hash(str(raw.get("page_id") or "")),
                "instagram_account_id_masked": _mask_id(str(raw.get("instagram_account_id") or "")),
                "instagram_account_id_hash": _hash(str(raw.get("instagram_account_id") or "")),
                "status": str(raw.get("status") or ""),
                "generation": int(raw.get("generation") or 0),
                "credential_id": credential_id,
                "credential_present": credential_present,
                "previous_binding_id": str(raw.get("previous_binding_id") or ""),
                "created_at": float(raw.get("created_at") or 0),
                "updated_at": float(raw.get("updated_at") or 0),
            }
        )
    rows.sort(key=lambda item: (item["tenant_id"], item["channel"], item["asset_id_hash"], item["created_at"]))
    return rows


def main() -> int:
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else REGISTRY_PATH
    rows = audit_registry(path)
    print(f"[meta-binding-audit] registry_path={path}")
    print(f"[meta-binding-audit] binding_count={len(rows)}")
    for row in rows:
        print("[meta-binding-audit] row " + json.dumps(row, separators=(",", ":"), sort_keys=True))
    by_tenant_channel: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for row in rows:
        key = (row["tenant_id"], row["channel"])
        by_tenant_channel.setdefault(key, []).append(row)
    for (tenant_id, channel), group in sorted(by_tenant_channel.items()):
        asset_hashes = {item["asset_id_hash"] for item in group if item["asset_id_hash"]}
        active = [item for item in group if item["status"] == "active"]
        disconnected = [item for item in group if item["status"] == "disconnected"]
        inactive = [item for item in group if item["status"] == "inactive"]
        print(
            "[meta-binding-audit] summary "
            + json.dumps(
                {
                    "tenant_id": tenant_id,
                    "channel": channel,
                    "total": len(group),
                    "distinct_asset_hashes": len(asset_hashes),
                    "active_count": len(active),
                    "disconnected_count": len(disconnected),
                    "inactive_count": len(inactive),
                    "same_asset_duplicate": len(asset_hashes) < len(group),
                },
                separators=(",", ":"),
                sort_keys=True,
            )
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
