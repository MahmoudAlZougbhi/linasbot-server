#!/usr/bin/env python3
"""Digest-bound plan/CAS/apply/restore for the one approved Managed PG firewall."""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import sys
from collections.abc import Mapping, Sequence
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final

if TYPE_CHECKING:
    from scripts.ha import managed_pg_firewall_authority as authority
    from scripts.ha import managed_pg_firewall_contract as contract
    from scripts.ha import managed_pg_firewall_provider as provider
    from scripts.ha import managed_pg_firewall_state as transaction_state
elif __package__:
    from . import managed_pg_firewall_authority as authority
    from . import managed_pg_firewall_contract as contract
    from . import managed_pg_firewall_provider as provider
    from . import managed_pg_firewall_state as transaction_state
else:
    import managed_pg_firewall_authority as authority
    import managed_pg_firewall_contract as contract
    import managed_pg_firewall_provider as provider
    import managed_pg_firewall_state as transaction_state

FirewallContractError = authority.FirewallContractError
artifact_lock = authority.artifact_lock
canonical = authority.canonical
secure_parent = authority.secure_parent
secure_read = authority.secure_read
sha256 = authority.sha256
parse_time = authority.parse_time
timestamp = authority.timestamp
write_once = authority.write_once
ensure_receipt = transaction_state.ensure
receipt_exists = transaction_state.exists
receipt_path = transaction_state.receipt_path
require_receipt = transaction_state.require
CLUSTER_ID = contract.CLUSTER_ID
CLUSTER_NAME = contract.CLUSTER_NAME
PLAN_FORMAT = contract.PLAN_FORMAT
ROLLBACK_FORMAT = contract.ROLLBACK_FORMAT
OWNER_CONFIRMATION: Final = "I_HOLD_EXCLUSIVE_MANAGED_PG_FIREWALL_UNTIL_COMPLETE"
PLAN_TTL_SECONDS = contract.PLAN_TTL_SECONDS
SHA_RE = contract.SHA_RE
TAG_NAME = contract.TAG_NAME
EXPECTED_TAG_MEMBERS = contract.EXPECTED_TAG_MEMBERS
UTC: Final = timezone.utc  # noqa: UP017 - isolated wrapper supports OS Python 3.9+.


def _rules_sha256(rules: Sequence[Mapping[str, str]]) -> str:
    return contract.rules_sha256(rules)


def _desired_rules() -> list[dict[str, str]]:
    return contract.desired_rules()


def _secure_executable(raw: str | None) -> tuple[Path, str]:
    return authority.secure_executable(raw, default_name="doctl")


def _read_rules_stable(path: Path, expected_sha256: str) -> list[dict[str, str]]:
    del path, expected_sha256
    return provider.read_rules_stable(CLUSTER_ID)


def _replace_rules(path: Path, expected_sha256: str, rules: Sequence[Mapping[str, str]]) -> None:
    del path, expected_sha256
    provider.replace_rules(CLUSTER_ID, rules)


def _read_tag_members_stable(path: Path, expected_sha256: str) -> list[str]:
    return provider.read_tag_members_stable(path, expected_sha256, TAG_NAME)


def _new_plan(
    *,
    operation: str,
    plan_path: Path,
    current_rules: Sequence[Mapping[str, str]],
    desired_rules: Sequence[Mapping[str, str]],
    tag_member_ids: Sequence[str],
    doctl_path: Path,
    doctl_sha256: str,
    source_plan_id: str = "",
    source_plan_sha256: str = "",
    source_rollback_path: str = "",
    source_rollback_sha256: str = "",
) -> dict[str, Any]:
    now = datetime.now(UTC)
    plan_id = "mpf_" + hashlib.sha256(os.urandom(32)).hexdigest()
    return contract.validate_plan(
        {
            "format": PLAN_FORMAT,
            "operation": operation,
            "plan_id": plan_id,
            "cluster_id": CLUSTER_ID,
            "cluster_name": CLUSTER_NAME,
            "authority_dir": str(plan_path.parent),
            "plan_path": str(plan_path),
            "created_at": timestamp(now),
            "expires_at": timestamp(now + timedelta(seconds=PLAN_TTL_SECONDS)),
            "doctl_path": str(doctl_path),
            "doctl_sha256": doctl_sha256,
            "current_rules": list(current_rules),
            "current_sha256": _rules_sha256(current_rules),
            "desired_rules": list(desired_rules),
            "desired_sha256": _rules_sha256(desired_rules),
            "tag_member_ids": list(tag_member_ids),
            "tag_members_sha256": sha256(canonical(list(tag_member_ids))),
            "source_plan_id": source_plan_id,
            "source_plan_sha256": source_plan_sha256,
            "source_rollback_path": source_rollback_path,
            "source_rollback_sha256": source_rollback_sha256,
        }
    )


def _load_json(path: Path) -> tuple[dict[str, Any], bytes]:
    payload = secure_read(path)
    try:
        raw = json.loads(payload)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise FirewallContractError("firewall authority is unreadable") from exc
    if not isinstance(raw, dict):
        raise FirewallContractError("firewall authority is invalid")
    return raw, payload


def _load_plan(path: Path) -> tuple[dict[str, Any], bytes]:
    raw, payload = _load_json(path)
    plan = contract.validate_plan(raw)
    if payload != canonical(plan) or path != Path(plan["plan_path"]) or path.parent != Path(plan["authority_dir"]):
        raise FirewallContractError("firewall plan is not canonical")
    return plan, payload


def _rollback_for(plan: Mapping[str, Any], plan_payload: bytes, rollback_path: Path) -> dict[str, Any]:
    return contract.validate_rollback(
        {
            "format": ROLLBACK_FORMAT,
            "plan_id": plan["plan_id"],
            "plan_sha256": sha256(plan_payload),
            "operation": plan["operation"],
            "cluster_id": CLUSTER_ID,
            "authority_dir": plan["authority_dir"],
            "plan_path": plan["plan_path"],
            "rollback_path": str(rollback_path),
            "created_at": plan["created_at"],
            "doctl_path": plan["doctl_path"],
            "doctl_sha256": plan["doctl_sha256"],
            "previous_rules": plan["current_rules"],
            "previous_sha256": plan["current_sha256"],
            "intended_rules": plan["desired_rules"],
            "intended_sha256": plan["desired_sha256"],
        }
    )


def _intent_for(
    plan: Mapping[str, Any],
    plan_payload: bytes,
    rollback_path: Path,
    rollback_payload: bytes,
) -> dict[str, object]:
    return transaction_state.intent(
        cluster_id=CLUSTER_ID,
        plan_id=str(plan["plan_id"]),
        plan_sha256=sha256(plan_payload),
        operation=str(plan["operation"]),
        authority_dir=Path(str(plan["authority_dir"])),
        plan_path=Path(str(plan["plan_path"])),
        rollback_path=rollback_path,
        rollback_sha256=sha256(rollback_payload),
        current_sha256=str(plan["current_sha256"]),
        desired_sha256=str(plan["desired_sha256"]),
    )


def _source_intent(rollback: Mapping[str, Any], rollback_payload: bytes) -> dict[str, object]:
    return transaction_state.intent(
        cluster_id=CLUSTER_ID,
        plan_id=str(rollback["plan_id"]),
        plan_sha256=str(rollback["plan_sha256"]),
        operation=str(rollback["operation"]),
        authority_dir=Path(str(rollback["authority_dir"])),
        plan_path=Path(str(rollback["plan_path"])),
        rollback_path=Path(str(rollback["rollback_path"])),
        rollback_sha256=sha256(rollback_payload),
        current_sha256=str(rollback["previous_sha256"]),
        desired_sha256=str(rollback["intended_sha256"]),
    )


def _plan(path: Path, doctl: str | None) -> int:
    parent = secure_parent(path)
    doctl_path, doctl_sha = _secure_executable(doctl)
    with artifact_lock(parent):
        current = _read_rules_stable(doctl_path, doctl_sha)
        if any(rule["type"] == "tag" and rule["value"] != TAG_NAME for rule in current):
            raise FirewallContractError("current firewall contains an unattested dynamic tag")
        tag_members = _read_tag_members_stable(doctl_path, doctl_sha)
        contract.require_desired_tag_members(_desired_rules(), tag_members)
        plan = _new_plan(
            operation="replace",
            plan_path=path,
            current_rules=current,
            desired_rules=_desired_rules(),
            tag_member_ids=tag_members,
            doctl_path=doctl_path,
            doctl_sha256=doctl_sha,
        )
        payload = canonical(plan)
        write_once(path, payload)
    print(f"PLAN_SHA256={sha256(payload)}")
    print(f"CURRENT_SHA256={plan['current_sha256']}")
    print(f"DESIRED_SHA256={plan['desired_sha256']}")
    print(f"APPLY_CONFIRMATION={contract.confirmation(plan, payload)}")
    return 0


def _restore_plan(source: Path, destination: Path, expected_source_sha256: str, doctl: str) -> int:
    parent = secure_parent(destination)
    if source.parent != parent:
        raise FirewallContractError("restore authorities must share one protected directory")
    with artifact_lock(parent):
        raw, source_payload = _load_json(source)
        if SHA_RE.fullmatch(expected_source_sha256) is None or not hmac.compare_digest(
            sha256(source_payload), expected_source_sha256
        ):
            raise PermissionError("exact firewall rollback artifact digest is missing")
        rollback = contract.validate_rollback(raw)
        if source_payload != canonical(rollback):
            raise FirewallContractError("firewall rollback is not canonical")
        if any(rule["type"] == "tag" and rule["value"] != TAG_NAME for rule in rollback["previous_rules"]):
            raise FirewallContractError("rollback contains an unattested dynamic tag")
        if source != Path(rollback["rollback_path"]) or Path(rollback["authority_dir"]) != parent:
            raise FirewallContractError("firewall rollback moved from its authority namespace")
        source_intent = _source_intent(rollback, source_payload)
        require_receipt(receipt_path(parent, str(rollback["plan_id"]), "intent"), source_intent)
        doctl_path, doctl_sha = _secure_executable(doctl)
        current = _read_rules_stable(doctl_path, doctl_sha)
        tag_members = _read_tag_members_stable(doctl_path, doctl_sha)
        contract.require_desired_tag_members(rollback["previous_rules"], tag_members)
        plan = _new_plan(
            operation="restore",
            plan_path=destination,
            current_rules=current,
            desired_rules=rollback["previous_rules"],
            tag_member_ids=tag_members,
            doctl_path=doctl_path,
            doctl_sha256=doctl_sha,
            source_plan_id=str(rollback["plan_id"]),
            source_plan_sha256=str(rollback["plan_sha256"]),
            source_rollback_path=str(source),
            source_rollback_sha256=sha256(source_payload),
        )
        payload = canonical(plan)
        write_once(destination, payload)
    print(f"PLAN_SHA256={sha256(payload)}")
    print(f"RESTORE_CONFIRMATION={contract.confirmation(plan, payload)}")
    return 0


def _source_supersede_authority(
    parent: Path,
    plan: Mapping[str, Any],
    plan_payload: bytes,
    restore_intent: Mapping[str, object],
) -> tuple[Path, dict[str, object]]:
    source_path = Path(str(plan["source_rollback_path"]))
    if source_path.parent != parent:
        raise FirewallContractError("restore source left its authority namespace")
    raw, source_payload = _load_json(source_path)
    rollback = contract.validate_rollback(raw)
    if (
        source_payload != canonical(rollback)
        or sha256(source_payload) != plan["source_rollback_sha256"]
        or rollback["plan_id"] != plan["source_plan_id"]
        or rollback["plan_sha256"] != plan["source_plan_sha256"]
        or rollback["previous_rules"] != plan["desired_rules"]
    ):
        raise FirewallContractError("restore source lineage differs")
    source_intent = _source_intent(rollback, source_payload)
    require_receipt(receipt_path(parent, str(rollback["plan_id"]), "intent"), source_intent)
    terminal = transaction_state.supersede(
        cluster_id=CLUSTER_ID,
        source_intent=source_intent,
        source_rollback_sha256=sha256(source_payload),
        restore_plan_id=str(plan["plan_id"]),
        restore_plan_sha256=sha256(plan_payload),
        restore_intent_sha256=sha256(canonical(dict(restore_intent))),
    )
    return receipt_path(parent, str(rollback["plan_id"]), "superseded"), terminal


def _apply(plan_path: Path, rollback_path: Path, confirmation: str, owner_confirmation: str, operation: str) -> int:
    parent = secure_parent(plan_path)
    if secure_parent(rollback_path) != parent or rollback_path == plan_path:
        raise FirewallContractError("firewall authorities must share one protected directory")
    if owner_confirmation != OWNER_CONFIRMATION:
        raise PermissionError("exclusive Managed Postgres firewall ownership is unconfirmed")
    with artifact_lock(parent):
        plan, plan_payload = _load_plan(plan_path)
        if plan["operation"] != operation or not hmac.compare_digest(
            confirmation, contract.confirmation(plan, plan_payload)
        ):
            raise PermissionError("exact Managed Postgres firewall confirmation is missing")
        doctl_path, doctl_sha = _secure_executable(str(plan["doctl_path"]))
        if not hmac.compare_digest(doctl_sha, str(plan["doctl_sha256"])):
            raise FirewallContractError("firewall plan tool authority changed")
        plan_id = str(plan["plan_id"])
        intent_path = receipt_path(parent, plan_id, "intent")
        complete_path = receipt_path(parent, plan_id, "complete")
        superseded_path = receipt_path(parent, plan_id, "superseded")
        if receipt_exists(superseded_path):
            raise PermissionError("Managed Postgres firewall plan was superseded by restore")
        rollback = _rollback_for(plan, plan_payload, rollback_path)
        rollback_payload = canonical(rollback)
        intent = _intent_for(plan, plan_payload, rollback_path, rollback_payload)
        completed = transaction_state.completion(transaction_intent=intent)
        source_terminal: tuple[Path, dict[str, object]] | None = None
        if operation == "restore":
            source_terminal = _source_supersede_authority(parent, plan, plan_payload, intent)
        started = receipt_exists(intent_path) or bool(source_terminal and receipt_exists(source_terminal[0]))
        if receipt_exists(intent_path):
            require_receipt(intent_path, intent)
        if source_terminal and receipt_exists(source_terminal[0]):
            require_receipt(*source_terminal)
        if not started:
            now = datetime.now(UTC)
            if now < parse_time(plan["created_at"]) - timedelta(seconds=30) or now > parse_time(plan["expires_at"]):
                raise PermissionError("Managed Postgres firewall plan expired")
        if receipt_exists(complete_path):
            require_receipt(intent_path, intent)
            require_receipt(complete_path, completed)
            write_once(rollback_path, rollback_payload)
            current = _read_rules_stable(doctl_path, doctl_sha)
            tag_members = _read_tag_members_stable(doctl_path, doctl_sha)
            if current != plan["desired_rules"] or tag_members != plan["tag_member_ids"]:
                raise PermissionError("completed Managed Postgres firewall plan is no longer current")
            print(f"OK: MANAGED_PG_FIREWALL_{operation.upper()}_VERIFIED")
            print(f"ROLLBACK_ARTIFACT_SHA256={sha256(rollback_payload)}")
            return 0
        current = _read_rules_stable(doctl_path, doctl_sha)
        tag_members = _read_tag_members_stable(doctl_path, doctl_sha)
        if tag_members != plan["tag_member_ids"]:
            raise PermissionError("Managed Postgres tag membership changed")
        current_sha = _rules_sha256(current)
        if current_sha not in {str(plan["current_sha256"]), str(plan["desired_sha256"])} or (
            not started and current_sha != plan["current_sha256"]
        ):
            raise PermissionError("Managed Postgres firewall baseline changed")
        if not started and datetime.now(UTC) > parse_time(plan["expires_at"]):
            raise PermissionError("Managed Postgres firewall plan expired")
        write_once(rollback_path, rollback_payload)
        if source_terminal:
            ensure_receipt(*source_terminal)
        if not receipt_exists(intent_path):
            ensure_receipt(intent_path, intent)
        if current != plan["desired_rules"]:
            _replace_rules(doctl_path, doctl_sha, plan["desired_rules"])
        observed = _read_rules_stable(doctl_path, doctl_sha)
        observed_members = _read_tag_members_stable(doctl_path, doctl_sha)
        if observed != plan["desired_rules"] or observed_members != plan["tag_member_ids"]:
            raise FirewallContractError("Managed Postgres firewall postcondition differs; use restore-plan")
        ensure_receipt(complete_path, completed)
    print(f"OK: MANAGED_PG_FIREWALL_{operation.upper()}_VERIFIED")
    print(f"ROLLBACK_ARTIFACT_SHA256={sha256(rollback_payload)}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--plan", action="store_true")
    mode.add_argument("--apply", action="store_true")
    mode.add_argument("--restore-plan", action="store_true")
    mode.add_argument("--restore", action="store_true")
    parser.add_argument("--plan-artifact", type=Path, required=True)
    parser.add_argument("--rollback-artifact", type=Path)
    parser.add_argument("--source-rollback-artifact", type=Path)
    parser.add_argument("--expected-source-rollback-sha256", default="")
    parser.add_argument("--confirm", default="")
    parser.add_argument("--owner-confirm", default="")
    parser.add_argument("--doctl-bin")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    plan_path = args.plan_artifact.expanduser()
    if args.plan:
        if (
            args.rollback_artifact
            or args.source_rollback_artifact
            or args.expected_source_rollback_sha256
            or args.confirm
            or args.owner_confirm
        ):
            raise FirewallContractError("plan received mutation-only arguments")
        return _plan(plan_path, args.doctl_bin)
    if args.restore_plan:
        if (
            not args.source_rollback_artifact
            or not args.expected_source_rollback_sha256
            or args.rollback_artifact
            or args.confirm
            or args.owner_confirm
            or not args.doctl_bin
        ):
            raise FirewallContractError("restore-plan arguments are incomplete or invalid")
        return _restore_plan(
            args.source_rollback_artifact.expanduser(),
            plan_path,
            args.expected_source_rollback_sha256,
            args.doctl_bin,
        )
    if (
        not args.rollback_artifact
        or args.source_rollback_artifact
        or args.expected_source_rollback_sha256
        or args.doctl_bin
    ):
        raise FirewallContractError("apply/restore arguments are incomplete or invalid")
    operation = "restore" if args.restore else "replace"
    return _apply(
        plan_path,
        args.rollback_artifact.expanduser(),
        args.confirm,
        args.owner_confirm,
        operation,
    )


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:  # noqa: BLE001 - never expose provider output, paths, or IDs.
        print(f"ERROR: Managed Postgres firewall transaction failed ({type(exc).__name__})", file=sys.stderr)
        raise SystemExit(2) from None
