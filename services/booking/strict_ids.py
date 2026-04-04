# -*- coding: utf-8 -*-
"""Strict ID validation against live CRM lists — no fuzzy name resolution."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple


def _sid(row: dict) -> Optional[int]:
    try:
        v = row.get("id")
        if v is None or v is False:
            return None
        i = int(v)
        return i if i > 0 else None
    except (TypeError, ValueError):
        return None


def strict_validate_service_id(
    service_id: Optional[Any], services: List[dict]
) -> Tuple[Optional[int], str]:
    """Returns (id, status) where status is ok | missing | invalid."""
    if service_id is None or (isinstance(service_id, str) and not str(service_id).strip()):
        return None, "missing"
    try:
        sid = int(service_id)
    except (TypeError, ValueError):
        return None, "invalid"
    allowed = {_sid(s) for s in services}
    allowed.discard(None)
    if sid not in allowed:
        return None, "invalid"
    return sid, "ok"


def strict_validate_branch_id(
    branch_id: Optional[Any], branches: List[dict]
) -> Tuple[Optional[int], str]:
    if branch_id is None or (isinstance(branch_id, str) and not str(branch_id).strip()):
        return None, "missing"
    try:
        bid = int(branch_id)
    except (TypeError, ValueError):
        return None, "invalid"
    allowed = {_sid(b) for b in branches}
    allowed.discard(None)
    if bid not in allowed:
        return None, "invalid"
    return bid, "ok"


def strict_validate_machine_id(
    machine_id: Optional[Any], machines: List[dict]
) -> Tuple[Optional[int], str]:
    if machine_id is None or (isinstance(machine_id, str) and not str(machine_id).strip()):
        return None, "missing"
    try:
        mid = int(machine_id)
    except (TypeError, ValueError):
        return None, "invalid"
    allowed = {_sid(m) for m in machines}
    allowed.discard(None)
    if mid not in allowed:
        return None, "invalid"
    return mid, "ok"
