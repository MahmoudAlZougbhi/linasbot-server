"""Per-tenant Live Chat inbox cache. Unscoped cache files are never loaded."""

from __future__ import annotations

import json
import os
from typing import Any

from services.live_chat.contracts import utc_now
from services.live_chat.tenant import normalize_live_chat_tenant_id, row_belongs_to_tenant


class LiveChatInboxCacheMixin:
    """Memory + disk inbox cache keyed by tenant_id."""

    PERSIST_UNIFIED_CACHE: Any
    UNIFIED_CACHE_PATH: Any
    UNIFIED_DISK_CACHE_MAX_AGE_SECONDS: Any
    _empty_counters: Any
    _parse_timestamp: Any
    _unified_inbox_by_tenant: dict[str, dict[str, Any]]
    _waiting_queue_by_tenant: dict[str, dict[str, Any]]
    _index_counters_by_tenant: dict[str, dict[str, Any]]

    def _tenant_inbox_slot(self, tenant_id: str) -> dict[str, Any] | None:
        tid = normalize_live_chat_tenant_id(tenant_id)
        if not tid:
            return None
        slot = self._unified_inbox_by_tenant.get(tid)
        if not isinstance(slot, dict):
            return None
        chats = slot.get("chats")
        if not isinstance(chats, list):
            return None
        scoped = [row for row in chats if isinstance(row, dict) and row_belongs_to_tenant(row, tid)]
        if len(scoped) != len(chats):
            slot = dict(slot)
            slot["chats"] = scoped
            self._unified_inbox_by_tenant[tid] = slot
        return slot

    def _cached_unified_response(
        self,
        page: int,
        page_size: int,
        filter_state: str,
        search: str,
        *,
        tenant_id: str = "",
    ) -> dict[str, Any] | None:
        slot = self._tenant_inbox_slot(tenant_id)
        if not slot:
            return None
        chats = list(slot.get("chats") or [])
        counters = dict(slot.get("counters") or self._counters_for_tenant(tenant_id))
        return {
            "success": True,
            "chats": chats,
            "total": int(slot.get("total") or len(chats)),
            "page": page,
            "page_size": page_size,
            "has_more": bool(slot.get("has_more")),
            "next_cursor": slot.get("next_cursor"),
            "filter": filter_state,
            "counters": counters,
            "search": search,
            "source": "cache",
        }

    def _store_unified_inbox(
        self,
        tenant_id: str,
        *,
        chats: list[dict[str, Any]],
        has_more: bool,
        total: int,
        next_cursor: str | None,
        page_size: int,
        counters: dict[str, int],
    ) -> None:
        tid = normalize_live_chat_tenant_id(tenant_id)
        if not tid:
            return
        scoped = [row for row in chats if row_belongs_to_tenant(row, tid)]
        self._unified_inbox_by_tenant[tid] = {
            "chats": scoped,
            "has_more": has_more,
            "total": total,
            "next_cursor": next_cursor,
            "page_size": page_size,
            "counters": dict(counters),
            "cached_at": utc_now(),
        }
        self._index_counters_by_tenant[tid] = {
            "counters": dict(counters),
            "cached_at": utc_now(),
        }
        self._persist_unified_cache_to_disk()

    def _counters_for_tenant(self, tenant_id: str) -> dict[str, int]:
        tid = normalize_live_chat_tenant_id(tenant_id)
        slot = self._index_counters_by_tenant.get(tid) if tid else None
        counters = slot.get("counters") if isinstance(slot, dict) else None
        if isinstance(counters, dict):
            typed: dict[str, int] = {str(key): int(value) for key, value in counters.items()}
            return typed
        empty = dict(self._empty_counters())
        typed_empty: dict[str, int] = {str(key): int(value) for key, value in empty.items()}
        return typed_empty

    def _unified_cache_file(self) -> Any:
        path = str(self.UNIFIED_CACHE_PATH or "").strip()
        if not path:
            return ""
        return path if os.path.isabs(path) else os.path.join(os.getcwd(), path)

    def _persist_unified_cache_to_disk(self) -> None:
        if not self.PERSIST_UNIFIED_CACHE:
            return
        cache_file = self._unified_cache_file()
        if not cache_file:
            return
        try:
            cache_dir = os.path.dirname(cache_file)
            if cache_dir:
                os.makedirs(cache_dir, exist_ok=True)
            tenants: dict[str, Any] = {}
            for tid, slot in self._unified_inbox_by_tenant.items():
                chats = [row for row in (slot.get("chats") or []) if row_belongs_to_tenant(row, tid)]
                if not chats:
                    continue
                cached_at = slot.get("cached_at") or utc_now()
                tenants[tid] = {
                    "chats": chats,
                    "has_more": bool(slot.get("has_more")),
                    "total": int(slot.get("total") or len(chats)),
                    "next_cursor": slot.get("next_cursor"),
                    "page_size": slot.get("page_size"),
                    "counters": dict(slot.get("counters") or self._empty_counters()),
                    "updated_at": cached_at.isoformat() if hasattr(cached_at, "isoformat") else str(cached_at),
                }
            payload = {"updated_at": utc_now().isoformat(), "tenants": tenants}
            with open(cache_file, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False)
        except Exception as e:
            print(f"⚠️ Could not persist unified cache to disk: {e}")

    def _load_unified_cache_from_disk(self, tenant_id: str = "") -> None:
        if not self.PERSIST_UNIFIED_CACHE:
            return
        cache_file = self._unified_cache_file()
        if not cache_file or not os.path.exists(cache_file):
            return
        try:
            with open(cache_file, encoding="utf-8") as f:
                payload = json.load(f) or {}
            tenants = payload.get("tenants")
            if not isinstance(tenants, dict):
                # Legacy unscoped cache would leak across workspaces.
                print("[live_chat:unified] refusing unscoped disk cache")
                return
            wanted = normalize_live_chat_tenant_id(tenant_id)
            max_age = max(60, int(self.UNIFIED_DISK_CACHE_MAX_AGE_SECONDS))
            now = utc_now()
            for tid, raw in tenants.items():
                key = normalize_live_chat_tenant_id(tid)
                if not key or (wanted and key != wanted):
                    continue
                if not isinstance(raw, dict):
                    continue
                chats = raw.get("chats")
                if not isinstance(chats, list) or not chats:
                    continue
                updated_at_raw = raw.get("updated_at") or payload.get("updated_at")
                if updated_at_raw:
                    try:
                        age = (now - self._parse_timestamp(updated_at_raw)).total_seconds()
                        if age > max_age:
                            continue
                    except Exception:
                        pass
                scoped = [row for row in chats if isinstance(row, dict) and row_belongs_to_tenant(row, key)]
                if not scoped:
                    continue
                counters = raw.get("counters")
                merged = self._empty_counters()
                if isinstance(counters, dict):
                    merged.update({k: int(v) for k, v in counters.items() if k in merged})
                self._unified_inbox_by_tenant[key] = {
                    "chats": scoped,
                    "has_more": bool(raw.get("has_more")),
                    "total": int(raw.get("total") or len(scoped)),
                    "next_cursor": raw.get("next_cursor"),
                    "page_size": raw.get("page_size"),
                    "counters": merged,
                    "cached_at": now,
                }
                self._index_counters_by_tenant[key] = {"counters": merged, "cached_at": now}
            print(
                f"[live_chat:unified] loaded disk cache tenants={len(self._unified_inbox_by_tenant)} file={cache_file}"
            )
        except Exception as e:
            print(f"⚠️ Could not load unified cache from disk: {e}")

    def _stale_unified_fallback(
        self,
        page: int,
        page_size: int,
        filter_state: str,
        search: str,
        *,
        tenant_id: str = "",
    ) -> dict[str, Any] | None:
        if not normalize_live_chat_tenant_id(tenant_id):
            return None
        resp = self._cached_unified_response(page, page_size, filter_state, search, tenant_id=tenant_id)
        if resp:
            resp["source"] = "memory_cache"
            return resp
        self._load_unified_cache_from_disk(tenant_id)
        resp = self._cached_unified_response(page, page_size, filter_state, search, tenant_id=tenant_id)
        if resp:
            resp["source"] = "disk_cache"
            return resp
        return None

    def _empty_unified_response(
        self, page: int, page_size: int, filter_state: str, search: str, source: str, *, tenant_id: str = ""
    ) -> dict[str, Any]:
        is_legitimate_empty = source in {"index_empty", "missing_tenant"}
        payload: dict[str, Any] = {
            "success": is_legitimate_empty or source == "missing_tenant",
            "chats": [],
            "total": 0,
            "page": page,
            "page_size": page_size,
            "has_more": False,
            "next_cursor": None,
            "filter": filter_state,
            "counters": self._counters_for_tenant(tenant_id),
            "search": search,
            "source": source,
        }
        if not payload["success"]:
            payload["error"] = "Could not load conversations."
        return payload
