"""FAQ / Smart Answers metrics + platform_owner analytics hooks."""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Any

from storage.persistent_storage import _DATA_ROOT


class FaqMetricsStore:
    def __init__(self, root: Path | None = None) -> None:
        self._lock = threading.RLock()
        self._root = root or (Path(_DATA_ROOT) / "faq_metrics")
        self._root.mkdir(parents=True, exist_ok=True)

    def _path(self, tenant_id: str) -> Path:
        return self._root / f"{tenant_id}.json"

    def _load(self, tenant_id: str) -> dict[str, Any]:
        path = self._path(tenant_id)
        if not path.is_file():
            return {
                "tenant_id": tenant_id,
                "faq_hits": 0,
                "generations_avoided": 0,
                "lookups": 0,
                "misses": 0,
                "updated_at": time.time(),
            }
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return {
                "tenant_id": tenant_id,
                "faq_hits": 0,
                "generations_avoided": 0,
                "lookups": 0,
                "misses": 0,
                "updated_at": time.time(),
            }

    def _save(self, tenant_id: str, data: dict[str, Any]) -> dict[str, Any]:
        data["updated_at"] = time.time()
        with self._lock:
            self._path(tenant_id).write_text(json.dumps(data), encoding="utf-8")
        return data

    def record_lookup(self, *, tenant_id: str, hit: bool, generation_avoided: bool = False) -> dict[str, Any]:
        with self._lock:
            data = self._load(tenant_id)
            data["lookups"] = int(data.get("lookups") or 0) + 1
            if hit:
                data["faq_hits"] = int(data.get("faq_hits") or 0) + 1
                if generation_avoided:
                    data["generations_avoided"] = int(data.get("generations_avoided") or 0) + 1
            else:
                data["misses"] = int(data.get("misses") or 0) + 1
            return self._save(tenant_id, data)

    def snapshot(self, tenant_id: str) -> dict[str, Any]:
        from services.faq_entitlements import get_faq_entitlement

        data = self._load(tenant_id)
        lookups = int(data.get("lookups") or 0)
        hits = int(data.get("faq_hits") or 0)
        ent = get_faq_entitlement(tenant_id)
        hit_rate = round(hits / lookups, 4) if lookups else 0.0
        return {
            **data,
            "hit_rate": hit_rate,
            "quota": {
                "used": ent["faq_used_entries"],
                "max": ent["faq_max_entries"],
                "display": ent["quota_display"],
                "enabled": ent["faq_enabled"],
            },
        }


faq_metrics_store = FaqMetricsStore()


def platform_owner_faq_analytics() -> dict[str, Any]:
    """Aggregate FAQ metrics across tenants for platform_owner dashboards."""
    root = Path(_DATA_ROOT) / "faq_metrics"
    tenants: list[dict[str, Any]] = []
    total_hits = 0
    total_avoided = 0
    if root.is_dir():
        for path in root.glob("*.json"):
            try:
                row = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                continue
            snap = faq_metrics_store.snapshot(str(row.get("tenant_id") or path.stem))
            tenants.append(snap)
            total_hits += int(snap.get("faq_hits") or 0)
            total_avoided += int(snap.get("generations_avoided") or 0)
    return {
        "tenants": tenants,
        "totals": {
            "faq_hits": total_hits,
            "generations_avoided": total_avoided,
            "tenant_count": len(tenants),
        },
    }
