"""In-memory Redis for claim tests. Supports SET NX EX and the owner Lua scripts."""

from __future__ import annotations

import time
from typing import Any

from services.scale.redis_claims import RedisClaimStore


class MemoryClaimRedis:
    def __init__(self) -> None:
        self.values: dict[str, tuple[str, float | None]] = {}

    def _live(self, key: str) -> str | None:
        item = self.values.get(key)
        if item is None:
            return None
        value, expires = item
        if expires is not None and expires <= time.time():
            self.values.pop(key, None)
            return None
        return value

    def ping(self) -> bool:
        return True

    def set(self, key: str, value: str, nx: bool = False, ex: int | None = None) -> bool | None:
        if nx and self._live(key) is not None:
            return None
        self.values[key] = (str(value), time.time() + ex if ex else None)
        return True

    def get(self, key: str) -> str | None:
        return self._live(key)

    def delete(self, key: str) -> int:
        return 1 if self.values.pop(key, None) is not None else 0

    def eval(self, script: str, _numkeys: int, *keys_and_args: str) -> int:
        key = keys_and_args[0]
        owner = keys_and_args[1]
        if self._live(key) != owner:
            return 0
        if "set" in script:
            self.values[key] = (str(keys_and_args[2]), time.time() + int(keys_and_args[3]))
            return 1
        if "del" in script:
            self.delete(key)
            return 1
        self.values[key] = (owner, time.time() + int(keys_and_args[2]))
        return 1


def install_memory_claim_store(monkeypatch: Any) -> MemoryClaimRedis:
    memory = MemoryClaimRedis()

    def _client(self: RedisClaimStore) -> MemoryClaimRedis:
        if self._redis is not None:
            return self._redis  # type: ignore[no-any-return]
        self._redis = memory
        return memory

    monkeypatch.setattr(RedisClaimStore, "_client", _client)
    return memory
