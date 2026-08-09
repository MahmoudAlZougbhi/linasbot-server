"""Scaffolding: store Expo/FCM device tokens for future owner push.

Push *send* is intentionally not implemented until Mahmoud approves
FCM/APNs/EAS push credentials and production secrets.
"""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Any

from storage.persistent_storage import _DATA_ROOT


class OwnerPushTokenStore:
    def __init__(self, root: Path | None = None) -> None:
        self._lock = threading.RLock()
        self._root = root or (Path(_DATA_ROOT) / "owner_push_tokens")
        self._root.mkdir(parents=True, exist_ok=True)

    def _path(self, tenant_id: str) -> Path:
        safe = (tenant_id or "linas").strip() or "linas"
        return self._root / f"{safe}.json"

    def _load(self, tenant_id: str) -> dict[str, Any]:
        path = self._path(tenant_id)
        if not path.is_file():
            return {"tenant_id": tenant_id, "tokens": {}}
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return {"tenant_id": tenant_id, "tokens": {}}
        if not isinstance(data, dict):
            return {"tenant_id": tenant_id, "tokens": {}}
        tokens = data.get("tokens")
        if not isinstance(tokens, dict):
            data["tokens"] = {}
        return data

    def upsert(
        self,
        *,
        tenant_id: str,
        user_id: str,
        token: str,
        platform: str | None = None,
        expo_project_id: str | None = None,
    ) -> dict[str, Any]:
        tid = (tenant_id or "linas").strip() or "linas"
        uid = (user_id or "").strip()
        tok = (token or "").strip()
        if not uid or not tok:
            raise ValueError("user_id and token are required")
        with self._lock:
            data = self._load(tid)
            data["tenant_id"] = tid
            data["tokens"][uid] = {
                "token": tok,
                "platform": (platform or "").strip() or None,
                "expo_project_id": (expo_project_id or "").strip() or None,
                "updated_at": time.time(),
            }
            self._path(tid).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            return data["tokens"][uid]

    def list_tokens(self, *, tenant_id: str) -> list[dict[str, Any]]:
        data = self._load(tenant_id)
        out: list[dict[str, Any]] = []
        for uid, row in (data.get("tokens") or {}).items():
            if isinstance(row, dict) and row.get("token"):
                out.append({"user_id": uid, **row})
        return out


owner_push_token_store = OwnerPushTokenStore()
