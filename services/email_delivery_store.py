"""Persist Resend delivery webhook events with idempotency (no email body / secrets)."""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Any

from storage.persistent_storage import _DATA_ROOT

# Map Resend event types to compact delivery states.
_EVENT_STATE = {
    "email.delivered": "delivered",
    "email.bounced": "bounced",
    "email.complained": "complained",
    "email.failed": "failed",
    "email.delivery_delayed": "delayed",
}


class EmailDeliveryStore:
    def __init__(self, store_dir: Path | None = None) -> None:
        self._lock = threading.RLock()
        self._dir = store_dir or (Path(_DATA_ROOT) / "email" / "delivery_events")
        self._dir.mkdir(parents=True, exist_ok=True)

    def _path(self, event_id: str) -> Path:
        safe = "".join(ch for ch in event_id if ch.isalnum() or ch in {"-", "_"})[:128]
        return self._dir / f"{safe}.json"

    def record_event(self, *, svix_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        """Store event once. Duplicate svix-id returns prior record with duplicate=True."""
        event_id = (svix_id or "").strip()
        if not event_id:
            raise ValueError("svix_id_required")

        event_type = str(payload.get("type") or "").strip()
        raw_data = payload.get("data")
        data: dict[str, Any] = raw_data if isinstance(raw_data, dict) else {}
        email_id = str(data.get("email_id") or data.get("id") or "").strip() or None
        raw_to = data.get("to")
        to_list: list[Any] = raw_to if isinstance(raw_to, list) else []
        # Store only domain-safe recipient fingerprint (no full mailbox when avoidable).
        recipients: list[str] = []
        for item in to_list[:10]:
            addr = str(item or "").strip().lower()
            if "@" in addr:
                local, _, domain = addr.partition("@")
                recipients.append(f"{local[:2]}***@{domain}" if local else f"***@{domain}")

        record = {
            "svix_id": event_id,
            "type": event_type,
            "state": _EVENT_STATE.get(event_type, "unknown"),
            "email_id": email_id,
            "recipients": recipients,
            "created_at": time.time(),
            "payload_keys": sorted(str(k) for k in data.keys())[:40],
        }

        path = self._path(event_id)
        with self._lock:
            if path.exists():
                try:
                    prior = json.loads(path.read_text(encoding="utf-8"))
                except Exception:
                    prior = record
                return {"duplicate": True, "record": prior}
            path.write_text(json.dumps(record), encoding="utf-8")
            return {"duplicate": False, "record": record}

    def get(self, svix_id: str) -> dict[str, Any] | None:
        path = self._path(svix_id)
        with self._lock:
            if not path.exists():
                return None
            try:
                loaded = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                return None
            return loaded if isinstance(loaded, dict) else None


email_delivery_store = EmailDeliveryStore()
