# -*- coding: utf-8 -*-
"""Durable rate limiting for auth and sensitive mutations (file-backed + memory)."""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Optional, Tuple

from storage.persistent_storage import _DATA_ROOT


class RateLimitService:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._dir = Path(_DATA_ROOT) / "auth" / "rate_limits"
        self._dir.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        safe = "".join(c if c.isalnum() or c in "-_." else "_" for c in key)[:180]
        return self._dir / f"{safe}.json"

    def hit(self, key: str, *, limit: int, window_seconds: int) -> Tuple[bool, int]:
        """
        Record a hit. Returns (allowed, retry_after_seconds).
        """
        now = time.time()
        window_start = now - window_seconds
        path = self._path(key)
        with self._lock:
            timestamps = []
            if path.exists():
                try:
                    timestamps = json.loads(path.read_text(encoding="utf-8")).get("hits") or []
                except Exception:
                    timestamps = []
            timestamps = [float(t) for t in timestamps if float(t) >= window_start]
            if len(timestamps) >= limit:
                oldest = min(timestamps) if timestamps else now
                retry = max(1, int(window_seconds - (now - oldest)) + 1)
                path.write_text(json.dumps({"hits": timestamps}), encoding="utf-8")
                return False, retry
            timestamps.append(now)
            path.write_text(json.dumps({"hits": timestamps}), encoding="utf-8")
            return True, 0


rate_limit_service = RateLimitService()
