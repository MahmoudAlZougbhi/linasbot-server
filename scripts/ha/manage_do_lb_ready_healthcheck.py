#!/usr/bin/env python3
"""CAS-guarded DigitalOcean readiness health-check cutover and rollback.

Run this on the owner's trusted operator workstation, never on either production
node.  ``plan`` is read-only.  ``apply`` mutates only the one observed load
balancer, preserves the complete API-update projection in an invoking-user-owned
0600 snapshot, and restores that exact projection automatically when read-back
cannot prove the requested one-field change.  A successful apply writes a 0600
attestation containing the exact ready-state projection and digest consumed by
the separate production bootstrap.

Authentication comes only from an existing ``doctl`` context or one token read
from stdin.  Tokens are never accepted through argv or environment variables.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import re
import stat
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

_contract_spec = importlib.util.spec_from_file_location(
    "do_lb_ready_contract",
    Path(__file__).with_name("do_lb_ready_contract.py"),
)
if _contract_spec is None or _contract_spec.loader is None:
    raise RuntimeError("DigitalOcean ready contract module is missing")
_contract = importlib.util.module_from_spec(_contract_spec)
_contract_spec.loader.exec_module(_contract)
LB_HEALTH_CONTRACT = _contract.LB_HEALTH_CONTRACT
LB_READY_PROJECTION_KEYS = _contract.LB_READY_PROJECTION_KEYS
validate_observed_get_routing = _contract.validate_observed_get_routing
validate_ready_projection_keyset = _contract.validate_ready_projection_keyset
validate_ready_projection_values = _contract.validate_ready_projection_values
validate_mutable_projection_routing_values = _contract.validate_mutable_projection_routing_values

LB_ID = "2535b8ff-b89c-442b-b5bf-91eae51ed3f6"
LB_NAME = _contract.LB_NAME
LB_IP = "157.245.31.104"
LB_SUBNET_UUID = _contract.LB_SUBNET_UUID
LB_VPC_UUID = _contract.LB_VPC_UUID
EXPECTED_DROPLET_IDS = _contract.LB_DROPLETS
API_ROOT = "https://api.digitalocean.com/v2/load_balancers"
OLD_HEALTH_PATH = _contract.OLD_HEALTH_PATH
READY_HEALTH_PATH = _contract.READY_HEALTH_PATH
_API_TOKEN: str | None = None
FAILOVER_ATTESTATION_SCHEMA = "linas-do-lb-failover-phase-attestation-v1"
READY_ATTESTATION_SCHEMA = 2
FAILOVER_PHASES = ("initial", "replay", "closeout")
FAILOVER_OBSERVATIONS = ("pre", "post")
_FAILOVER_TX_RE = re.compile(r"mft_[0-9a-f]{64}")
_UTC_RE = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?Z")

# DigitalOcean's update endpoint is full-representation, not a one-field PATCH.
# Refuse unknown response fields rather than accidentally resetting a new
# mutable property.  `region` is normalized from the GET object to its slug.
UPDATE_KEYS = frozenset(
    {
        "name",
        "region",
        "size",
        "size_unit",
        "forwarding_rules",
        "health_check",
        "sticky_sessions",
        "redirect_http_to_https",
        "enable_proxy_protocol",
        "enable_backend_keepalive",
        "vpc_uuid",
        "subnet_uuid",
        "disable_lets_encrypt_dns_records",
        "tls_cipher_policy",
        "droplet_ids",
        "tag",
        "project_id",
        "firewall",
        "http_idle_timeout_seconds",
        "glb_settings",
        "glb_cdn_settings",
        "domains",
        "target_load_balancer_ids",
        # Immutable after creation, but part of the provider's documented full
        # update representation. Preserve the already-validated exact values.
        "network_stack",
        "type",
    }
)
# The closed response-only allowlist intentionally excludes every field in the
# documented full PUT representation. Deprecated ``algorithm`` can no longer
# be specified, so it is validated but omitted.
READ_ONLY_KEYS = frozenset(
    {
        "id",
        "ip",
        "ipv6",
        "status",
        "created_at",
        "urn",
        "algorithm",
    }
)

# Exact reviewed full PUT representation — see do_lb_ready_contract.py.


def _canonical(value: Any) -> bytes:
    return json.dumps(value, allow_nan=False, separators=(",", ":"), sort_keys=True).encode()


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _require_digest(value: str, label: str) -> str:
    normalized = str(value or "").strip().lower()
    if len(normalized) != 64 or any(char not in "0123456789abcdef" for char in normalized):
        raise ValueError(f"{label} must be a lowercase SHA-256 digest")
    return normalized


def _validate_token(token: str) -> str:
    if len(token) < 32 or len(token) > 8192 or any(char in token for char in "\r\n\0"):
        raise PermissionError("DigitalOcean authentication material is invalid")
    return token


def _configure_auth(auth_source: str) -> None:
    global _API_TOKEN
    if _API_TOKEN is not None:
        raise RuntimeError("DigitalOcean authentication is already configured")
    if auth_source == "doctl":
        # Prevent an ambient provider-token environment variable from changing
        # which credential the local doctl context returns.
        child_env = {
            key: value
            for key, value in os.environ.items()
            if key not in {"DIGITALOCEAN_TOKEN", "DIGITALOCEAN_ACCESS_TOKEN"}
        }
        result = subprocess.run(
            ["doctl", "auth", "token"],
            env=child_env,
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
        if result.returncode:
            raise PermissionError("the selected local doctl context did not provide a token")
        token = result.stdout.strip()
    elif auth_source == "stdin":
        raw = sys.stdin.buffer.read(8193)
        if len(raw) > 8192:
            raise PermissionError("stdin authentication material is too large")
        try:
            token = raw.decode("utf-8", errors="strict").strip()
        except UnicodeDecodeError as exc:
            raise PermissionError("stdin authentication material is invalid") from exc
    else:
        raise ValueError("unknown DigitalOcean authentication source")
    _API_TOKEN = _validate_token(token)


def _token() -> str:
    if _API_TOKEN is None:
        raise PermissionError("DigitalOcean authentication is not configured")
    return _API_TOKEN


def _request(method: str, *, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    body = None if payload is None else _canonical(payload)
    request = urllib.request.Request(
        f"{API_ROOT}/{LB_ID}",
        data=body,
        method=method,
        headers={
            "Authorization": f"Bearer {_token()}",
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": "linasbot-meta-ha-bootstrap/1",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            raw = response.read()
            if response.status not in ({200} if method == "GET" else {200, 202}):
                raise RuntimeError("DigitalOcean API returned an unexpected status")
    except urllib.error.HTTPError as exc:
        # Never print the provider response; it can contain account metadata.
        raise RuntimeError(f"DigitalOcean API request failed with HTTP {exc.code}") from exc
    if not raw:
        return {}
    parsed = json.loads(raw)
    if not isinstance(parsed, dict):
        raise RuntimeError("DigitalOcean API response is not an object")
    return parsed


def _get_load_balancer() -> dict[str, Any]:
    wrapper = _request("GET")
    value = wrapper.get("load_balancer")
    if not isinstance(value, dict):
        raise RuntimeError("DigitalOcean response has no load_balancer object")
    return value


def update_projection(load_balancer: dict[str, Any]) -> dict[str, Any]:
    unknown = set(load_balancer) - UPDATE_KEYS - READ_ONLY_KEYS
    if unknown:
        raise RuntimeError("DigitalOcean load balancer has unhandled fields; refusing full update")
    projection = {key: load_balancer[key] for key in UPDATE_KEYS if key in load_balancer}
    if "droplet_ids" in projection:
        projection["droplet_ids"] = sorted(int(value) for value in projection["droplet_ids"])
    region = projection.get("region")
    if isinstance(region, dict):
        slug = region.get("slug")
        if not isinstance(slug, str) or not slug:
            raise RuntimeError("DigitalOcean region identity is invalid")
        projection["region"] = slug
    if not isinstance(projection.get("name"), str) or not projection.get("forwarding_rules"):
        raise RuntimeError("DigitalOcean update projection is incomplete")
    # The current full-representation API uses size_unit. GET can still return
    # the deprecated size slug as response compatibility metadata; never send
    # both, and never drop the exact observed modern capacity.
    size_unit = projection.get("size_unit")
    if isinstance(size_unit, bool) or not isinstance(size_unit, int) or size_unit <= 0:
        raise RuntimeError("DigitalOcean load-balancer size_unit is invalid")
    projection.pop("size", None)
    # Backend selection is exact droplet membership. GET currently includes an
    # empty tag compatibility field, but PUT treats tag and droplet_ids as
    # mutually exclusive. Preserve only the exact droplet IDs.
    if "tag" in projection:
        if projection["tag"] != "":
            raise RuntimeError("DigitalOcean load-balancer tag conflicts with fixed droplet membership")
        del projection["tag"]
    return projection


def validate_observed_identity(load_balancer: dict[str, Any]) -> dict[str, Any]:
    if load_balancer.get("id") != LB_ID:
        raise RuntimeError("DigitalOcean load balancer ID changed")
    if load_balancer.get("name") != LB_NAME or load_balancer.get("ip") != LB_IP:
        raise RuntimeError("DigitalOcean load balancer name/IP identity changed")
    if load_balancer.get("status") != "active":
        raise RuntimeError("DigitalOcean load balancer is not active")
    if load_balancer.get("algorithm") != "round_robin":
        raise RuntimeError("DigitalOcean load-balancer algorithm changed")
    if load_balancer.get("size") != "lb-small":
        raise RuntimeError("DigitalOcean load-balancer size changed")
    if load_balancer.get("tag", "") != "":
        raise RuntimeError("DigitalOcean load-balancer tag conflicts with fixed droplet membership")
    if load_balancer.get("project_id") != "70160077-6e21-4fc7-9c81-45e6b60d8919":
        raise RuntimeError("DigitalOcean load-balancer project changed")
    validate_observed_get_routing(load_balancer)
    region = load_balancer.get("region")
    if not isinstance(region, dict) or region.get("slug") != "lon1":
        raise RuntimeError("DigitalOcean load-balancer region changed")
    droplet_ids = sorted(int(value) for value in load_balancer.get("droplet_ids") or [])
    if droplet_ids != EXPECTED_DROPLET_IDS:
        raise RuntimeError("DigitalOcean load balancer backend membership changed")
    forwarding = load_balancer.get("forwarding_rules")
    if not isinstance(forwarding, list) or len(forwarding) != 2:
        raise RuntimeError("DigitalOcean forwarding-rule count changed")
    normalized_rules = {
        (
            rule.get("entry_protocol"),
            int(rule.get("entry_port") or 0),
            rule.get("target_protocol"),
            int(rule.get("target_port") or 0),
        )
        for rule in forwarding
        if isinstance(rule, dict)
    }
    if normalized_rules != {("http", 80, "http", 80), ("https", 443, "http", 80)}:
        raise RuntimeError("DigitalOcean forwarding rules changed")
    https_rule = next(rule for rule in forwarding if rule.get("entry_protocol") == "https")
    if not str(https_rule.get("certificate_id") or ""):
        raise RuntimeError("DigitalOcean HTTPS forwarding certificate is missing")
    health = load_balancer.get("health_check")
    if not isinstance(health, dict):
        raise RuntimeError("DigitalOcean health-check object is missing")
    path = health.get("path")
    if path not in {OLD_HEALTH_PATH, READY_HEALTH_PATH}:
        raise RuntimeError("DigitalOcean health-check path is not authorized")
    if health != {**LB_HEALTH_CONTRACT, "path": path}:
        raise RuntimeError("DigitalOcean health check is not the observed direct HTTP :8003 target")
    projection = update_projection(load_balancer)
    validate_ready_projection_keyset(projection)
    return projection


def desired_projection(before: dict[str, Any]) -> dict[str, Any]:
    desired = cast(dict[str, Any], json.loads(_canonical(before)))
    health = desired["health_check"]
    health["path"] = READY_HEALTH_PATH
    return desired


def apply_confirmation(before_sha256: str) -> str:
    return f"CHANGE_DO_LB_READY_{before_sha256[:16].upper()}"


def restore_confirmation(before_sha256: str) -> str:
    return f"RESTORE_DO_LB_{before_sha256[:16].upper()}"


def attest_confirmation(ready_sha256: str) -> str:
    return f"ATTEST_DO_LB_READY_{ready_sha256[:16].upper()}"


def snapshot_path_for(before_sha256: str, state_root: Path) -> Path:
    _require_digest(before_sha256, "snapshot digest")
    return state_root / f"{LB_ID}.before.{before_sha256}.json"


def attestation_path_for(ready_sha256: str, state_root: Path) -> Path:
    _require_digest(ready_sha256, "ready projection digest")
    return state_root / f"{LB_ID}.ready.{ready_sha256}.json"


def failover_attestation_path_for(
    transaction_id: str,
    manifest_sha256: str,
    phase: str,
    observation: str,
    state_root: Path,
) -> Path:
    if _FAILOVER_TX_RE.fullmatch(transaction_id) is None:
        raise ValueError("failover transaction ID is invalid")
    manifest = _require_digest(manifest_sha256, "failover manifest digest")
    if phase not in FAILOVER_PHASES:
        raise ValueError("failover attestation phase is invalid")
    if observation not in FAILOVER_OBSERVATIONS:
        raise ValueError("failover attestation observation is invalid")
    return state_root / f"{LB_ID}.failover.{transaction_id}.{manifest}.{phase}.{observation}.json"


def failover_attest_confirmation(
    ready_sha256: str,
    transaction_id: str,
    manifest_sha256: str,
    phase: str,
    observation: str,
) -> str:
    digest = _require_digest(ready_sha256, "ready projection digest")
    if _FAILOVER_TX_RE.fullmatch(transaction_id) is None:
        raise ValueError("failover transaction ID is invalid")
    manifest = _require_digest(manifest_sha256, "failover manifest digest")
    if phase not in FAILOVER_PHASES:
        raise ValueError("failover attestation phase is invalid")
    if observation not in FAILOVER_OBSERVATIONS:
        raise ValueError("failover attestation observation is invalid")
    return (
        f"ATTEST_DO_LB_FAILOVER_{phase.upper()}_{observation.upper()}_{digest[:16].upper()}_"
        f"{manifest[:8].upper()}_{transaction_id[-8:].upper()}"
    )


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _state_root(value: Path) -> Path:
    raw = os.fspath(value)
    if not os.path.isabs(raw):
        raise PermissionError("operator state directory must be an explicit absolute path")
    normalized = Path(os.path.normpath(raw))
    if os.fspath(normalized) != raw or len(normalized.parts) < 4:
        raise PermissionError("operator state directory is not a narrow canonical path")
    return normalized


def _ensure_state_root(path: Path) -> None:
    if path != _state_root(path):
        raise PermissionError("operator state directory is not canonical")
    if not path.parent.exists() or path.parent.is_symlink() or path.parent.resolve(strict=True) != path.parent:
        raise PermissionError("operator state parent must already exist without symlinks")
    parent = path.parent.lstat()
    if (
        not stat.S_ISDIR(parent.st_mode)
        or stat.S_ISLNK(parent.st_mode)
        or parent.st_uid != os.geteuid()
        or parent.st_gid != os.getegid()
    ):
        raise PermissionError("operator state parent must be owned by the invoking user")
    path.mkdir(mode=0o700, exist_ok=True)
    info = path.lstat()
    if (
        not stat.S_ISDIR(info.st_mode)
        or stat.S_ISLNK(info.st_mode)
        or info.st_uid != os.geteuid()
        or info.st_gid != os.getegid()
        or stat.S_IMODE(info.st_mode) != 0o700
        or path.resolve(strict=True) != path
    ):
        raise PermissionError("operator state directory must be invoking-user-owned mode 0700")


def _write_protected_json(path: Path, payload: dict[str, Any]) -> None:
    _ensure_state_root(path.parent)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(path, flags, 0o600)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "wb") as handle:
            fd = -1
            handle.write(_canonical(payload) + b"\n")
            handle.flush()
            os.fsync(handle.fileno())
        directory_fd = os.open(path.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        if fd >= 0:
            os.close(fd)


def _replace_protected_json(path: Path, payload: dict[str, Any]) -> None:
    """Atomically refresh one exact operator-owned phase observation."""

    _ensure_state_root(path.parent)
    if path.exists() or path.is_symlink():
        _read_protected_json(path, "phase attestation being refreshed")
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        os.fchmod(descriptor, 0o600)
        os.fchown(descriptor, os.geteuid(), os.getegid())
        with os.fdopen(descriptor, "wb") as handle:
            descriptor = -1
            handle.write(_canonical(payload) + b"\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        directory_fd = os.open(path.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def _read_protected_json(path: Path, label: str) -> dict[str, Any]:
    _ensure_state_root(path.parent)
    info = path.lstat()
    if (
        not stat.S_ISREG(info.st_mode)
        or stat.S_ISLNK(info.st_mode)
        or info.st_uid != os.geteuid()
        or info.st_gid != os.getegid()
        or stat.S_IMODE(info.st_mode) != 0o600
    ):
        raise PermissionError(f"load-balancer {label} must be invoking-user-owned mode 0600")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(path, flags)
    try:
        opened = os.fstat(fd)
        if (opened.st_dev, opened.st_ino) != (info.st_dev, info.st_ino):
            raise RuntimeError("load-balancer snapshot changed while opening")
        with os.fdopen(os.dup(fd), "r", encoding="utf-8") as handle:
            payload = json.load(handle)
    finally:
        os.close(fd)
    if not isinstance(payload, dict):
        raise RuntimeError(f"load-balancer {label} is not a JSON object")
    return payload


def _read_snapshot(path: Path) -> dict[str, Any]:
    payload = _read_protected_json(path, "snapshot")
    if not isinstance(payload, dict) or payload.get("schema") != 1:
        raise RuntimeError("load-balancer snapshot schema is invalid")
    before = payload.get("before")
    if not isinstance(before, dict) or payload.get("before_sha256") != _digest(before):
        raise RuntimeError("load-balancer snapshot digest is invalid")
    if payload.get("desired_sha256") != _digest(desired_projection(before)):
        raise RuntimeError("load-balancer snapshot desired-state digest is invalid")
    return payload


def _attestation_payload(ready: dict[str, Any], before_sha256: str | None) -> dict[str, Any]:
    ready_sha256 = _digest(ready)
    health = ready.get("health_check")
    if not isinstance(health, dict) or health.get("path") != READY_HEALTH_PATH:
        raise RuntimeError("cannot attest a load balancer that is not using /api/ready")
    return {
        "schema": READY_ATTESTATION_SCHEMA,
        "load_balancer_id": LB_ID,
        "observed_at": _now(),
        "transaction_before_sha256": (
            _require_digest(before_sha256, "attestation before digest") if before_sha256 is not None else None
        ),
        "ready_mutable_sha256": ready_sha256,
        "ready_projection": ready,
        "health_check": {
            "protocol": health.get("protocol"),
            "port": health.get("port"),
            "path": health.get("path"),
            "check_interval_seconds": health.get("check_interval_seconds"),
            "response_timeout_seconds": health.get("response_timeout_seconds"),
            "healthy_threshold": health.get("healthy_threshold"),
            "unhealthy_threshold": health.get("unhealthy_threshold"),
        },
    }


def _validate_attestation(payload: dict[str, Any], ready_sha256: str) -> None:
    expected_keys = {
        "schema",
        "load_balancer_id",
        "observed_at",
        "transaction_before_sha256",
        "ready_mutable_sha256",
        "ready_projection",
        "health_check",
    }
    if (
        set(payload) != expected_keys
        or payload.get("schema") != READY_ATTESTATION_SCHEMA
        or payload.get("load_balancer_id") != LB_ID
    ):
        raise RuntimeError("ready attestation schema or load-balancer identity is invalid")
    observed_at = payload.get("observed_at")
    if not isinstance(observed_at, str) or _UTC_RE.fullmatch(observed_at) is None:
        raise RuntimeError("ready attestation observation time is invalid")
    try:
        datetime.fromisoformat(observed_at[:-1] + "+00:00")
    except ValueError as exc:
        raise RuntimeError("ready attestation observation time is invalid") from exc
    if payload.get("ready_mutable_sha256") != ready_sha256:
        raise RuntimeError("ready attestation names a different projection digest")
    ready = payload.get("ready_projection")
    if not isinstance(ready, dict) or _digest(ready) != ready_sha256:
        raise RuntimeError("ready attestation projection digest is invalid")
    validate_ready_projection_keyset(ready)
    validate_ready_projection_values(ready)
    health = ready.get("health_check")
    if not isinstance(health, dict) or payload.get("health_check") != {
        "protocol": health.get("protocol"),
        "port": health.get("port"),
        "path": health.get("path"),
        "check_interval_seconds": health.get("check_interval_seconds"),
        "response_timeout_seconds": health.get("response_timeout_seconds"),
        "healthy_threshold": health.get("healthy_threshold"),
        "unhealthy_threshold": health.get("unhealthy_threshold"),
    }:
        raise RuntimeError("ready attestation health-check projection is invalid")
    observed = {
        **ready,
        "id": LB_ID,
        "ip": LB_IP,
        "status": "active",
        "algorithm": "round_robin",
        "size": "lb-small",
        "size_unit": ready.get("size_unit"),
        "tag": "",
        "region": {"slug": ready.get("region")},
        "health_check": dict(_contract.LB_HEALTH_CONTRACT_OLD),
    }
    observed_projection = validate_observed_identity(observed)
    ready_before = dict(ready)
    ready_before["health_check"] = dict(_contract.LB_HEALTH_CONTRACT_OLD)
    if observed_projection != ready_before:
        raise RuntimeError("ready attestation is not the exact authorized mutable projection")
    if health.get("path") != READY_HEALTH_PATH:
        raise RuntimeError("ready attestation does not prove /api/ready")
    transaction_before = payload.get("transaction_before_sha256")
    if transaction_before is not None:
        _require_digest(transaction_before, "attestation before digest")


def _write_attestation(state_root: Path, ready: dict[str, Any], before_sha256: str | None) -> Path:
    payload = _attestation_payload(ready, before_sha256)
    ready_sha256 = str(payload["ready_mutable_sha256"])
    path = attestation_path_for(ready_sha256, state_root)
    if path.exists() or path.is_symlink():
        current = _read_protected_json(path, "ready attestation")
        _validate_attestation(current, ready_sha256)
        _replace_protected_json(path, payload)
    else:
        _write_protected_json(path, payload)
    _validate_attestation(_read_protected_json(path, "ready attestation"), ready_sha256)
    return path


def _failover_attestation_payload(
    ready: dict[str, Any],
    transaction_id: str,
    manifest_sha256: str,
    phase: str,
    observation: str,
) -> dict[str, Any]:
    if phase not in FAILOVER_PHASES:
        raise ValueError("failover attestation phase is invalid")
    if observation not in FAILOVER_OBSERVATIONS:
        raise ValueError("failover attestation observation is invalid")
    ready_sha256 = _digest(ready)
    return {
        "schema": FAILOVER_ATTESTATION_SCHEMA,
        "load_balancer_id": LB_ID,
        "failover_transaction_id": transaction_id,
        "manifest_sha256": _require_digest(manifest_sha256, "failover manifest digest"),
        "phase": phase,
        "observation": observation,
        "observed_at": _now(),
        "ready_mutable_sha256": ready_sha256,
        "ready_attestation": _attestation_payload(ready, None),
    }


def _validate_failover_attestation(
    payload: dict[str, Any],
    *,
    transaction_id: str,
    manifest_sha256: str,
    ready_sha256: str,
    phase: str,
    observation: str,
) -> None:
    if phase not in FAILOVER_PHASES:
        raise ValueError("failover attestation phase is invalid")
    if observation not in FAILOVER_OBSERVATIONS:
        raise ValueError("failover attestation observation is invalid")
    if set(payload) != {
        "schema",
        "load_balancer_id",
        "failover_transaction_id",
        "manifest_sha256",
        "phase",
        "observation",
        "observed_at",
        "ready_mutable_sha256",
        "ready_attestation",
    }:
        raise RuntimeError("failover LB attestation fields are invalid")
    if (
        payload.get("schema") != FAILOVER_ATTESTATION_SCHEMA
        or payload.get("load_balancer_id") != LB_ID
        or payload.get("failover_transaction_id") != transaction_id
        or payload.get("manifest_sha256") != _require_digest(manifest_sha256, "failover manifest digest")
        or payload.get("phase") != phase
        or payload.get("observation") != observation
        or payload.get("ready_mutable_sha256") != _require_digest(ready_sha256, "ready projection digest")
    ):
        raise RuntimeError("failover LB attestation binding is invalid")
    observed_at = payload.get("observed_at")
    if not isinstance(observed_at, str) or _UTC_RE.fullmatch(observed_at) is None:
        raise RuntimeError("failover LB attestation observation time is invalid")
    try:
        datetime.fromisoformat(observed_at[:-1] + "+00:00")
    except ValueError as exc:
        raise RuntimeError("failover LB attestation observation time is invalid") from exc
    base = payload.get("ready_attestation")
    if not isinstance(base, dict):
        raise RuntimeError("failover LB attestation has no exact ready projection")
    _validate_attestation(base, ready_sha256)


def _write_failover_attestation(
    state_root: Path,
    ready: dict[str, Any],
    transaction_id: str,
    manifest_sha256: str,
    phase: str,
    observation: str,
) -> Path:
    payload = _failover_attestation_payload(ready, transaction_id, manifest_sha256, phase, observation)
    ready_sha256 = str(payload["ready_mutable_sha256"])
    path = failover_attestation_path_for(transaction_id, manifest_sha256, phase, observation, state_root)
    if path.exists() or path.is_symlink():
        current = _read_protected_json(path, "failover ready attestation")
        _validate_failover_attestation(
            current,
            transaction_id=transaction_id,
            manifest_sha256=manifest_sha256,
            ready_sha256=ready_sha256,
            phase=phase,
            observation=observation,
        )
        _replace_protected_json(path, payload)
    else:
        _write_protected_json(path, payload)
    return path


def _wait_projection(expected: dict[str, Any], *, attempts: int = 12) -> bool:
    expected_digest = _digest(expected)
    for _ in range(attempts):
        current = validate_observed_identity(_get_load_balancer())
        if _digest(current) == expected_digest:
            return True
        time.sleep(5)
    return False


def _rollback_failed_apply(before: dict[str, Any], desired: dict[str, Any]) -> bool:
    """Restore only from a state this exact transaction could have produced."""

    try:
        current = validate_observed_identity(_get_load_balancer())
        current_sha256 = _digest(current)
        if current_sha256 == _digest(before):
            return True
        if current_sha256 != _digest(desired):
            return False
        # The API has no conditional PUT/ETag. Recheck immediately and require
        # the exclusive owner window through the request so automatic rollback
        # never knowingly overwrites a provider mutation between observations.
        rollback_from = validate_observed_identity(_get_load_balancer())
        if _digest(rollback_from) != current_sha256:
            return False
        _request("PUT", payload=before)
        return _wait_projection(before)
    except Exception:
        return False


def _plan(args: argparse.Namespace) -> int:
    state_root = _state_root(args.state_dir)
    _ensure_state_root(state_root)
    before = validate_observed_identity(_get_load_balancer())
    validate_mutable_projection_routing_values(before)
    path = str(before["health_check"].get("path") or "")
    if path not in {OLD_HEALTH_PATH, READY_HEALTH_PATH}:
        raise RuntimeError("DigitalOcean health path differs from both authorized states")
    before_sha256 = _digest(before)
    desired = desired_projection(before)
    validate_ready_projection_values(desired)
    desired_sha256 = _digest(desired)
    health = before["health_check"]
    minimum_drain = int(health["check_interval_seconds"]) * int(health["unhealthy_threshold"]) + 10
    print(f"load_balancer_id={LB_ID}")
    print(f"current_health_path={path}")
    print(f"current_mutable_sha256={before_sha256}")
    print(f"ready_mutable_sha256={desired_sha256}")
    print(f"minimum_drain_seconds={minimum_drain}")
    if path == READY_HEALTH_PATH:
        print("OK: DigitalOcean already uses the exact /api/ready direct health check")
        print(f"DRY-RUN: confirmation={attest_confirmation(before_sha256)}")
        print(f"DRY-RUN: attestation={attestation_path_for(before_sha256, state_root)}")
    else:
        print(f"DRY-RUN: confirmation={apply_confirmation(before_sha256)}")
        print(f"DRY-RUN: snapshot={snapshot_path_for(before_sha256, state_root)}")
        print(f"DRY-RUN: attestation={attestation_path_for(desired_sha256, state_root)}")
    return 0


def _apply(args: argparse.Namespace) -> int:
    state_root = _state_root(args.state_dir)
    _ensure_state_root(state_root)
    before = validate_observed_identity(_get_load_balancer())
    validate_mutable_projection_routing_values(before)
    before_sha256 = _digest(before)
    if before_sha256 != _require_digest(args.expected_before_sha256, "expected before digest"):
        raise RuntimeError("DigitalOcean load balancer changed after owner dry-run")
    path = str(before["health_check"].get("path") or "")
    if path == READY_HEALTH_PATH:
        raise RuntimeError("DigitalOcean is already ready; use the exact attest operation")
    if path != OLD_HEALTH_PATH:
        raise RuntimeError("DigitalOcean health path is not the authorized old value")
    if args.confirm != apply_confirmation(before_sha256):
        raise PermissionError("exact DigitalOcean change confirmation is missing")
    snapshot_path = Path(os.path.abspath(os.fspath(args.snapshot)))
    if snapshot_path != snapshot_path_for(before_sha256, state_root):
        raise PermissionError("snapshot path is not the exact digest-bound canonical path")
    desired = desired_projection(before)
    validate_ready_projection_values(desired)
    _write_protected_json(
        snapshot_path,
        {
            "schema": 1,
            "load_balancer_id": LB_ID,
            "before_sha256": before_sha256,
            "desired_sha256": _digest(desired),
            "before": before,
        },
    )
    # Re-read immediately before the full-representation update (CAS).
    if _digest(validate_observed_identity(_get_load_balancer())) != before_sha256:
        raise RuntimeError("DigitalOcean load balancer changed before update")
    try:
        _request("PUT", payload=desired)
        if not _wait_projection(desired):
            raise RuntimeError("DigitalOcean readiness update read-back did not converge")
        attestation_path = _write_attestation(state_root, desired, before_sha256)
    except Exception:
        # CAS-guard rollback too: never overwrite an unrelated concurrent
        # owner change while trying to restore this transaction's snapshot.
        restored = _rollback_failed_apply(before, desired)
        if not restored:
            raise RuntimeError("DigitalOcean update failed and exact rollback is uncertain") from None
        raise RuntimeError("DigitalOcean update failed; exact prior projection was restored") from None
    artifact = _canonical(_read_protected_json(attestation_path, "ready attestation")) + b"\n"
    print(f"ready_mutable_sha256={_digest(desired)}")
    print(f"attestation_sha256={hashlib.sha256(artifact).hexdigest()}")
    print(f"observed_at={_read_protected_json(attestation_path, 'ready attestation')['observed_at']}")
    print(
        f"OK: DigitalOcean health path is {READY_HEALTH_PATH}; snapshot={snapshot_path}; attestation={attestation_path}"
    )
    return 0


def _attest(args: argparse.Namespace) -> int:
    state_root = _state_root(args.state_dir)
    _ensure_state_root(state_root)
    current = validate_observed_identity(_get_load_balancer())
    current_sha256 = _digest(current)
    if current_sha256 != _require_digest(args.expected_current_sha256, "expected current digest"):
        raise RuntimeError("DigitalOcean load balancer changed after owner dry-run")
    if current["health_check"].get("path") != READY_HEALTH_PATH:
        raise RuntimeError("DigitalOcean is not using the exact /api/ready health check")
    if args.confirm != attest_confirmation(current_sha256):
        raise PermissionError("exact DigitalOcean attestation confirmation is missing")
    # Bind the protected artifact to a second authenticated read. This refuses
    # a provider mutation in the confirmation-to-capture interval.
    observed = validate_observed_identity(_get_load_balancer())
    if _digest(observed) != current_sha256:
        raise RuntimeError("DigitalOcean load balancer changed during ready-state attestation")
    attestation_path = _write_attestation(state_root, observed, None)
    artifact = _canonical(_read_protected_json(attestation_path, "ready attestation")) + b"\n"
    print(f"ready_mutable_sha256={current_sha256}")
    print(f"attestation_sha256={hashlib.sha256(artifact).hexdigest()}")
    print(f"observed_at={_read_protected_json(attestation_path, 'ready attestation')['observed_at']}")
    print(f"OK: exact ready projection attested at {attestation_path}")
    return 0


def _plan_failover(args: argparse.Namespace) -> int:
    state_root = _state_root(args.state_dir)
    _ensure_state_root(state_root)
    manifest = _require_digest(args.manifest_sha256, "failover manifest digest")
    if _FAILOVER_TX_RE.fullmatch(args.transaction_id) is None:
        raise ValueError("failover transaction ID is invalid")
    current = validate_observed_identity(_get_load_balancer())
    digest = _digest(current)
    if current["health_check"].get("path") != READY_HEALTH_PATH:
        raise RuntimeError("DigitalOcean is not using the exact /api/ready health check")
    print(f"ready_mutable_sha256={digest}")
    print(
        "DRY-RUN: confirmation="
        f"{failover_attest_confirmation(digest, args.transaction_id, manifest, args.phase, args.observation)}"
    )
    print(
        "DRY-RUN: attestation="
        f"{failover_attestation_path_for(args.transaction_id, manifest, args.phase, args.observation, state_root)}"
    )
    return 0


def _attest_failover(args: argparse.Namespace) -> int:
    state_root = _state_root(args.state_dir)
    _ensure_state_root(state_root)
    expected = _require_digest(args.expected_current_sha256, "expected current digest")
    manifest = _require_digest(args.manifest_sha256, "failover manifest digest")
    if _FAILOVER_TX_RE.fullmatch(args.transaction_id) is None:
        raise ValueError("failover transaction ID is invalid")
    current = validate_observed_identity(_get_load_balancer())
    if _digest(current) != expected or current["health_check"].get("path") != READY_HEALTH_PATH:
        raise RuntimeError("DigitalOcean is not in the exact owner-authorized /api/ready state")
    confirmation = failover_attest_confirmation(expected, args.transaction_id, manifest, args.phase, args.observation)
    if args.confirm != confirmation:
        raise PermissionError("exact transaction-bound failover LB attestation confirmation is missing")
    # A second authenticated GET is the observation bound into the immutable
    # file. Refuse concurrent provider changes between validation and capture.
    observed = validate_observed_identity(_get_load_balancer())
    if _digest(observed) != expected:
        raise RuntimeError("DigitalOcean load balancer changed during failover observation")
    path = _write_failover_attestation(
        state_root, observed, args.transaction_id, manifest, args.phase, args.observation
    )
    print(f"ready_mutable_sha256={expected}")
    print(f"phase={args.phase}")
    print(f"observation={args.observation}")
    artifact = _canonical(_read_protected_json(path, "failover ready attestation")) + b"\n"
    print(f"attestation_sha256={hashlib.sha256(artifact).hexdigest()}")
    print(f"observed_at={_read_protected_json(path, 'failover ready attestation')['observed_at']}")
    print(f"OK: transaction-bound failover LB observation attested at {path}")
    return 0


def _restore(args: argparse.Namespace) -> int:
    state_root = _state_root(args.state_dir)
    _ensure_state_root(state_root)
    snapshot_path = Path(os.path.abspath(os.fspath(args.snapshot)))
    snapshot = _read_snapshot(snapshot_path)
    if snapshot.get("load_balancer_id") != LB_ID:
        raise RuntimeError("snapshot belongs to a different load balancer")
    before = snapshot["before"]
    before_sha256 = str(snapshot["before_sha256"])
    if snapshot_path != snapshot_path_for(before_sha256, state_root):
        raise PermissionError("snapshot path is not the exact digest-bound canonical path")
    current = validate_observed_identity(_get_load_balancer())
    current_sha256 = _digest(current)
    if current_sha256 != _require_digest(args.expected_current_sha256, "expected current digest"):
        raise RuntimeError("DigitalOcean load balancer changed before restore")
    if current_sha256 != snapshot.get("desired_sha256"):
        raise RuntimeError("current DigitalOcean state is not the exact desired state paired with this snapshot")
    if args.confirm != restore_confirmation(before_sha256):
        raise PermissionError("exact DigitalOcean restore confirmation is missing")
    # Re-read immediately before the full-representation restore. DigitalOcean
    # exposes no conditional ETag for this PUT, so the operator must also hold
    # the documented exclusive LB-owner window through the request; this second
    # authenticated GET closes mutations up to that final provider boundary.
    restored_from = validate_observed_identity(_get_load_balancer())
    if _digest(restored_from) != current_sha256:
        raise RuntimeError("DigitalOcean load balancer changed during restore confirmation")
    _request("PUT", payload=before)
    if not _wait_projection(before):
        raise RuntimeError("DigitalOcean exact snapshot restore is uncertain")
    attestation_path = attestation_path_for(current_sha256, state_root)
    if attestation_path.exists() or attestation_path.is_symlink():
        attestation = _read_protected_json(attestation_path, "ready attestation")
        _validate_attestation(attestation, current_sha256)
        attestation_path.unlink()
        directory_fd = os.open(state_root, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    print("OK: DigitalOcean exact pre-change projection was restored")
    return 0


def _operator_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--state-dir",
        type=Path,
        required=True,
        help="absolute invoking-user-owned local directory (created mode 0700 if absent)",
    )
    parser.add_argument(
        "--auth-source",
        choices=("doctl", "stdin"),
        default="doctl",
        help="use the selected local doctl context, or read one token from stdin",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    plan = commands.add_parser("plan", help="read-only identity/CAS plan")
    _operator_args(plan)
    apply = commands.add_parser("apply", help="apply exact /api/ready change")
    _operator_args(apply)
    apply.add_argument("--expected-before-sha256", required=True)
    apply.add_argument("--confirm", required=True)
    apply.add_argument("--snapshot", type=Path, required=True)
    attest = commands.add_parser("attest", help="attest an already-active exact /api/ready state")
    _operator_args(attest)
    attest.add_argument("--expected-current-sha256", required=True)
    attest.add_argument("--confirm", required=True)
    plan_failover = commands.add_parser(
        "plan-failover", help="read-only fresh /api/ready plan bound to one manifest/failover transaction"
    )
    _operator_args(plan_failover)
    plan_failover.add_argument("--transaction-id", required=True)
    plan_failover.add_argument("--manifest-sha256", required=True)
    plan_failover.add_argument("--phase", choices=FAILOVER_PHASES, required=True)
    plan_failover.add_argument("--observation", choices=FAILOVER_OBSERVATIONS, required=True)
    attest_failover = commands.add_parser(
        "attest-failover", help="freshly attest /api/ready for one exact manifest/failover transaction"
    )
    _operator_args(attest_failover)
    attest_failover.add_argument("--expected-current-sha256", required=True)
    attest_failover.add_argument("--transaction-id", required=True)
    attest_failover.add_argument("--manifest-sha256", required=True)
    attest_failover.add_argument("--phase", choices=FAILOVER_PHASES, required=True)
    attest_failover.add_argument("--observation", choices=FAILOVER_OBSERVATIONS, required=True)
    attest_failover.add_argument("--confirm", required=True)
    restore = commands.add_parser("restore", help="restore an exact protected snapshot")
    _operator_args(restore)
    restore.add_argument("--snapshot", type=Path, required=True)
    restore.add_argument("--expected-current-sha256", required=True)
    restore.add_argument("--confirm", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    global _API_TOKEN
    args = build_parser().parse_args(argv)
    try:
        _configure_auth(args.auth_source)
        if args.command == "plan":
            return _plan(args)
        if args.command == "apply":
            return _apply(args)
        if args.command == "attest":
            return _attest(args)
        if args.command == "plan-failover":
            return _plan_failover(args)
        if args.command == "attest-failover":
            return _attest_failover(args)
        if args.command == "restore":
            return _restore(args)
        raise AssertionError("unreachable")
    except Exception as exc:  # noqa: BLE001 - provider bodies and tokens are never printed
        print(f"ERROR: DigitalOcean health-check transaction failed ({type(exc).__name__}): {exc}", file=sys.stderr)
        return 2
    finally:
        # Python strings cannot be reliably zeroized, but release every retained
        # reference immediately and never persist the credential.
        _API_TOKEN = None


if __name__ == "__main__":
    raise SystemExit(main())
