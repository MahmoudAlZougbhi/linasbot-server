"""Closed schemas for the Managed Postgres firewall transaction."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from datetime import timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final

if TYPE_CHECKING:
    from scripts.ha import managed_pg_firewall_authority as authority
    from scripts.ha import managed_pg_firewall_provider as provider
elif __package__:
    from . import managed_pg_firewall_authority as authority
    from . import managed_pg_firewall_provider as provider
else:
    import managed_pg_firewall_authority as authority
    import managed_pg_firewall_provider as provider

FirewallContractError = authority.FirewallContractError
canonical = authority.canonical
parse_time = authority.parse_time
sha256 = authority.sha256

CLUSTER_ID: Final = "17d6fb7e-30d7-442a-a716-5c5344639659"
CLUSTER_NAME: Final = "linas-postgres-prod"
DESIRED_RULES: Final = (
    {"type": "droplet", "value": "510629908"},
    {"type": "droplet", "value": "591901417"},
    {"type": "tag", "value": "linas"},
)
PLAN_FORMAT: Final = "linas-managed-pg-firewall-plan-v1"
ROLLBACK_FORMAT: Final = "linas-managed-pg-firewall-rollback-v1"
PLAN_TTL_SECONDS: Final = 300
SHA_RE: Final = re.compile(r"[0-9a-f]{64}")
PLAN_ID_RE: Final = re.compile(r"mpf_[0-9a-f]{64}")
TAG_NAME: Final = "linas"
EXPECTED_TAG_MEMBERS: Final = ("510629908", "591901417")


def rules_sha256(rules: Sequence[Mapping[str, str]]) -> str:
    return sha256(canonical(list(rules)))


def normalize_rules(raw: object) -> list[dict[str, str]]:
    return authority.normalize_rules(
        raw,
        cluster_id=CLUSTER_ID,
        allowed_types=provider.ALLOWED_RULE_TYPES,
        allowed_keys=provider.RULE_KEYS,
    )


def desired_rules() -> list[dict[str, str]]:
    return normalize_rules(list(DESIRED_RULES))


def require_desired_tag_members(
    rules: Sequence[Mapping[str, str]],
    tag_members: Sequence[str],
) -> None:
    desired_tags = [rule["value"] for rule in rules if rule["type"] == "tag"]
    if any(tag != TAG_NAME for tag in desired_tags):
        raise FirewallContractError("firewall plan contains an unattested dynamic tag")
    if desired_tags and tuple(tag_members) != EXPECTED_TAG_MEMBERS:
        raise FirewallContractError("linas tag membership differs from the fixed policy")


def validate_plan(raw: object) -> dict[str, Any]:
    keys = {
        "format",
        "operation",
        "plan_id",
        "cluster_id",
        "cluster_name",
        "authority_dir",
        "plan_path",
        "created_at",
        "expires_at",
        "doctl_path",
        "doctl_sha256",
        "current_rules",
        "current_sha256",
        "desired_rules",
        "desired_sha256",
        "tag_member_ids",
        "tag_members_sha256",
        "source_plan_id",
        "source_plan_sha256",
        "source_rollback_path",
        "source_rollback_sha256",
    }
    if not isinstance(raw, dict) or set(raw) != keys or raw.get("format") != PLAN_FORMAT:
        raise FirewallContractError("firewall plan schema is invalid")
    if (
        raw.get("operation") not in {"replace", "restore"}
        or PLAN_ID_RE.fullmatch(str(raw.get("plan_id") or "")) is None
    ):
        raise FirewallContractError("firewall plan identity is invalid")
    if raw.get("cluster_id") != CLUSTER_ID or raw.get("cluster_name") != CLUSTER_NAME:
        raise FirewallContractError("firewall plan targets another cluster")
    authority_dir = raw.get("authority_dir")
    plan_path = raw.get("plan_path")
    if (
        not isinstance(authority_dir, str)
        or not isinstance(plan_path, str)
        or not Path(authority_dir).is_absolute()
        or not Path(plan_path).is_absolute()
        or Path(plan_path).parent != Path(authority_dir)
    ):
        raise FirewallContractError("firewall plan authority namespace is invalid")
    created = parse_time(raw.get("created_at"))
    expires = parse_time(raw.get("expires_at"))
    if expires <= created or expires - created != timedelta(seconds=PLAN_TTL_SECONDS):
        raise FirewallContractError("firewall plan validity window is invalid")
    doctl_path = raw.get("doctl_path")
    if (
        not isinstance(doctl_path, str)
        or not Path(doctl_path).is_absolute()
        or SHA_RE.fullmatch(str(raw.get("doctl_sha256") or "")) is None
    ):
        raise FirewallContractError("firewall plan tool authority is invalid")
    current = normalize_rules(raw.get("current_rules"))
    desired = normalize_rules(raw.get("desired_rules"))
    if current != raw["current_rules"] or desired != raw["desired_rules"]:
        raise FirewallContractError("firewall plan rules are not canonical")
    if raw.get("current_sha256") != rules_sha256(current) or raw.get("desired_sha256") != rules_sha256(desired):
        raise FirewallContractError("firewall plan rule digest is invalid")
    tag_members = raw.get("tag_member_ids")
    if (
        not isinstance(tag_members, list)
        or any(not isinstance(value, str) or not value.isdigit() or int(value) < 1 for value in tag_members)
        or tag_members != sorted(set(tag_members), key=int)
        or raw.get("tag_members_sha256") != sha256(canonical(tag_members))
    ):
        raise FirewallContractError("firewall plan tag membership is invalid")
    require_desired_tag_members(desired, tag_members)
    if raw["operation"] == "replace" and desired != desired_rules():
        raise FirewallContractError("firewall replacement differs from the fixed policy")
    _validate_plan_source(raw)
    return dict(raw)


def _validate_plan_source(raw: Mapping[str, Any]) -> None:
    source_id = raw.get("source_plan_id")
    source_plan_sha = raw.get("source_plan_sha256")
    source_path = raw.get("source_rollback_path")
    source_sha = raw.get("source_rollback_sha256")
    source_values = (source_id, source_plan_sha, source_path, source_sha)
    if (
        not isinstance(source_id, str)
        or not isinstance(source_plan_sha, str)
        or not isinstance(source_path, str)
        or not isinstance(source_sha, str)
    ):
        raise FirewallContractError("firewall plan rollback authority is invalid")
    if raw["operation"] == "replace" and any(source_values):
        raise FirewallContractError("firewall plan rollback authority is inconsistent")
    if raw["operation"] == "restore" and (
        PLAN_ID_RE.fullmatch(source_id) is None
        or SHA_RE.fullmatch(source_plan_sha) is None
        or not Path(source_path).is_absolute()
        or Path(source_path).parent != Path(raw["authority_dir"])
        or SHA_RE.fullmatch(source_sha) is None
    ):
        raise FirewallContractError("firewall plan rollback authority is inconsistent")


def confirmation(plan: Mapping[str, Any], payload: bytes) -> str:
    prefix = "REPLACE" if plan["operation"] == "replace" else "RESTORE"
    return (
        f"{prefix}_MANAGED_PG_FIREWALL:{plan['plan_id']}:{CLUSTER_ID}:"
        f"{plan['current_sha256']}:{plan['desired_sha256']}:{sha256(payload)}"
    )


def validate_rollback(raw: object) -> dict[str, Any]:
    keys = {
        "format",
        "plan_id",
        "plan_sha256",
        "operation",
        "cluster_id",
        "authority_dir",
        "plan_path",
        "rollback_path",
        "created_at",
        "doctl_path",
        "doctl_sha256",
        "previous_rules",
        "previous_sha256",
        "intended_rules",
        "intended_sha256",
    }
    if not isinstance(raw, dict) or set(raw) != keys or raw.get("format") != ROLLBACK_FORMAT:
        raise FirewallContractError("firewall rollback schema is invalid")
    if (
        PLAN_ID_RE.fullmatch(str(raw.get("plan_id") or "")) is None
        or SHA_RE.fullmatch(str(raw.get("plan_sha256") or "")) is None
        or raw.get("operation") not in {"replace", "restore"}
    ):
        raise FirewallContractError("firewall rollback identity is invalid")
    if raw.get("cluster_id") != CLUSTER_ID:
        raise FirewallContractError("firewall rollback targets another cluster")
    authority_dir = raw.get("authority_dir")
    plan_path = raw.get("plan_path")
    rollback_path = raw.get("rollback_path")
    if (
        not isinstance(authority_dir, str)
        or not isinstance(plan_path, str)
        or not isinstance(rollback_path, str)
        or not Path(authority_dir).is_absolute()
        or not Path(plan_path).is_absolute()
        or not Path(rollback_path).is_absolute()
        or Path(plan_path).parent != Path(authority_dir)
        or Path(rollback_path).parent != Path(authority_dir)
    ):
        raise FirewallContractError("firewall rollback authority namespace is invalid")
    parse_time(raw.get("created_at"))
    if (
        not isinstance(raw.get("doctl_path"), str)
        or not Path(raw["doctl_path"]).is_absolute()
        or SHA_RE.fullmatch(str(raw.get("doctl_sha256") or "")) is None
    ):
        raise FirewallContractError("firewall rollback tool authority is invalid")
    previous = normalize_rules(raw.get("previous_rules"))
    intended = normalize_rules(raw.get("intended_rules"))
    if previous != raw["previous_rules"] or intended != raw["intended_rules"]:
        raise FirewallContractError("firewall rollback rules are not canonical")
    if raw.get("previous_sha256") != rules_sha256(previous) or raw.get("intended_sha256") != rules_sha256(intended):
        raise FirewallContractError("firewall rollback digest is invalid")
    return dict(raw)
