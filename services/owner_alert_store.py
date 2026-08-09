"""Tenant-scoped owner notification inbox (file-backed, no fake events)."""

from __future__ import annotations

import json
import threading
import time
import uuid
from pathlib import Path
from typing import Any

from storage.persistent_storage import _DATA_ROOT


class OwnerAlertStore:
    """Persist owner alerts under ``data/owner_alerts/{tenant_id}/``.

    One JSON file per alert. Index is derived by scanning (small scale).
    """

    def __init__(self, root: Path | None = None) -> None:
        self._lock = threading.RLock()
        self._root = root or (Path(_DATA_ROOT) / "owner_alerts")
        self._root.mkdir(parents=True, exist_ok=True)

    def _tenant_dir(self, tenant_id: str) -> Path:
        safe = (tenant_id or "linas").strip() or "linas"
        path = self._root / safe
        path.mkdir(parents=True, exist_ok=True)
        return path

    def _alert_path(self, tenant_id: str, alert_id: str) -> Path:
        return self._tenant_dir(tenant_id) / f"{alert_id}.json"

    def create(self, *, tenant_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        now = time.time()
        alert_id = uuid.uuid4().hex
        record = {
            "id": alert_id,
            "tenant_id": (tenant_id or "linas").strip() or "linas",
            "created_at": now,
            "read": False,
            "read_at": None,
            **payload,
        }
        path = self._alert_path(record["tenant_id"], alert_id)
        with self._lock:
            path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
        return record

    def list_alerts(
        self,
        *,
        tenant_id: str,
        limit: int = 50,
        unread_only: bool = False,
    ) -> list[dict[str, Any]]:
        lim = max(1, min(int(limit or 50), 200))
        items: list[dict[str, Any]] = []
        with self._lock:
            for path in self._tenant_dir(tenant_id).glob("*.json"):
                try:
                    data = json.loads(path.read_text(encoding="utf-8"))
                except Exception:
                    continue
                if not isinstance(data, dict) or not data.get("id"):
                    continue
                if unread_only and data.get("read"):
                    continue
                items.append(data)
        items.sort(key=lambda x: float(x.get("created_at") or 0), reverse=True)
        return items[:lim]

    def unread_count(self, *, tenant_id: str) -> int:
        return len(self.list_alerts(tenant_id=tenant_id, limit=200, unread_only=True))

    def get(self, *, tenant_id: str, alert_id: str) -> dict[str, Any] | None:
        path = self._alert_path(tenant_id, alert_id)
        with self._lock:
            if not path.is_file():
                return None
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                return None
        return data if isinstance(data, dict) else None

    def mark_read(self, *, tenant_id: str, alert_id: str) -> dict[str, Any] | None:
        path = self._alert_path(tenant_id, alert_id)
        with self._lock:
            if not path.is_file():
                return None
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                return None
            if not isinstance(data, dict):
                return None
            data["read"] = True
            data["read_at"] = time.time()
            path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            return data

    def mark_all_read(self, *, tenant_id: str) -> int:
        count = 0
        with self._lock:
            for path in self._tenant_dir(tenant_id).glob("*.json"):
                try:
                    data = json.loads(path.read_text(encoding="utf-8"))
                except Exception:
                    continue
                if not isinstance(data, dict) or data.get("read"):
                    continue
                data["read"] = True
                data["read_at"] = time.time()
                path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
                count += 1
        return count

    def recent_duplicate(
        self,
        *,
        tenant_id: str,
        alert_type: str,
        conversation_id: str | None,
        user_id: str | None,
        within_seconds: float = 1800.0,
    ) -> bool:
        """True if a same-type alert for this conversation/user exists within the window."""
        now = time.time()
        conv = (conversation_id or "").strip()
        uid = (user_id or "").strip()
        for item in self.list_alerts(tenant_id=tenant_id, limit=80):
            if str(item.get("type") or "") != alert_type:
                continue
            created = float(item.get("created_at") or 0)
            if now - created > within_seconds:
                continue
            if conv and str(item.get("conversation_id") or "") == conv:
                return True
            if not conv and uid and str(item.get("user_id") or "") == uid:
                return True
        return False


owner_alert_store = OwnerAlertStore()
