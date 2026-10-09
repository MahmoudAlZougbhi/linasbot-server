"""Startup, readiness, and liveness payloads. No secret values."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

_READY_BUDGET_SECONDS = 0.2


def live_payload() -> dict[str, Any]:
    return {"ok": True, "role": "live"}


def startup_payload(*, migrations_at_head: bool | None) -> dict[str, Any]:
    if migrations_at_head is None:
        return {"ok": True, "role": "startup", "migrations": "skipped"}
    return {"ok": migrations_at_head, "role": "startup", "migrations": "head" if migrations_at_head else "behind"}


def ready_payload(
    *,
    pg_seconds: float | None,
    valkey_ok: bool | None,
    spaces_configured: bool | None,
    flags_ok: bool,
    strict: bool,
) -> dict[str, Any]:
    checks: dict[str, Any] = {}
    ok = True

    def consider(name: str, passed: bool | None, *, required: bool) -> None:
        nonlocal ok
        if passed is None:
            checks[name] = {"ok": True, "configured": False}
            if strict and required:
                ok = False
            return
        checks[name] = {"ok": passed, "configured": True}
        if not passed:
            ok = False

    pg_passed = None if pg_seconds is None else pg_seconds < _READY_BUDGET_SECONDS
    consider("postgres", pg_passed, required=True)
    consider("valkey", valkey_ok, required=True)
    consider("spaces", spaces_configured, required=True)
    checks["feature_flags"] = {"ok": flags_ok}
    if not flags_ok:
        ok = False
    return {"ok": ok, "role": "ready", "checks": checks}


def measure(probe: Callable[[], bool] | None) -> bool | None:
    if probe is None:
        return None
    try:
        return bool(probe())
    except Exception:
        return False
