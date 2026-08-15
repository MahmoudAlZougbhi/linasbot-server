"""Immutable replay authority for Managed Postgres firewall transactions."""

from __future__ import annotations

import hmac
import re
from collections.abc import Mapping
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from scripts.ha import managed_pg_firewall_authority as authority
elif __package__:
    from . import managed_pg_firewall_authority as authority
else:
    import managed_pg_firewall_authority as authority

FirewallContractError = authority.FirewallContractError
canonical = authority.canonical
secure_read = authority.secure_read
sha256 = authority.sha256
write_once = authority.write_once

INTENT_FORMAT = "linas-managed-pg-firewall-intent-v1"
COMPLETE_FORMAT = "linas-managed-pg-firewall-complete-v1"
SUPERSEDE_FORMAT = "linas-managed-pg-firewall-supersede-v1"
PLAN_ID_RE = re.compile(r"mpf_[0-9a-f]{64}")
KINDS = frozenset({"intent", "complete", "superseded"})


def receipt_path(parent: Path, plan_id: str, kind: str) -> Path:
    if PLAN_ID_RE.fullmatch(plan_id) is None or kind not in KINDS:
        raise FirewallContractError("firewall transaction receipt identity is invalid")
    return parent / f"managed-pg-firewall-{plan_id}.{kind}.json"


def intent(
    *,
    cluster_id: str,
    plan_id: str,
    plan_sha256: str,
    operation: str,
    authority_dir: Path,
    plan_path: Path,
    rollback_path: Path,
    rollback_sha256: str,
    current_sha256: str,
    desired_sha256: str,
) -> dict[str, object]:
    return {
        "format": INTENT_FORMAT,
        "cluster_id": cluster_id,
        "plan_id": plan_id,
        "plan_sha256": plan_sha256,
        "operation": operation,
        "authority_dir": str(authority_dir),
        "plan_path": str(plan_path),
        "rollback_path": str(rollback_path),
        "rollback_sha256": rollback_sha256,
        "current_sha256": current_sha256,
        "desired_sha256": desired_sha256,
    }


def completion(*, transaction_intent: Mapping[str, object]) -> dict[str, object]:
    return {
        "format": COMPLETE_FORMAT,
        "cluster_id": transaction_intent["cluster_id"],
        "plan_id": transaction_intent["plan_id"],
        "plan_sha256": transaction_intent["plan_sha256"],
        "intent_sha256": sha256(canonical(dict(transaction_intent))),
        "operation": transaction_intent["operation"],
        "rollback_sha256": transaction_intent["rollback_sha256"],
        "desired_sha256": transaction_intent["desired_sha256"],
    }


def supersede(
    *,
    cluster_id: str,
    source_intent: Mapping[str, object],
    source_rollback_sha256: str,
    restore_plan_id: str,
    restore_plan_sha256: str,
    restore_intent_sha256: str,
) -> dict[str, object]:
    return {
        "format": SUPERSEDE_FORMAT,
        "cluster_id": cluster_id,
        "source_plan_id": source_intent["plan_id"],
        "source_plan_sha256": source_intent["plan_sha256"],
        "source_intent_sha256": sha256(canonical(dict(source_intent))),
        "source_rollback_sha256": source_rollback_sha256,
        "restore_plan_id": restore_plan_id,
        "restore_plan_sha256": restore_plan_sha256,
        "restore_intent_sha256": restore_intent_sha256,
    }


def require(path: Path, expected: Mapping[str, object]) -> None:
    payload = canonical(dict(expected))
    try:
        actual = secure_read(path, allow_transaction_authority=True)
    except FileNotFoundError as exc:
        raise FirewallContractError("required firewall transaction receipt is missing") from exc
    if not hmac.compare_digest(actual, payload):
        raise FirewallContractError("firewall transaction receipt differs")


def ensure(path: Path, expected: Mapping[str, object]) -> None:
    write_once(path, canonical(dict(expected)), allow_transaction_authority=True)


def exists(path: Path) -> bool:
    return path.exists() or path.is_symlink()
