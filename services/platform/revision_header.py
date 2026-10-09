"""Monotonic config revisions. A process must not serve an older revision."""

from __future__ import annotations

_SEEN: dict[str, int] = {}


class StaleConfigRead(Exception):
    def __init__(self, tenant_id: str, seen: int, offered: int) -> None:
        super().__init__(f"{tenant_id} revision {offered} is older than {seen}")
        self.tenant_id = tenant_id
        self.seen = seen
        self.offered = offered


def reset_for_tests() -> None:
    _SEEN.clear()


def observe_revision(tenant_id: str, revision: int) -> dict[str, str]:
    previous = _SEEN.get(tenant_id)
    if previous is not None and revision < previous:
        raise StaleConfigRead(tenant_id, previous, revision)
    _SEEN[tenant_id] = revision if previous is None else max(previous, revision)
    return {"X-Config-Revision": str(revision)}
