"""Focused contracts for the explicit one-time Meta HA bootstrap tools."""

from __future__ import annotations

import copy
import importlib.util
import io
import json
import os
import stat
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
BOOTSTRAP_PATH = ROOT / "scripts" / "ha" / "bootstrap_meta_ha_contract.py"
LB_PATH = ROOT / "scripts" / "ha" / "manage_do_lb_ready_healthcheck.py"
CONTRACT_PATH = ROOT / "scripts" / "ha" / "do_lb_ready_contract.py"


def _load(path: Path, name: str):  # type: ignore[no-untyped-def]
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


bootstrap = _load(BOOTSTRAP_PATH, "bootstrap_meta_ha_contract_test")
lb = _load(LB_PATH, "manage_do_lb_ready_healthcheck_test")
contract = _load(CONTRACT_PATH, "do_lb_ready_contract_test")


def _observed_lb() -> dict[str, object]:
    return {
        "algorithm": "round_robin",
        "created_at": "2026-08-01T00:00:00Z",
        "disable_lets_encrypt_dns_records": False,
        "droplet_ids": [591901417, 510629908],
        "enable_backend_keepalive": True,
        "enable_proxy_protocol": False,
        "forwarding_rules": [
            {"entry_protocol": "http", "entry_port": 80, "target_protocol": "http", "target_port": 80},
            {
                "entry_protocol": "https",
                "entry_port": 443,
                "target_protocol": "http",
                "target_port": 80,
                "certificate_id": "ccd5-observed",
            },
        ],
        "health_check": {
            "protocol": "http",
            "port": 8003,
            "path": "/api/health",
            "check_interval_seconds": 5,
            "response_timeout_seconds": 3,
            "healthy_threshold": 2,
            "unhealthy_threshold": 3,
        },
        "http_idle_timeout_seconds": 60,
        "id": lb.LB_ID,
        "ip": lb.LB_IP,
        "ipv6": "",
        "name": lb.LB_NAME,
        "network_stack": "DUALSTACK",
        "project_id": "70160077-6e21-4fc7-9c81-45e6b60d8919",
        "redirect_http_to_https": True,
        "region": {"slug": "lon1", "name": "London 1"},
        "size": "lb-small",
        "size_unit": 1,
        "status": "active",
        "sticky_sessions": {"type": "none"},
        "subnet_uuid": "2415d1ce-b8e6-4707-bc89-56e234548d60",
        "tag": "",
        "type": "REGIONAL",
        "vpc_uuid": "d0e11d67-3fba-4966-b2db-6a471307df85",
    }


def _provider_observed_lb() -> dict[str, object]:
    observed = copy.deepcopy(_observed_lb())
    rules = observed["forwarding_rules"]
    assert isinstance(rules, list)
    for rule in rules:
        assert isinstance(rule, dict)
        rule["tls_passthrough"] = False
        if rule["entry_protocol"] == "http":
            rule["certificate_id"] = ""
    return observed


def _ready_projection() -> dict[str, object]:
    observed = _observed_lb()
    observed["health_check"] = {**observed["health_check"], "path": "/api/ready"}  # type: ignore[index]
    return lb.validate_observed_identity(observed)


def _bootstrap_lb_authority_and_evidence(
    *,
    target_sha: str = "c" * 40,
    attestation_sha256: str = "9" * 64,
    observed_at: str = "2026-08-16T00:00:00Z",
) -> tuple[dict[str, object], dict[str, object]]:
    ready = _ready_projection()
    ready_sha256 = bootstrap._digest(ready)
    authority: dict[str, object] = {
        "schema": bootstrap.LB_PLAN_AUTHORITY_SCHEMA,
        "load_balancer_id": bootstrap.LB_ID,
        "load_balancer_name": bootstrap.LB_NAME,
        "load_balancer_ip": bootstrap.LB_IP,
        "project_id": bootstrap.LB_PROJECT_ID,
        "droplet_ids": bootstrap.LB_DROPLETS,
        "ready_mutable_sha256": ready_sha256,
        "ready_projection": ready,
        "health_check": bootstrap.LB_HEALTH_CONTRACT,
        "minimum_drain_seconds": 25,
    }
    evidence: dict[str, object] = {
        "schema": bootstrap.LB_APPLY_EVIDENCE_SCHEMA,
        "target_sha": target_sha,
        "authority_sha256": bootstrap._digest(authority),
        "attestation_sha256": attestation_sha256,
        "load_balancer_id": bootstrap.LB_ID,
        "ready_mutable_sha256": ready_sha256,
        "observed_at": observed_at,
        "transaction_before_sha256": None,
    }
    return authority, evidence


def _patch_bootstrap_plan_context(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    payload: dict[str, object],
    *,
    target_sha: str = "a" * 40,
    expected_ready_sha256: str | None = None,
) -> tuple[SimpleNamespace, Path, bytes]:
    raw = bootstrap._canonical(payload) + b"\n"
    state_root = tmp_path / "meta-ha"
    state_root.mkdir(exist_ok=True)
    path = state_root / "lb-ready-bootstrap-attestation.json"
    path.write_bytes(raw)
    monkeypatch.setattr(bootstrap, "STATE_ROOT", state_root)
    monkeypatch.setattr(bootstrap, "LB_BOOTSTRAP_ATTESTATION_PATH", path)
    monkeypatch.setattr(bootstrap, "_secure_dir", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(bootstrap, "_secure_regular", lambda *_args, **_kwargs: path.stat())
    shared = {"qg_target_sha": target_sha, "plan_sha256": "1" * 64}

    def probe(node_id: str, expected_sha: str) -> dict[str, object]:
        return {
            "previous_sha": expected_sha,
            "runtime_authority": {"shared": shared},
            "live_units": {"api": "same"},
            "pg": {"state_sha256": "d" * 64},
            "nested_runtime": {"portable_content": "same"},
            "node_id": node_id,
        }

    monkeypatch.setattr(bootstrap, "_helper_source", lambda: (b"helper", "2" * 64))
    monkeypatch.setattr(bootstrap, "_node_probe", probe)
    monkeypatch.setattr(
        bootstrap,
        "_remote",
        lambda *_args: json.dumps(probe("node02", "c" * 40), separators=(",", ":")),
    )
    monkeypatch.setattr(
        bootstrap._nested_evidence,
        "portable_content_identity",
        lambda value: value["portable_content"],
    )
    ready_sha256 = expected_ready_sha256 or str(payload["ready_mutable_sha256"])
    args = SimpleNamespace(
        target_sha=target_sha,
        expected_node01_sha="b" * 40,
        expected_node02_sha="c" * 40,
        expected_pg_state_sha256="d" * 64,
        expected_lb_ready_sha256=ready_sha256,
        expected_lb_attestation_sha256=bootstrap._digest_bytes(raw),
        lb_ready_attestation=path,
        expected_plan_sha256="0" * 64,
        confirm="",
    )
    return args, path, raw


def test_do_lb_update_is_full_projection_cas_and_changes_only_health_path() -> None:
    observed = _observed_lb()
    before = lb.validate_observed_identity(observed)
    desired = lb.desired_projection(before)

    assert before["region"] == "lon1"
    assert "id" not in before and "ip" not in before
    assert "network" not in before
    assert before["network_stack"] == "DUALSTACK"
    assert before["type"] == "REGIONAL"
    assert before["size_unit"] == 1
    assert before["enable_proxy_protocol"] is False
    assert before["subnet_uuid"] == contract.LB_SUBNET_UUID
    assert before["vpc_uuid"] == contract.LB_VPC_UUID
    assert "size" not in before
    assert "tag" not in before
    assert before["droplet_ids"] == [510629908, 591901417]
    assert desired["health_check"]["path"] == "/api/ready"
    before_without_health = {key: value for key, value in before.items() if key != "health_check"}
    desired_without_health = {key: value for key, value in desired.items() if key != "health_check"}
    assert desired_without_health == before_without_health
    old_health = dict(before["health_check"])
    new_health = dict(desired["health_check"])
    assert {**new_health, "path": old_health["path"]} == old_health


def test_do_lb_current_provider_get_shape_normalizes_to_the_existing_canonical_digest() -> None:
    canonical = lb.validate_observed_identity(_observed_lb())
    provider = lb.validate_observed_identity(_provider_observed_lb())
    reordered = _provider_observed_lb()
    reordered_rules = reordered["forwarding_rules"]
    assert isinstance(reordered_rules, list)
    reordered["forwarding_rules"] = list(reversed(reordered_rules))

    assert provider == canonical
    assert lb.validate_observed_identity(reordered) == canonical
    assert lb._digest(provider) == lb._digest(canonical)
    assert provider["forwarding_rules"] == [
        {
            "entry_protocol": "http",
            "entry_port": 80,
            "target_protocol": "http",
            "target_port": 80,
        },
        {
            "entry_protocol": "https",
            "entry_port": 443,
            "target_protocol": "http",
            "target_port": 80,
            "certificate_id": "ccd5-observed",
        },
    ]


@pytest.mark.parametrize(
    "mutator",
    [
        lambda rules: rules[0].update({"unknown": True}),
        lambda rules: rules[0].update({"tls_passthrough": True}),
        lambda rules: rules[1].update({"tls_passthrough": True}),
        lambda rules: rules[0].update({"certificate_id": "unexpected"}),
        lambda rules: rules[1].update({"certificate_id": ""}),
        lambda rules: rules[1].pop("certificate_id"),
        lambda rules: rules[0].update({"entry_port": True}),
        lambda rules: rules[1].update({"target_port": "80"}),
    ],
)
def test_do_lb_provider_get_shape_rejects_unknown_or_unsafe_defaults(mutator: object) -> None:
    observed = _provider_observed_lb()
    rules = observed["forwarding_rules"]
    assert isinstance(rules, list)
    mutator(rules)  # type: ignore[operator]

    with pytest.raises(RuntimeError, match="DigitalOcean (?:observed|ready projection)"):
        lb.validate_observed_identity(observed)


def test_do_lb_provider_defaults_are_get_only_not_part_of_ready_attestation_projection() -> None:
    ready = _ready_projection_from_observed()
    rules = ready["forwarding_rules"]
    assert isinstance(rules, list)
    for rule in rules:
        assert isinstance(rule, dict)
        rule["tls_passthrough"] = False
        rule.setdefault("certificate_id", "")

    with pytest.raises(RuntimeError, match="forwarding rules"):
        contract.validate_ready_projection_values(ready)


def test_do_lb_current_provider_shape_works_for_plan_readback_and_attestation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider_old = _provider_observed_lb()
    canonical_old = lb.validate_observed_identity(_observed_lb())
    canonical_ready = lb.desired_projection(canonical_old)
    provider_ready = _provider_observed_lb()
    provider_ready["health_check"] = dict(contract.LB_HEALTH_CONTRACT_READY)
    state_root = tmp_path / "operator-state"

    monkeypatch.setattr(lb, "_get_load_balancer", lambda: provider_old)
    assert lb._plan(SimpleNamespace(state_dir=state_root)) == 0

    monkeypatch.setattr(lb, "_get_load_balancer", lambda: provider_ready)
    assert lb._wait_projection(canonical_ready, attempts=1) is True

    ready_sha = lb._digest(canonical_ready)
    args = SimpleNamespace(
        state_dir=state_root,
        expected_current_sha256=ready_sha,
        confirm=lb.attest_confirmation(ready_sha),
    )
    assert lb._attest(args) == 0
    path = lb.attestation_path_for(ready_sha, state_root)
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["ready_projection"] == canonical_ready
    lb._validate_attestation(payload, ready_sha)


def test_do_lb_apply_rejects_unsafe_provider_defaults_before_any_put(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observed = _provider_observed_lb()
    rules = observed["forwarding_rules"]
    assert isinstance(rules, list) and isinstance(rules[1], dict)
    rules[1]["tls_passthrough"] = True
    requests: list[tuple[str, object]] = []
    monkeypatch.setattr(lb, "_get_load_balancer", lambda: observed)

    def request(method: str, *, payload: object = None) -> dict[str, object]:
        requests.append((method, payload))
        return {}

    monkeypatch.setattr(lb, "_request", request)
    args = SimpleNamespace(
        state_dir=tmp_path / "operator-state",
        expected_before_sha256="0" * 64,
        snapshot=tmp_path / "never-used.json",
        confirm="never-used",
    )

    with pytest.raises(RuntimeError, match="TLS passthrough"):
        lb._apply(args)
    assert requests == []


def test_do_lb_immutable_network_shape_is_validated_and_preserved_in_full_put() -> None:
    observed = _observed_lb()
    projection = lb.validate_observed_identity(observed)
    assert "network" not in observed
    assert observed["network_stack"] == "DUALSTACK"
    assert "network" not in projection
    assert projection["network_stack"] == "DUALSTACK"
    assert projection["type"] == "REGIONAL"

    observed["network"] = "EXTERNAL"
    with pytest.raises(RuntimeError, match="forbidden"):
        lb.validate_observed_identity(observed)

    observed = _observed_lb()
    observed["network_stack"] = "IPV4"
    with pytest.raises(RuntimeError, match="routing/safety contract"):
        lb.validate_observed_identity(observed)

    observed = _observed_lb()
    observed["size_unit"] = 2
    with pytest.raises(RuntimeError, match="routing/safety contract"):
        lb.validate_observed_identity(observed)


def test_do_lb_full_put_keeps_modern_capacity_and_omits_empty_tag() -> None:
    observed = _observed_lb()
    assert observed["size"] == "lb-small"
    assert observed["size_unit"] == 1
    assert observed["tag"] == ""
    projection = lb.validate_observed_identity(observed)
    assert projection["size_unit"] == 1
    assert "size" not in projection
    assert "tag" not in projection
    assert projection["droplet_ids"] == [510629908, 591901417]

    observed["tag"] = "meta-backends"
    with pytest.raises(RuntimeError, match="tag conflicts"):
        lb.validate_observed_identity(observed)

    observed = _observed_lb()
    observed["network_stack"] = "IPV4"
    with pytest.raises(RuntimeError, match="routing/safety contract"):
        lb.validate_observed_identity(observed)


def _ready_projection_from_observed() -> dict[str, object]:
    return lb.desired_projection(lb.validate_observed_identity(_observed_lb()))


def test_do_lb_projection_keysets_match_across_all_consumers() -> None:
    assert lb.LB_READY_PROJECTION_KEYS == contract.LB_READY_PROJECTION_KEYS
    assert bootstrap.LB_READY_PROJECTION_KEYS == contract.LB_READY_PROJECTION_KEYS


def test_do_lb_ready_projection_digest_matches_across_consumers() -> None:
    ready = _ready_projection_from_observed()
    digest = lb._digest(ready)
    contract.validate_ready_projection_values(ready)
    bootstrap._validate_lb_ready_projection(ready, digest)
    assert digest == lb._digest(ready)


@pytest.mark.parametrize(
    ("mutator", "pattern"),
    [
        (lambda projection: projection.pop("subnet_uuid"), "incomplete or unknown"),
        (lambda projection: projection.update({"network": "EXTERNAL"}), "forbidden network"),
        (lambda projection: projection.update({"network": None}), "forbidden network"),
        (lambda projection: projection.update({"firewall": None}), "incomplete or unknown"),
        (lambda projection: projection.update({"http_idle_timeout_seconds": 61}), "idle timeout"),
        (
            lambda projection: projection["forwarding_rules"][0].update({"extra": True}),
            "forwarding rules",
        ),
        (lambda projection: projection.update({"network_stack": "IPV4"}), "routing identity"),
        (lambda projection: projection.update({"size_unit": 2}), "routing identity"),
        (lambda projection: projection.update({"enable_proxy_protocol": True}), "routing identity"),
        (
            lambda projection: projection.update({"subnet_uuid": "00000000-0000-0000-0000-000000000000"}),
            "routing identity",
        ),
        (
            lambda projection: projection.update({"vpc_uuid": "00000000-0000-0000-0000-000000000000"}),
            "routing identity",
        ),
        (lambda projection: projection.update({"extra_field": True}), "incomplete or unknown"),
    ],
)
def test_do_lb_ready_projection_rejects_mutated_shapes_without_put(mutator: object, pattern: str) -> None:
    ready = _ready_projection_from_observed()
    mutator(ready)  # type: ignore[operator]
    with pytest.raises(RuntimeError, match=pattern):
        contract.validate_ready_projection_values(ready)


def test_do_lb_plan_and_apply_validate_ready_projection_before_any_put(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state_root = tmp_path / "lb-owner-state"
    lb._ensure_state_root(state_root)
    before = lb.validate_observed_identity(_observed_lb())
    desired = lb.desired_projection(before)
    contract.validate_mutable_projection_routing_values(before)
    contract.validate_ready_projection_values(desired)
    requests: list[tuple[str, object]] = []
    monkeypatch.setattr(lb, "_get_load_balancer", lambda: _observed_lb())
    monkeypatch.setattr(
        lb,
        "_request",
        lambda method, *, payload=None: requests.append((method, payload)) or {},
    )
    invalid = dict(desired)
    invalid["subnet_uuid"] = "00000000-0000-0000-0000-000000000000"
    monkeypatch.setattr(lb, "desired_projection", lambda _before: invalid)
    before_sha = lb._digest(before)
    args = SimpleNamespace(
        state_dir=state_root,
        expected_before_sha256=before_sha,
        snapshot=lb.snapshot_path_for(before_sha, state_root),
        confirm=lb.apply_confirmation(before_sha),
    )
    with pytest.raises(RuntimeError, match="routing identity"):
        lb._apply(args)
    assert requests == []


@pytest.mark.parametrize(
    ("mutator", "pattern"),
    [
        (lambda projection: projection.update({"network": "EXTERNAL"}), "forbidden network"),
        (lambda projection: projection.update({"network": None}), "forbidden network"),
        (lambda projection: projection.update({"firewall": None}), "incomplete or unknown"),
        (lambda projection: projection.update({"http_idle_timeout_seconds": 61}), "idle timeout"),
        (
            lambda projection: projection["forwarding_rules"][0].update({"extra": True}),
            "forwarding rules",
        ),
        (lambda projection: projection.update({"network_stack": "IPV4"}), "routing identity"),
        (lambda projection: projection.update({"size_unit": 2}), "routing identity"),
        (lambda projection: projection.update({"enable_proxy_protocol": True}), "routing identity"),
        (
            lambda projection: projection.update({"subnet_uuid": "00000000-0000-0000-0000-000000000000"}),
            "routing identity",
        ),
        (lambda projection: projection.update({"extra_field": True}), "incomplete or unknown"),
    ],
)
def test_do_lb_apply_issues_zero_puts_for_invalid_ready_projection(
    mutator: object,
    pattern: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state_root = tmp_path / "lb-owner-state"
    lb._ensure_state_root(state_root)
    before = lb.validate_observed_identity(_observed_lb())
    desired = lb.desired_projection(before)
    mutator(desired)  # type: ignore[operator]
    requests: list[tuple[str, object]] = []
    monkeypatch.setattr(lb, "_get_load_balancer", lambda: _observed_lb())
    monkeypatch.setattr(
        lb,
        "_request",
        lambda method, *, payload=None: requests.append((method, payload)) or {},
    )
    monkeypatch.setattr(lb, "desired_projection", lambda _before: desired)
    before_sha = lb._digest(before)
    args = SimpleNamespace(
        state_dir=state_root,
        expected_before_sha256=before_sha,
        snapshot=lb.snapshot_path_for(before_sha, state_root),
        confirm=lb.apply_confirmation(before_sha),
    )
    with pytest.raises(RuntimeError, match=pattern):
        lb._apply(args)
    assert requests == []


def test_do_lb_apply_and_restore_round_trip_preserves_full_representation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    state_root = tmp_path / "lb-owner-state"
    lb._ensure_state_root(state_root)
    before = lb.validate_observed_identity(_observed_lb())
    desired = lb.desired_projection(before)
    before_sha = lb._digest(before)
    desired_sha = lb._digest(desired)
    requests: list[tuple[str, object]] = []
    observations = iter(
        (
            _observed_lb(),
            _observed_lb(),
            dict(_observed_lb(), health_check=dict(contract.LB_HEALTH_CONTRACT_READY)),
            dict(_observed_lb(), health_check=dict(contract.LB_HEALTH_CONTRACT_READY)),
        )
    )
    monkeypatch.setattr(lb, "_get_load_balancer", lambda: next(observations))
    monkeypatch.setattr(
        lb,
        "_request",
        lambda method, *, payload=None: requests.append((method, payload)) and {},
    )
    monkeypatch.setattr(lb, "_wait_projection", lambda expected, **kwargs: True)
    apply_args = SimpleNamespace(
        state_dir=state_root,
        expected_before_sha256=before_sha,
        snapshot=lb.snapshot_path_for(before_sha, state_root),
        confirm=lb.apply_confirmation(before_sha),
    )
    lb._apply(apply_args)
    assert requests[0] == ("PUT", desired)
    restore_args = SimpleNamespace(
        state_dir=state_root,
        snapshot=lb.snapshot_path_for(before_sha, state_root),
        expected_current_sha256=desired_sha,
        confirm=lb.restore_confirmation(before_sha),
    )
    lb._restore(restore_args)
    assert requests[-1] == ("PUT", before)


def test_do_lb_update_refuses_unknown_fields_and_has_exact_restore_token() -> None:
    observed = _observed_lb()
    observed["new_mutable_field"] = True
    with pytest.raises(RuntimeError, match="unhandled fields"):
        lb.update_projection(observed)

    digest = "a" * 64
    assert lb.apply_confirmation(digest) == "CHANGE_DO_LB_READY_AAAAAAAAAAAAAAAA"
    assert lb.restore_confirmation(digest) == "RESTORE_DO_LB_AAAAAAAAAAAAAAAA"
    assert lb.attest_confirmation(digest) == "ATTEST_DO_LB_READY_AAAAAAAAAAAAAAAA"


def test_do_lb_failed_apply_rollback_is_itself_cas_guarded(monkeypatch: pytest.MonkeyPatch) -> None:
    before = lb.validate_observed_identity(_observed_lb())
    desired = lb.desired_projection(before)
    unrelated_observed = _observed_lb()
    unrelated_health = dict(unrelated_observed["health_check"])
    unrelated_health["path"] = "/api/ready"
    unrelated_observed["health_check"] = unrelated_health
    unrelated_observed["http_idle_timeout_seconds"] = 61
    requests: list[tuple[str, object]] = []

    monkeypatch.setattr(lb, "_get_load_balancer", lambda: unrelated_observed)
    monkeypatch.setattr(
        lb,
        "_request",
        lambda method, *, payload=None: requests.append((method, payload)),
    )

    assert lb._rollback_failed_apply(before, desired) is False
    assert requests == []

    desired_observed = _observed_lb()
    desired_observed["health_check"] = {  # type: ignore[index]
        **desired_observed["health_check"],  # type: ignore[index]
        "path": "/api/ready",
    }
    changed_after_first_get = dict(desired_observed)
    changed_after_first_get["http_idle_timeout_seconds"] = 61
    observations = iter((desired_observed, changed_after_first_get))
    monkeypatch.setattr(lb, "_get_load_balancer", lambda: next(observations))
    assert lb._rollback_failed_apply(before, desired) is False
    assert requests == []


def test_do_lb_restore_uses_a_second_authenticated_get_before_zero_put(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    state_root = tmp_path / "lb-owner-state"
    lb._ensure_state_root(state_root)
    before = lb.validate_observed_identity(_observed_lb())
    desired = lb.desired_projection(before)
    before_sha = lb._digest(before)
    desired_sha = lb._digest(desired)
    snapshot_path = lb.snapshot_path_for(before_sha, state_root)
    lb._write_protected_json(
        snapshot_path,
        {
            "schema": 1,
            "load_balancer_id": lb.LB_ID,
            "before_sha256": before_sha,
            "desired_sha256": desired_sha,
            "before": before,
        },
    )
    first = _observed_lb()
    first["health_check"] = {**first["health_check"], "path": "/api/ready"}  # type: ignore[index]
    changed = dict(first)
    changed["http_idle_timeout_seconds"] = 61
    observations = iter((first, changed))
    requests: list[tuple[str, object]] = []
    monkeypatch.setattr(lb, "_get_load_balancer", lambda: next(observations))
    monkeypatch.setattr(
        lb,
        "_request",
        lambda method, *, payload=None: requests.append((method, payload)),
    )
    args = SimpleNamespace(
        state_dir=state_root,
        snapshot=snapshot_path,
        expected_current_sha256=desired_sha,
        confirm=lb.restore_confirmation(before_sha),
    )
    with pytest.raises(RuntimeError, match="routing/safety contract changed"):
        lb._restore(args)
    assert requests == []


def test_do_lb_operator_state_and_attestation_are_local_and_exact(tmp_path: Path) -> None:
    state_root = tmp_path / "lb-owner-state"
    lb._ensure_state_root(state_root)
    assert stat.S_IMODE(state_root.stat().st_mode) == 0o700
    before = lb.validate_observed_identity(_observed_lb())
    ready = lb.desired_projection(before)
    before_digest = lb._digest(before)
    ready_digest = lb._digest(ready)

    snapshot = lb.snapshot_path_for(before_digest, state_root)
    assert snapshot.parent == state_root
    attestation_path = lb._write_attestation(state_root, ready, before_digest)
    assert attestation_path == lb.attestation_path_for(ready_digest, state_root)
    assert stat.S_IMODE(attestation_path.stat().st_mode) == 0o600
    payload = json.loads(attestation_path.read_text(encoding="utf-8"))
    lb._validate_attestation(payload, ready_digest)
    assert payload["transaction_before_sha256"] == before_digest
    assert payload["ready_mutable_sha256"] == ready_digest


def test_do_lb_failover_attestation_is_fresh_double_read_and_manifest_bound(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    observed = _observed_lb()
    observed["health_check"] = {**observed["health_check"], "path": "/api/ready"}  # type: ignore[index]
    ready = lb.validate_observed_identity(observed)
    digest = lb._digest(ready)
    transaction_id = "mft_" + "f" * 64
    manifest_sha = "c" * 64
    calls: list[int] = []
    monkeypatch.setattr(lb, "_get_load_balancer", lambda: calls.append(1) or observed)
    args = SimpleNamespace(
        state_dir=tmp_path / "operator-state",
        expected_current_sha256=digest,
        transaction_id=transaction_id,
        manifest_sha256=manifest_sha,
        phase="initial",
        observation="pre",
        confirm=lb.failover_attest_confirmation(digest, transaction_id, manifest_sha, "initial", "pre"),
    )

    assert lb._attest_failover(args) == 0
    assert len(calls) == 2
    path = lb.failover_attestation_path_for(transaction_id, manifest_sha, "initial", "pre", args.state_dir)
    payload = json.loads(path.read_text(encoding="utf-8"))
    lb._validate_failover_attestation(
        payload,
        transaction_id=transaction_id,
        manifest_sha256=manifest_sha,
        ready_sha256=digest,
        phase="initial",
        observation="pre",
    )
    assert payload["observed_at"].endswith("Z")


def test_do_lb_auth_boundary_never_accepts_provider_token_from_argv_or_environment() -> None:
    source = LB_PATH.read_text(encoding="utf-8")
    assert '["doctl", "auth", "token"]' in source
    assert 'choices=("doctl", "stdin")' in source
    assert "--token" not in source
    assert 'os.getenv("DIGITALOCEAN' not in source
    assert "state-dir" in source
    parser = lb.build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["plan"])


def test_bootstrap_consumes_exact_protected_lb_attestation_without_provider_credential(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = BOOTSTRAP_PATH.read_text(encoding="utf-8")
    assert "--expected-lb-ready-sha256" in source
    assert "--expected-lb-attestation-sha256" in source
    assert "--lb-ready-attestation" in source
    assert "install-lb-ready-attestation" in source
    assert "LB_PLAN_AUTHORITY_SCHEMA" in source
    assert "LB_APPLY_EVIDENCE_SCHEMA" in source
    assert "DIGITALOCEAN_TOKEN" not in source
    assert "DIGITALOCEAN_ACCESS_TOKEN" not in source
    observed = _observed_lb()
    observed["health_check"] = {**observed["health_check"], "path": "/api/ready"}  # type: ignore[index]
    ready = lb.validate_observed_identity(observed)
    ready_sha = lb._digest(ready)
    payload = lb._attestation_payload(ready, None)
    raw = bootstrap._canonical(payload) + b"\n"
    artifact_sha = bootstrap._digest_bytes(raw)
    state_root = tmp_path / "meta-ha"
    state_root.mkdir()
    path = state_root / "lb-ready-bootstrap-attestation.json"
    path.write_bytes(raw)
    monkeypatch.setattr(bootstrap, "STATE_ROOT", state_root)
    monkeypatch.setattr(bootstrap, "LB_BOOTSTRAP_ATTESTATION_PATH", path)
    monkeypatch.setattr(bootstrap, "_secure_dir", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(bootstrap, "_secure_regular", lambda *_args, **_kwargs: path.stat())

    target_sha = "a" * 40
    authority, evidence = bootstrap._lb_owner_attestation(path, artifact_sha, ready_sha, target_sha)
    assert authority["ready_mutable_sha256"] == ready_sha
    assert authority["ready_projection"] == ready
    assert evidence["attestation_sha256"] == artifact_sha
    assert evidence["authority_sha256"] == bootstrap._digest(authority)
    assert evidence["target_sha"] == target_sha
    assert evidence["observed_at"] == payload["observed_at"]
    assert authority["health_check"] == {
        "protocol": "http",
        "port": 8003,
        "path": "/api/ready",
        "check_interval_seconds": 5,
        "response_timeout_seconds": 3,
        "healthy_threshold": 2,
        "unhealthy_threshold": 3,
    }
    assert authority["minimum_drain_seconds"] == 25
    with pytest.raises(RuntimeError, match="artifact digest changed"):
        bootstrap._lb_owner_attestation(path, "0" * 64, ready_sha, target_sha)
    with pytest.raises(RuntimeError, match="artifact digest changed"):
        bootstrap._lb_owner_attestation(path, "1" * 64, ready_sha, target_sha)
    with pytest.raises(TypeError):
        bootstrap._lb_owner_attestation(ready_sha)

    stale_payload = dict(payload)
    stale_payload["observed_at"] = (
        (datetime.now(UTC) - timedelta(minutes=6)).isoformat(timespec="seconds").replace("+00:00", "Z")
    )
    stale_raw = bootstrap._canonical(stale_payload) + b"\n"
    path.write_bytes(stale_raw)
    with pytest.raises(RuntimeError, match="not fresh enough"):
        bootstrap._lb_owner_attestation(path, bootstrap._digest_bytes(stale_raw), ready_sha, target_sha)
    path.write_bytes(raw)

    parsed = bootstrap.build_parser().parse_args(
        [
            "install-lb-ready-attestation",
            "--target-sha",
            "a" * 40,
            "--expected-attestation-sha256",
            artifact_sha,
            "--expected-ready-sha256",
            ready_sha,
            "--confirm",
            bootstrap._lb_attestation_install_confirmation(artifact_sha, ready_sha),
        ]
    )
    assert parsed.command == "install-lb-ready-attestation"

    missing_artifact_args = [
        "plan",
        "--target-sha",
        "a" * 40,
        "--expected-node01-sha",
        "b" * 40,
        "--expected-node02-sha",
        "c" * 40,
        "--expected-pg-state-sha256",
        "d" * 64,
        "--expected-lb-ready-sha256",
        ready_sha,
        "--node01-hostname",
        bootstrap.FIXED_NODES["node01"]["hostname"],
        "--node01-public-ip",
        bootstrap.FIXED_NODES["node01"]["public_ip"],
        "--node01-private-ip",
        bootstrap.FIXED_NODES["node01"]["private_ip"],
        "--node02-hostname",
        bootstrap.FIXED_NODES["node02"]["hostname"],
        "--node02-public-ip",
        bootstrap.FIXED_NODES["node02"]["public_ip"],
        "--node02-private-ip",
        bootstrap.FIXED_NODES["node02"]["private_ip"],
        "--peer-host",
        bootstrap.FIXED_NODES["node01"]["peer_ip"],
        "--drain-seconds",
        "30",
    ]
    with pytest.raises(SystemExit):
        bootstrap.build_parser().parse_args(missing_artifact_args)


def test_bootstrap_old_stable_plan_accepts_fresh_matching_apply_attestation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ready = _ready_projection()
    ready_sha = bootstrap._digest(ready)
    first_payload = lb._attestation_payload(ready, None)
    first_payload["observed_at"] = (
        (datetime.now(UTC) - timedelta(minutes=2)).isoformat(timespec="seconds").replace("+00:00", "Z")
    )
    args, path, _ = _patch_bootstrap_plan_context(monkeypatch, tmp_path, first_payload)
    first_plan, _, _, first_evidence = bootstrap._combined_plan(args)
    old_plan_sha = bootstrap._digest(first_plan)

    refreshed_payload = lb._attestation_payload(ready, None)
    refreshed_payload["observed_at"] = (
        (datetime.now(UTC) - timedelta(seconds=5)).isoformat(timespec="seconds").replace("+00:00", "Z")
    )
    refreshed_raw = bootstrap._canonical(refreshed_payload) + b"\n"
    path.write_bytes(refreshed_raw)
    args.expected_lb_attestation_sha256 = bootstrap._digest_bytes(refreshed_raw)
    args.expected_lb_ready_sha256 = ready_sha
    args.expected_plan_sha256 = old_plan_sha
    args.confirm = bootstrap._confirmation(old_plan_sha)

    refreshed_plan, _, _, refreshed_evidence, validated_sha = bootstrap._validated_apply_context(args)

    assert refreshed_plan == first_plan
    assert validated_sha == old_plan_sha
    assert refreshed_evidence["attestation_sha256"] != first_evidence["attestation_sha256"]
    assert refreshed_evidence["observed_at"] != first_evidence["observed_at"]
    assert refreshed_evidence["authority_sha256"] == first_evidence["authority_sha256"]
    assert "attestation_sha256" not in refreshed_plan["lb"]
    assert "observed_at" not in refreshed_plan["lb"]


def test_bootstrap_stale_apply_attestation_fails_before_any_transaction_mutation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ready = _ready_projection()
    payload = lb._attestation_payload(ready, None)
    payload["observed_at"] = (
        (datetime.now(UTC) - timedelta(minutes=6)).isoformat(timespec="seconds").replace("+00:00", "Z")
    )
    args, _, _ = _patch_bootstrap_plan_context(monkeypatch, tmp_path, payload)
    args.expected_plan_sha256 = "1" * 64
    args.confirm = bootstrap._confirmation(args.expected_plan_sha256)
    mutations: list[str] = []
    monkeypatch.setattr(bootstrap, "_write_coordinator_journal", lambda *_args: mutations.append("journal"))
    monkeypatch.setattr(bootstrap, "_node_call_local", lambda *_args, **_kwargs: mutations.append("local"))
    monkeypatch.setattr(bootstrap, "_remote_phase", lambda *_args, **_kwargs: mutations.append("remote"))

    with pytest.raises(RuntimeError, match="not fresh enough"):
        bootstrap._orchestrate_apply(args)

    assert mutations == []


@pytest.mark.parametrize("invalid", ["stale", "projection", "load-balancer"])
def test_bootstrap_apply_evidence_install_rejects_invalid_bytes_before_publication(
    invalid: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ready = _ready_projection()
    payload = lb._attestation_payload(ready, None)
    expected_ready_sha = bootstrap._digest(ready)
    if invalid == "stale":
        payload["observed_at"] = (
            (datetime.now(UTC) - timedelta(minutes=6)).isoformat(timespec="seconds").replace("+00:00", "Z")
        )
    elif invalid == "projection":
        changed_projection = copy.deepcopy(ready)
        changed_projection["enable_backend_keepalive"] = False
        payload["ready_projection"] = changed_projection
        payload["ready_mutable_sha256"] = bootstrap._digest(changed_projection)
        expected_ready_sha = str(payload["ready_mutable_sha256"])
    else:
        payload["load_balancer_id"] = "ffffffff-ffff-4fff-bfff-ffffffffffff"
    raw = bootstrap._canonical(payload) + b"\n"
    artifact_sha = bootstrap._digest_bytes(raw)
    publications: list[Path] = []
    monkeypatch.setattr(bootstrap, "_require_root", lambda: None)
    monkeypatch.setattr(bootstrap, "_assert_identity", lambda *_args: None)
    monkeypatch.setattr(bootstrap.sys, "stdin", SimpleNamespace(buffer=io.BytesIO(raw)))
    monkeypatch.setattr(bootstrap, "STATE_ROOT", tmp_path)
    monkeypatch.setattr(bootstrap, "LB_BOOTSTRAP_ATTESTATION_PATH", tmp_path / "lb-attestation.json")
    monkeypatch.setattr(bootstrap, "_atomic_write", lambda path, *_args, **_kwargs: publications.append(path))

    with pytest.raises(RuntimeError):
        bootstrap._install_lb_ready_attestation(
            artifact_sha,
            expected_ready_sha,
            bootstrap._lb_attestation_install_confirmation(artifact_sha, expected_ready_sha),
        )

    assert publications == []


@pytest.mark.parametrize("drift", ["projection", "load-balancer", "target"])
def test_bootstrap_apply_authority_drift_fails_before_any_transaction_mutation(
    drift: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ready = _ready_projection()
    payload = lb._attestation_payload(ready, None)
    args, path, _ = _patch_bootstrap_plan_context(monkeypatch, tmp_path, payload)
    plan, _, _, _ = bootstrap._combined_plan(args)
    args.expected_plan_sha256 = bootstrap._digest(plan)
    args.confirm = bootstrap._confirmation(args.expected_plan_sha256)

    if drift == "projection":
        changed_projection = copy.deepcopy(ready)
        changed_projection["enable_backend_keepalive"] = False
        payload["ready_projection"] = changed_projection
        payload["ready_mutable_sha256"] = bootstrap._digest(changed_projection)
        args.expected_lb_ready_sha256 = str(payload["ready_mutable_sha256"])
    elif drift == "load-balancer":
        payload["load_balancer_id"] = "ffffffff-ffff-4fff-bfff-ffffffffffff"
    else:
        args.target_sha = "e" * 40
    if drift != "target":
        raw = bootstrap._canonical(payload) + b"\n"
        path.write_bytes(raw)
        args.expected_lb_attestation_sha256 = bootstrap._digest_bytes(raw)

    mutations: list[str] = []
    monkeypatch.setattr(bootstrap, "_write_coordinator_journal", lambda *_args: mutations.append("journal"))
    monkeypatch.setattr(bootstrap, "_node_call_local", lambda *_args, **_kwargs: mutations.append("local"))
    monkeypatch.setattr(bootstrap, "_remote_phase", lambda *_args, **_kwargs: mutations.append("remote"))

    with pytest.raises(RuntimeError):
        bootstrap._orchestrate_apply(args)

    assert mutations == []


def test_bootstrap_coordinator_records_the_actual_refreshed_apply_evidence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ready = _ready_projection()
    payload = lb._attestation_payload(ready, None)
    args, _, raw = _patch_bootstrap_plan_context(monkeypatch, tmp_path, payload)
    plan, _, _, _ = bootstrap._combined_plan(args)
    args.expected_plan_sha256 = bootstrap._digest(plan)
    args.confirm = bootstrap._confirmation(args.expected_plan_sha256)
    captured: list[dict[str, object]] = []

    class JournalCaptured(Exception):
        pass

    def capture(payload_value: dict[str, object]) -> None:
        captured.append(copy.deepcopy(payload_value))
        raise JournalCaptured

    monkeypatch.setattr(bootstrap, "_write_coordinator_journal", capture)
    with pytest.raises(JournalCaptured):
        bootstrap._orchestrate_apply(args)

    assert len(captured) == 1
    journal = captured[0]
    evidence = journal["lb_apply_evidence"]
    assert isinstance(evidence, dict)
    assert evidence["attestation_sha256"] == bootstrap._digest_bytes(raw)
    assert evidence["observed_at"] == payload["observed_at"]
    assert evidence["authority_sha256"] == bootstrap._digest(journal["lb_plan_authority"])
    assert evidence["target_sha"] == args.target_sha


def test_bootstrap_pg_probe_is_self_contained_for_observed_old_baselines() -> None:
    # Both observed live SHAs predate the release helper functions. The one-time
    # plan therefore must use only the already-installed SQLAlchemy dependency
    # and explicit SQL, never symbols imported from the undeployed target tree.
    compile(bootstrap.PG_PROBE, "<bootstrap-pg-probe>", "exec")
    assert "from sqlalchemy import create_engine, text" in bootstrap.PG_PROBE
    assert "meta_asset_bindings" in bootstrap.PG_PROBE
    assert "meta_registry_audit_events" in bootstrap.PG_PROBE
    assert "REPEATABLE READ" in bootstrap.PG_PROBE
    assert "pg_advisory_xact_lock" in bootstrap.PG_PROBE
    assert "from db." not in bootstrap.PG_PROBE
    assert "from services." not in bootstrap.PG_PROBE
    assert "/opt/linasbot" not in bootstrap.PG_PROBE


def test_bootstrap_renders_only_the_fixed_nonsecret_ha_contract() -> None:
    original = (
        b"SECRET_TOKEN=keep-this-byte-for-byte\n"
        b"META_REGISTRY_BACKEND=file\n"
        b"META_DELETION_NODE_ID=old\n"
        b"# owner comment\n"
    )
    rendered = bootstrap._render_env(original, "node02")
    values = bootstrap._parse_env(rendered)

    assert b"SECRET_TOKEN=keep-this-byte-for-byte\n" in rendered
    assert b"# owner comment\n" in rendered
    assert values["META_DELETION_NODE_ID"] == "node02"
    assert values["META_DELETION_REQUIRED_NODES"] == "node01,node02"
    assert values["META_REGISTRY_BACKEND"] == "postgres"
    assert values["META_HA_LB_READY_HEALTHCHECK_APPROVED"] == "true"
    assert values["META_HA_LB_DRAIN_SECONDS"] == "30"
    assert values["LINAS_MAINTENANCE_DRAIN_FILE"] == "/var/lib/linasbot/meta-ha/maintenance"
    assert values["LINAS_HA_PEER_HOST"] == "10.106.0.3"


def test_bootstrap_fixed_topology_and_confirmation_cannot_be_inferred_silently() -> None:
    assert bootstrap.FIXED_NODES == {
        "node01": {
            "hostname": "ubuntu-s-2vcpu-2gb-90gb-intel-lon1-01",
            "public_ip": "139.59.167.62",
            "private_ip": "10.106.0.3",
            "peer_ip": "10.106.0.4",
        },
        "node02": {
            "hostname": "linas-app-lon1-02",
            "public_ip": "167.99.89.243",
            "private_ip": "10.106.0.4",
            "peer_ip": "10.106.0.3",
        },
    }
    digest = "b" * 64
    assert bootstrap._confirmation(digest) == ("BOOTSTRAP_META_HA_BBBBBBBBBBBBBBBB_AND_ROTATE_EXPOSED_CREDENTIALS")
    assert "historical .env backups were group/world-readable" in bootstrap.ROTATION_WARNING


def test_bootstrap_source_encodes_drain_archive_legacy_and_recovery_boundaries() -> None:
    source = BOOTSTRAP_PATH.read_text(encoding="utf-8")
    prepare = source.index('_node_call_local("prepare"')
    peer_prepare = source.index('_remote_phase(source, source_sha, "prepare"', prepare)
    peer_drain = source.index('_remote_phase(source, source_sha, "drain"', peer_prepare)
    public = source.index("_public_ready()", peer_drain)
    first_sleep = source.index("time.sleep(30)", public)
    local_drain = source.index('_node_call_local("drain"', first_sleep)
    first_apply = source.index('"apply", node_id="node02"', local_drain)

    assert prepare < peer_prepare < peer_drain < public < first_sleep < local_drain < first_apply
    for contract in (
        "bootstrap.active",
        "bootstrap.coordinator.json",
        "transaction.json",
        "env.before",
        "deploy.active",
        "deploy-node.active",
        "ConditionPathExists=!/var/lib/linasbot/meta-ha/bootstrap.runtime.guard",
        "direct LB port 8003 did not close",
        "historical-env",
        "os.rename(source, destination)",
        "linas_ai_bot.service.before",
        '"disable", "--now", "linas_ai_bot.service"',
        "legacy runtime retirement verification failed",
        "state_sha256",
        "PostgreSQL authority is not the writable primary",
        "recover-rollback",
        "persistent maintenance retained",
        "StrictHostKeyChecking=yes",
    ):
        assert contract in source
    assert "unlink(LEGACY_UNIT" not in source
    assert "rmtree" not in source


def test_bootstrap_refuses_a_per_node_release_transaction_sentinel() -> None:
    source = BOOTSTRAP_PATH.read_text(encoding="utf-8")
    probe = source[source.index("def _node_probe(") : source.index("def _lb_owner_attestation")]

    assert bootstrap.DEPLOY_NODE_ACTIVE == bootstrap.STATE_ROOT / "deploy-node.active"
    assert "DEPLOY_NODE_ACTIVE.exists()" in probe
    assert "DEPLOY_NODE_ACTIVE.is_symlink()" in probe
    assert "an interrupted HA release transaction requires confirmed recovery" in probe


def test_bootstrap_allows_only_disconnected_missing_credential_tombstones() -> None:
    probe = bootstrap.PG_PROBE
    assert 'binding.get("status") != "disconnected"' in probe
    assert 'credential = credentials.get(binding.get("credential_id"))' in probe
    assert "data-deletion/deauthorization" in probe


def test_bootstrap_legacy_retirement_is_durable_and_exactly_rollback_safe() -> None:
    source = BOOTSTRAP_PATH.read_text(encoding="utf-8")
    for contract in (
        "legacy-linas-ai-bot-retired",
        "90-linasbot-retired.conf",
        "LEGACY_RETIREMENT_GUARD_BYTES",
        "ConditionPathExists=!/var/lib/linasbot/meta-ha/legacy-linas-ai-bot-retired",
        "prove_manual_start_denied=True",
        "_remove_legacy_retirement_for_rollback",
    ):
        assert contract in source
    install = source[source.index("def _install_legacy_retirement") : source.index("def _remove_legacy_retirement")]
    guard_publish = install.index("_atomic_write(\n            LEGACY_RETIREMENT_GUARD")
    marker_publish = install.index("_atomic_write(\n            LEGACY_RETIREMENT_MARKER")
    disable = install.index('["systemctl", "disable", "--now", "linas_ai_bot.service"]')
    assert disable < guard_publish < marker_publish
    assert install.index('["systemctl", "daemon-reload"]') < install.index('b"legacy-linas-ai-bot-retired\\n"')
    assert "bootstrap.active" in bootstrap.LEGACY_RETIREMENT_GUARD_BYTES.decode()
    rollback = source[source.index("def _remove_legacy_retirement_for_rollback") : source.index("def _node_apply")]
    assert "marker_exists != guard_exists" not in rollback
    assert rollback.index('"disable", "--now", "linas_ai_bot.service"') < rollback.index("if marker_exists:")


def test_bootstrap_boot_guards_are_fail_closed_at_every_publish_and_reboot_boundary() -> None:
    source = BOOTSTRAP_PATH.read_text(encoding="utf-8")
    guard = bootstrap.BOOT_GUARD.decode()
    assert guard == (
        "[Unit]\n"
        "# Exact one-time Meta HA bootstrap boot guard.\n"
        "ConditionPathExists=!/var/lib/linasbot/meta-ha/bootstrap.runtime.guard\n"
    )
    install = source[source.index("def _install_boot_guards") : source.index("def _remove_boot_guards")]
    assert install.index("_secure_regular(ACTIVE_PATH)") < install.index("for path in BOOT_GUARDS")
    remove = source[source.index("def _remove_boot_guards") : source.index("def _install_nginx_override")]
    assert remove.index('["systemctl", "is-active", unit]') < remove.index("for path in BOOT_GUARDS")
    assert remove.index('["systemctl", "is-enabled", unit]') < remove.index("for path in BOOT_GUARDS")

    drain = source[source.index("def _node_drain") : source.index("def _move_historical")]
    install_guard = drain.index("_install_boot_guards(backup)")
    arm_runtime = drain.index("_arm_bootstrap_runtime_guard()")
    disable = drain.index('_quiesce_and_disable_units(probe["canonical_services"])')
    maintenance = drain.index("_arm_marker(PERSISTENT_MARKER)")
    assert install_guard < arm_runtime < disable < maintenance

    admit = source[source.index("def _node_admit(") : source.index("def _node_redrain")]
    quiesce = admit.index("_quiesce_and_disable_units(states)")
    static_guard = admit.index("_install_controlled_failover_guard_contract()")
    release_runtime = admit.index("_clear_bootstrap_runtime_guard()")
    rearm_runtime = admit.index("_arm_bootstrap_runtime_guard()")
    assert quiesce < static_guard < release_runtime < rearm_runtime
    assert "_remove_boot_guards(backup)" not in admit
    assert admit.index("_start_units_disabled({API_UNIT: states[API_UNIT]})") < admit.index("_wait_health()")
    assert admit.index("_wait_health()") < admit.index(
        "_start_units_disabled({unit: states[unit] for unit in WORKER_UNITS})"
    )
    process_disabled = admit.index("_assert_process_contract(node_id, require_enabled=False)")
    enable = admit.index("_enable_units_after_verification(states)")
    process_enabled = admit.index("_assert_process_contract(node_id, require_enabled=True)")
    clear = admit.index("_unlink_durable(VOLATILE_MARKER)")
    assert admit.index("_wait_health()") < process_disabled < enable < process_enabled < clear


def test_bootstrap_installs_permanent_controlled_failover_guards_only_while_quiesced() -> None:
    source = BOOTSTRAP_PATH.read_text(encoding="utf-8")
    payload = bootstrap.CONTROLLED_FAILOVER_GUARD.decode()
    assert payload == (
        "[Unit]\n"
        "# Permanently installed controlled Meta failover reboot guard.\n"
        "ConditionPathExists=!/var/lib/linasbot/meta-ha/controlled-failover.runtime.guard\n"
    )
    install = source[
        source.index("def _install_controlled_failover_guard_contract") : source.index("def _install_nginx_override")
    ]
    assert install.index('"is-active", unit') < install.index("for path in CONTROLLED_FAILOVER_GUARDS")
    assert install.index('"is-enabled", unit') < install.index("for path in CONTROLLED_FAILOVER_GUARDS")
    assert install.index("for path in CONTROLLED_FAILOVER_GUARDS") < install.index('["systemctl", "daemon-reload"]')
    admit = source[source.index("def _node_admit(") : source.index("def _node_redrain")]
    quiesce = admit.index("_quiesce_and_disable_units(states)")
    static_install = admit.index("_install_controlled_failover_guard_contract()")
    runtime_release = admit.index("_clear_bootstrap_runtime_guard()")
    assert quiesce < static_install < runtime_release
    assert "_remove_boot_guards(backup)" not in admit
    commit = source[source.index("def _node_commit_proof") : source.index("def _node_finalize")]
    assert "_assert_controlled_failover_guard_contract()" in commit


def test_bootstrap_requires_and_proves_all_four_durable_worker_processes() -> None:
    source = BOOTSTRAP_PATH.read_text(encoding="utf-8")
    process = source[source.index("def _assert_process_contract") : source.index("def _node_admit")]
    commit = source[source.index("def _node_commit_proof") : source.index("def _node_finalize")]
    values = {"REDIS_URL": "redis://private", "LINAS_REQUIRE_REDIS": "true"}
    states = {
        unit: {"active": "active", "enabled": "enabled"} for unit in (bootstrap.API_UNIT, *bootstrap.WORKER_UNITS)
    }

    bootstrap._assert_durable_worker_preconditions(values, states)
    states[bootstrap.WORKER_UNITS[-1]]["active"] = "inactive"
    with pytest.raises(RuntimeError, match="every canonical API/worker active and enabled"):
        bootstrap._assert_durable_worker_preconditions(values, states)

    assert '[str(REPO_DIR / "venv/bin/python"), "main.py"]' in process
    assert '"scripts/run_queue_worker.py", "--queue", queue' in process
    assert 'Path(os.path.realpath(proc / "cwd")) != REPO_DIR' in process
    assert '(proc / "environ").read_bytes()' in process
    assert "process_values.get(key) != value" in process
    assert "stable_pid != pid" in process
    assert "canonical process is not active before maintenance clear" in process
    assert "canonical process is not enabled before maintenance clear" in process
    assert "_assert_process_contract(node_id, require_enabled=True)" in commit
    rollback = source[source.index("def _node_admit_rollback") : source.index("def _node_commit_proof")]
    assert rollback.index(
        "_assert_process_contract(node_id, require_enabled=False, require_bootstrapped_contract=False)"
    ) < rollback.index("_enable_units_after_verification(states)")
    assert rollback.index("_enable_units_after_verification(states)") < rollback.index(
        "_assert_process_contract(node_id, require_enabled=True, require_bootstrapped_contract=False)"
    )
    assert rollback.index(
        "_assert_process_contract(node_id, require_enabled=True, require_bootstrapped_contract=False)"
    ) < rollback.index("_unlink_durable(VOLATILE_MARKER)")


def test_bootstrap_prepare_and_lost_ack_are_idempotently_recoverable() -> None:
    source = BOOTSTRAP_PATH.read_text(encoding="utf-8")
    prepare = source[source.index("def _node_prepare") : source.index("def _node_abort_prepare")]
    status = source[source.index("def _node_status") : source.index("def _public_ready")]
    apply = source[source.index("def _orchestrate_apply") : source.index("def _orchestrate_recovery")]

    active_publish = prepare.index("_atomic_write(ACTIVE_PATH, active_payload, no_replace=True)")
    backup_create = prepare.index("backup.mkdir(mode=0o700)")
    env_backup = prepare.index('write_or_verify(backup / "env.before"')
    journal_publish = prepare.index("_write_journal(backup, prepared)")
    assert active_publish < backup_create < env_backup < journal_publish
    assert "bootstrap active sentinel belongs to another prepare" in prepare
    assert "partial bootstrap prepare artifact changed" in prepare
    assert "partial bootstrap prepare journal changed" in prepare
    assert "node state changed after the owner-authorized bootstrap plan" in prepare
    assert "expected_probe_sha256" in prepare
    assert 'status = str(journal.get("status") or "preparing")' in status
    assert "durably finalized and has no active sentinel" in status

    catch = apply[apply.index("except BaseException:") :]
    peer_abort = catch.index('_remote_phase(source, source_sha, "abort-prepare"')
    local_abort = catch.index('_node_call_local("abort-prepare"')
    coordinator_unlink = catch.index("_unlink_durable(COORDINATOR_PATH)")
    assert peer_abort < coordinator_unlink
    assert local_abort < coordinator_unlink
    assert "local_prepared" not in apply and "peer_prepared" not in apply


def test_bootstrap_prepare_abort_receipt_closes_every_active_unlink_boundary(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    tx_id = "a" * 32
    plan_sha = "b" * 64
    state_root = tmp_path / "state"
    backup = tmp_path / f"backup-{tx_id}"
    active = state_root / "bootstrap.active"
    persistent = state_root / "maintenance"
    volatile = state_root / "maintenance-volatile"
    runtime_guard = state_root / "bootstrap.runtime.guard"
    boot_guards = (tmp_path / "api.guard", tmp_path / "worker.guard")
    committed = state_root / "bootstrap.committed.json"
    state_root.mkdir()
    backup.mkdir()

    def local_atomic_write(path: Path, payload: bytes, **_kwargs: object) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)

    monkeypatch.setattr(bootstrap, "_backup_dir", lambda _tx_id: backup)
    monkeypatch.setattr(bootstrap, "ACTIVE_PATH", active)
    monkeypatch.setattr(bootstrap, "PERSISTENT_MARKER", persistent)
    monkeypatch.setattr(bootstrap, "VOLATILE_MARKER", volatile)
    monkeypatch.setattr(bootstrap, "BOOTSTRAP_RUNTIME_GUARD", runtime_guard)
    monkeypatch.setattr(bootstrap, "BOOT_GUARDS", boot_guards)
    monkeypatch.setattr(bootstrap, "COMMITTED_PROOF_PATH", committed)
    monkeypatch.setattr(bootstrap, "_secure_dir", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(bootstrap, "_secure_regular", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(bootstrap, "_atomic_write", local_atomic_write)
    monkeypatch.setattr(bootstrap, "_port_listening", lambda port: port == 8003)

    active.write_text(
        json.dumps({"schema": 1, "tx_id": tx_id, "plan_sha256": plan_sha, "node_id": "node01"}),
        encoding="utf-8",
    )
    # Model a stop after the durable abort journal but before its receipt.
    (backup / "journal.json").write_text(
        json.dumps(
            {
                "schema": 1,
                "tx_id": tx_id,
                "plan_sha256": plan_sha,
                "status": "aborted_before_drain",
            }
        ),
        encoding="utf-8",
    )
    assert bootstrap._node_status(tx_id, plan_sha)["state"] == "active"

    bootstrap._node_abort_prepare(tx_id, plan_sha)
    assert not active.exists()
    assert (backup / "abort.complete.json").exists()
    assert bootstrap._node_status(tx_id, plan_sha) == {
        "state": "released",
        "status": "aborted_before_drain",
        "commit_proof": False,
    }
    # An ACK loss after the sentinel unlink is an exact idempotent success.
    bootstrap._node_abort_prepare(tx_id, plan_sha)


def test_bootstrap_release_receipt_is_last_and_recovery_replays_pending_cleanup() -> None:
    source = BOOTSTRAP_PATH.read_text(encoding="utf-8")
    release = source[source.index("def _node_release_active") : source.index("def _node_status")]
    active_unlink = release.index("_unlink_durable(ACTIVE_PATH)")
    runtime_clear = release.index("_clear_bootstrap_runtime_guard()")
    guard_cleanup = release.index("_remove_boot_guards(backup, require_quiesced=False)")
    process_proof = release.index("_assert_process_contract(")
    receipt_publish = release.rindex("_atomic_write(")
    assert active_unlink < runtime_clear < guard_cleanup < process_proof < receipt_publish

    status = source[source.index("def _node_status") : source.index("def _public_ready")]
    assert '"released" if released or aborted else "release-pending"' in status
    recovery = source[source.index("def _recover_decided_node") : source.index("def _orchestrate_decided_recovery")]
    pending = recovery[recovery.index('if status["state"] == "release-pending"') :]
    assert pending.index('call(\n            "release-active"') < pending.index("return")


def test_standalone_bootstrap_rollback_reconciles_released_and_pending_nodes(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    tx_id = "a" * 32
    plan_sha = "b" * 64
    target_sha = "c" * 40
    calls: list[tuple[str, object]] = []
    monkeypatch.setattr(bootstrap, "COORDINATOR_PATH", tmp_path / "coordinator")
    monkeypatch.setattr(bootstrap, "_helper_source", lambda: (b"helper", "d" * 64))
    monkeypatch.setattr(bootstrap, "_assert_exact_helper", lambda *_args: None)
    monkeypatch.setattr(bootstrap, "_assert_identity", lambda *_args: None)
    monkeypatch.setattr(bootstrap, "_public_ready", lambda: calls.append(("public", True)))

    def local(command: str, **_kwargs: str) -> object:
        calls.append(("local", command))
        if command == "status":
            return {"state": "released", "status": "rolled_back", "commit_proof": False}
        raise AssertionError(f"unexpected local command: {command}")

    def remote(_source: bytes, _sha: str, command: str, **_kwargs: str) -> object:
        calls.append(("peer", command))
        if command == "status":
            return {"state": "release-pending", "status": "recovery_rolled_back", "commit_proof": False}
        raise AssertionError(f"unexpected peer command: {command}")

    def recover_node(**kwargs: object) -> None:
        calls.append(("recover", kwargs["local"]))

    monkeypatch.setattr(bootstrap, "_node_call_local", local)
    monkeypatch.setattr(bootstrap, "_remote_phase", remote)
    monkeypatch.setattr(bootstrap, "_recover_decided_node", recover_node)
    args = SimpleNamespace(
        target_sha=target_sha,
        tx_id=tx_id,
        plan_sha256=plan_sha,
        peer_host=bootstrap.FIXED_NODES["node01"]["peer_ip"],
        confirm=bootstrap._recovery_confirmation(tx_id, plan_sha),
    )

    assert bootstrap._orchestrate_recovery(args) == 0
    assert ("local", "redrain") not in calls
    assert ("peer", "redrain") not in calls
    assert [(kind, value) for kind, value in calls if kind == "recover"] == [
        ("recover", False),
        ("recover", True),
    ]
    assert calls[-1] == ("public", True)


def test_standalone_bootstrap_rollback_redrains_only_unreleased_mutated_nodes(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    tx_id = "a" * 32
    plan_sha = "b" * 64
    calls: list[tuple[str, str]] = []
    monkeypatch.setattr(bootstrap, "COORDINATOR_PATH", tmp_path / "coordinator")
    monkeypatch.setattr(bootstrap, "_helper_source", lambda: (b"helper", "d" * 64))
    monkeypatch.setattr(bootstrap, "_assert_exact_helper", lambda *_args: None)
    monkeypatch.setattr(bootstrap, "_assert_identity", lambda *_args: None)
    monkeypatch.setattr(bootstrap, "_public_ready", lambda: None)

    def local(command: str, **_kwargs: str) -> object:
        calls.append(("local", command))
        if command == "status":
            return {"state": "active", "status": "admitted", "commit_proof": False}
        if command == "redrain":
            return None
        raise AssertionError(command)

    def remote(_source: bytes, _sha: str, command: str, **_kwargs: str) -> object:
        calls.append(("peer", command))
        if command == "status":
            return {"state": "released", "status": "rolled_back", "commit_proof": False}
        raise AssertionError(command)

    monkeypatch.setattr(bootstrap, "_node_call_local", local)
    monkeypatch.setattr(bootstrap, "_remote_phase", remote)
    monkeypatch.setattr(bootstrap, "_recover_decided_node", lambda **_kwargs: None)
    args = SimpleNamespace(
        target_sha="c" * 40,
        tx_id=tx_id,
        plan_sha256=plan_sha,
        peer_host=bootstrap.FIXED_NODES["node01"]["peer_ip"],
        confirm=bootstrap._recovery_confirmation(tx_id, plan_sha),
    )

    assert bootstrap._orchestrate_recovery(args) == 0
    assert calls.count(("local", "redrain")) == 1
    assert ("peer", "redrain") not in calls


def test_bootstrap_commit_memory_never_precedes_durable_readback(monkeypatch: pytest.MonkeyPatch) -> None:
    lb_authority, lb_evidence = _bootstrap_lb_authority_and_evidence()
    payload = {
        "schema": bootstrap.BOOTSTRAP_COORDINATOR_SCHEMA,
        "tx_id": "a" * 32,
        "plan_sha256": "b" * 64,
        "target_sha": "c" * 40,
        "node01_previous_sha": "d" * 40,
        "node02_previous_sha": "e" * 40,
        "expected_pg_state_sha256": "f" * 64,
        "lb_plan_authority": lb_authority,
        "lb_apply_evidence": lb_evidence,
        "source_sha256": "1" * 64,
        "peer_host": bootstrap.FIXED_NODES["node01"]["peer_ip"],
        "phase": "both-verified",
        "decision": "rollback",
    }

    def fail_before_replace(_candidate: dict[str, object]) -> None:
        raise OSError("injected-before-replace")

    monkeypatch.setattr(bootstrap, "_write_coordinator_journal", fail_before_replace)
    with pytest.raises(OSError, match="before-replace"):
        bootstrap._publish_commit_decision(payload)
    assert payload["decision"] == "rollback"


def test_bootstrap_recovery_journal_keeps_apply_evidence_exact(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    lb_authority, lb_evidence = _bootstrap_lb_authority_and_evidence()
    state_root = tmp_path / "state"
    state_root.mkdir()
    coordinator_path = state_root / "bootstrap.coordinator.json"
    payload = {
        "schema": bootstrap.BOOTSTRAP_COORDINATOR_SCHEMA,
        "tx_id": "a" * 32,
        "plan_sha256": "b" * 64,
        "target_sha": "c" * 40,
        "node01_previous_sha": "d" * 40,
        "node02_previous_sha": "e" * 40,
        "expected_pg_state_sha256": "f" * 64,
        "lb_plan_authority": lb_authority,
        "lb_apply_evidence": lb_evidence,
        "source_sha256": "1" * 64,
        "peer_host": bootstrap.FIXED_NODES["node01"]["peer_ip"],
        "phase": "planned",
        "decision": "rollback",
    }

    def local_atomic_write(path: Path, body: bytes, **_kwargs: object) -> None:
        path.write_bytes(body)

    monkeypatch.setattr(bootstrap, "STATE_ROOT", state_root)
    monkeypatch.setattr(bootstrap, "COORDINATOR_PATH", coordinator_path)
    monkeypatch.setattr(bootstrap, "_secure_dir", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(bootstrap, "_secure_regular", lambda *_args, **_kwargs: coordinator_path.stat())
    monkeypatch.setattr(bootstrap, "_atomic_write", local_atomic_write)

    bootstrap._write_coordinator_journal(payload)
    advanced = {**payload, "phase": "node01-prepared"}
    bootstrap._write_coordinator_journal(advanced)
    raw = coordinator_path.read_bytes()
    recovered = bootstrap._read_coordinator_journal(bootstrap._digest_bytes(raw))
    assert recovered["lb_apply_evidence"] == lb_evidence

    changed_evidence = {**lb_evidence, "attestation_sha256": "8" * 64}
    with pytest.raises(RuntimeError, match="immutable contract changed"):
        bootstrap._write_coordinator_journal({**advanced, "lb_apply_evidence": changed_evidence})
    with pytest.raises(RuntimeError, match="changed after owner confirmation"):
        bootstrap._read_coordinator_journal("7" * 64)


def test_bootstrap_durable_decision_recovery_survives_finalize_ack_loss() -> None:
    source = BOOTSTRAP_PATH.read_text(encoding="utf-8")
    apply = source[source.index("def _orchestrate_apply") : source.index("def _orchestrate_recovery")]
    recovery = source[source.index("def _orchestrate_decided_recovery") : source.index("def _decided_recovery_status")]
    publish = source[source.index("def _publish_commit_decision") : source.index("def _parse_env")]
    assert "bootstrap.coordinator.json" in source
    assert apply.index('update_coordinator("planned")') < apply.index('_node_call_local("prepare"')
    assert publish.index("_write_coordinator_journal(candidate)") < publish.index("_read_current_coordinator_journal()")
    assert apply.index("coordinator = _publish_commit_decision(coordinator)") < apply.index(
        'update_coordinator("node02-admit-started")'
    )
    assert apply.index("coordinator = _publish_commit_decision(coordinator)") < apply.index('"commit-proof"')
    assert apply.index("persisted_coordinator, _ = _read_current_coordinator_journal()") < apply.index(
        "if not drain_started:"
    )
    assert apply.index('"finalize"') < apply.index('"release-active"')
    assert "durable bootstrap commit decision cannot be reversed" in source
    assert '"recover-decided"' in source
    assert '"recovery-status"' in source
    assert "RECOVER_BOOTSTRAP_" in source
    assert "_recover_decided_node" in recovery
    assert recovery.index("_recover_decided_node(") < recovery.index("_unlink_durable(COORDINATOR_PATH)")


def test_bootstrap_refuses_controlled_failover_and_registry_nfs_retirement() -> None:
    source = BOOTSTRAP_PATH.read_text(encoding="utf-8")
    probe = source[source.index("def _node_probe(") : source.index("def _lb_owner_attestation")]
    assert 'CONTROLLED_FAILOVER_ACTIVE = STATE_ROOT / "controlled-failover.active"' in source
    assert 'REGISTRY_NFS_RETIRE_ACTIVE = STATE_ROOT / "registry-nfs-retire.active"' in source
    assert "CONTROLLED_FAILOVER_ACTIVE.exists()" in probe
    assert "REGISTRY_NFS_RETIRE_ACTIVE.exists()" in probe
    assert "PYTHON_RUNTIME_PROVISION_ACTIVE.exists()" in probe
    assert "PYTHON_RUNTIME_PROVISION_COORDINATOR.exists()" in probe
    installer = source[source.index("def _install_lb_ready_attestation") : source.index("def _lb_owner_attestation")]
    assert "PYTHON_RUNTIME_PROVISION_ACTIVE" in installer
    assert "PYTHON_RUNTIME_PROVISION_COORDINATOR" in installer


@pytest.mark.parametrize("key", ["PYTHONPATH", "PYTHONHOME", "LD_PRELOAD", "LD_AUDIT", "BASH_ENV", "NODE_OPTIONS"])
def test_bootstrap_rejects_code_loader_environment_controls(key: str) -> None:
    with pytest.raises(RuntimeError, match="forbidden code-loader control"):
        bootstrap._assert_no_execution_env_injection({key: "/outside"})


def test_bootstrap_no_replace_authority_adopts_the_post_link_crash_state(tmp_path: Path) -> None:
    payload = b'{"schema":1}\n'
    final = tmp_path / "probe-authority.json"
    temporary = tmp_path / ".probe-authority.json.bootstrap.injected"
    temporary.write_bytes(payload)
    temporary.chmod(0o600)
    os.link(temporary, final)
    assert final.stat().st_nlink == 2

    assert (
        bootstrap._read_authority_file(
            final,
            expected_uid=os.getuid(),
            expected_gid=os.getgid(),
        )
        == payload
    )
    assert final.stat().st_nlink == 1
    assert not temporary.exists()

    unknown_final = tmp_path / "unknown-authority.json"
    unknown_alias = tmp_path / "unrelated-hardlink"
    unknown_final.write_bytes(payload)
    unknown_final.chmod(0o600)
    os.link(unknown_final, unknown_alias)
    with pytest.raises(PermissionError, match="unsafe bootstrap authority"):
        bootstrap._read_authority_file(
            unknown_final,
            expected_uid=os.getuid(),
            expected_gid=os.getgid(),
        )


def test_bootstrap_guard_callers_repair_exact_post_link_crash_aliases(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    runtime_guard = tmp_path / "bootstrap.runtime.guard"
    runtime_alias = tmp_path / ".bootstrap.runtime.guard.bootstrap.killed"
    runtime_guard.write_bytes(bootstrap.BOOTSTRAP_RUNTIME_GUARD_BYTES)
    runtime_guard.chmod(0o600)
    os.link(runtime_guard, runtime_alias)

    controlled_paths = (tmp_path / "api.guard", tmp_path / "worker.guard")
    controlled_aliases: list[Path] = []
    for path in controlled_paths:
        path.write_bytes(bootstrap.CONTROLLED_FAILOVER_GUARD)
        path.chmod(0o644)
        alias = path.parent / f".{path.name}.bootstrap.killed"
        os.link(path, alias)
        controlled_aliases.append(alias)

    original_read = bootstrap._read_regular_any_owner

    def root_metadata(path: Path):  # type: ignore[no-untyped-def]
        payload, info = original_read(path)
        return payload, SimpleNamespace(
            st_uid=0,
            st_gid=0,
            st_mode=info.st_mode,
            st_nlink=info.st_nlink,
        )

    monkeypatch.setattr(bootstrap, "BOOTSTRAP_RUNTIME_GUARD", runtime_guard)
    monkeypatch.setattr(bootstrap, "CONTROLLED_FAILOVER_GUARDS", controlled_paths)
    monkeypatch.setattr(
        bootstrap,
        "CONTROLLED_FAILOVER_RUNTIME_GUARD",
        tmp_path / "controlled-failover.runtime.guard",
    )
    monkeypatch.setattr(bootstrap, "_read_regular_any_owner", root_metadata)
    monkeypatch.setattr(
        bootstrap,
        "_run",
        lambda *_args, **_kwargs: SimpleNamespace(stdout="no\n", returncode=0),
    )

    bootstrap._assert_bootstrap_runtime_guard()
    bootstrap._assert_controlled_failover_guard_contract()
    assert runtime_guard.stat().st_nlink == 1
    assert not runtime_alias.exists()
    assert all(path.stat().st_nlink == 1 for path in controlled_paths)
    assert all(not alias.exists() for alias in controlled_aliases)


def test_bootstrap_runtime_launcher_and_probe_never_execute_the_legacy_venv(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = BOOTSTRAP_PATH.read_text(encoding="utf-8")
    probe = source[source.index("def _prepare_probe_environment") : source.index("def _service_state")]
    assert "wheelhouse.tar" in probe
    assert 'str(SYSTEM_PYTHON), "-B", "-I", "-m", "venv"' in probe
    assert 'str(SYSTEM_PYTHON),\n            "-B",\n            "-I",\n            "-m",\n            "pip"' in probe
    for option in (
        '"--isolated"',
        '"--no-index"',
        '"--no-cache-dir"',
        '"--require-hashes"',
        '"--only-binary=:all:"',
        '"--no-compile"',
    ):
        assert option in probe
    assert 'REPO_DIR / "venv/bin/python"' not in probe
    assert '[str(SYSTEM_PYTHON), "-B", "-I", "-S", "-c", runner' in probe

    helper = BOOTSTRAP_PATH.read_bytes()
    helper_sha = bootstrap._digest_bytes(helper)
    authority = {
        "authority_root": "/state/python-runtime-transactions/pyr_" + "a" * 32 + "/authority",
        "control_root": "/state/python-runtime-transactions/pyr_" + "a" * 32 + "/control",
        "launcher_path": "/state/python-runtime-provision-launchers/1-" + "b" * 64 + ".py",
        "shared": {"plan_sha256": "c" * 64},
    }
    observed: list[list[str]] = []
    monkeypatch.setattr(bootstrap, "_runtime_authority", lambda node_id: authority)
    monkeypatch.setattr(
        bootstrap.subprocess,
        "run",
        lambda command, **_kwargs: observed.append(command) or SimpleNamespace(returncode=0, stdout=b"{}\n"),
    )
    assert bootstrap._remote("10.106.0.4", helper, helper_sha, ["node-probe"]) == "{}\n"
    command = observed[0]
    launcher = command.index(authority["launcher_path"])
    assert command[launcher - 4 : launcher] == ["/usr/bin/python3", "-B", "-I", "-S"]
    assert command[launcher + 1 : launcher + 5] == [
        "run-bootstrap",
        str(Path(authority["authority_root"]).parent),
        authority["control_root"],
        "c" * 64,
    ]
    assert "python3.11" not in " ".join(command)


def test_bootstrap_first_transition_orders_unit_and_bytecode_authority_before_commit() -> None:
    source = BOOTSTRAP_PATH.read_text(encoding="utf-8")
    prepare = source[source.index("def _node_prepare") : source.index("def _node_abort_prepare")]
    drain = source[source.index("def _node_drain") : source.index("def _transition_historical_env")]
    apply = source[source.index("def _node_apply") : source.index("def _assert_env_contract")]
    verify = source[source.index("def _node_verify") : source.index("def _quiesce_and_disable_units")]
    rollback = source[source.index("def _node_rollback") : source.index("def _node_admit_rollback")]
    commit = source[source.index("def _nested_commit_proof_fields") : source.index("def _node_finalize")]
    release = source[source.index("def _node_release_active") : source.index("def _node_status")]

    assert prepare.index("_backup_live_units(") < prepare.index("_write_journal(backup, prepared)")
    assert prepare.index("_prepare_probe_environment(") < prepare.index("_write_journal(backup, prepared)")
    assert prepare.index("_backup_git_metadata(") < prepare.index("_write_journal(backup, prepared)")
    assert apply.index("_normalize_git_metadata(") < apply.index("_archive_repo_bytecode(")
    assert apply.index("_archive_repo_bytecode(") < apply.index("_install_target_units(")
    assert apply.index("_install_target_units(") < apply.index("_atomic_write(ENV_PATH")
    assert apply.index("_atomic_write(ENV_PATH") < apply.index('"status": "applied"')
    assert verify.index("_assert_target_units(") < verify.index("_assert_env_contract(")
    assert verify.index("_assert_repo_bytecode_absent()") < verify.index("_assert_env_contract(")
    assert verify.index("_nested.assert_quarantined(") < verify.index("_assert_env_contract(")
    assert rollback.index("_restore_repo_bytecode(") < rollback.index('"status": "rolled_back_drained"')
    assert rollback.index("_restore_git_metadata(") < rollback.index('"status": "rolled_back_drained"')
    assert '"format": "linas-meta-ha-bootstrap-node-v3"' in source
    assert '"target_unit_contract_sha256"' in commit
    assert '"legacy_bytecode_manifest_sha256"' in commit
    assert '"repo_bytecode_absent": True' in commit
    assert '"nested_runtime_present"' in commit
    assert '"nested_runtime_evidence_sha256"' in commit
    assert '"nested_runtime_quarantined"' in commit
    assert '"nested_runtime_authority_sha256"' in commit
    assert drain.index("_nested.apply_quarantine(") < drain.index('"status": "drained"')
    assert verify.index("_nested.assert_quarantined(") < verify.index("_assert_env_contract(")
    assert rollback.index("_nested.restore_quarantine(") < rollback.index('"status": "rolled_back_drained"')
    assert release.index("_assert_target_units(") < release.rindex("_atomic_write(")
    assert release.index("_assert_repo_bytecode_absent()") < release.rindex("_atomic_write(")


def test_bootstrap_git_metadata_migration_replays_chown_chmod_crash_boundaries(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    backup = tmp_path / "backup"
    backup.mkdir()
    paths = {
        "opt": tmp_path / "opt",
        "repo": tmp_path / "opt/repo",
        "git": tmp_path / "opt/repo/.git",
        "git/config": tmp_path / "opt/repo/.git/config",
    }
    paths["git"].mkdir(parents=True)
    paths["git/config"].write_text("[core]\n", encoding="utf-8")
    entries = sorted(
        [
            {"path": "opt", "type": "directory", "uid": 501, "gid": 20, "mode": 0o755},
            {"path": "repo", "type": "directory", "uid": 501, "gid": 20, "mode": 0o750},
            {"path": "git", "type": "directory", "uid": 501, "gid": 20, "mode": 0o700},
            {"path": "git/config", "type": "file", "uid": 501, "gid": 20, "mode": 0o644},
        ],
        key=lambda entry: os.fsencode(str(entry["path"])),
    )
    (backup / "git-metadata.before.json").write_bytes(bootstrap._canonical({"schema": 1, "entries": entries}) + b"\n")
    state = {str(entry["path"]): dict(entry) for entry in entries}

    def collect() -> list[dict[str, object]]:
        return [dict(state[str(entry["path"])]) for entry in entries]

    reverse_paths = {path: label for label, path in paths.items()}

    def fake_chown(path: Path, uid: int, gid: int, **_kwargs: object) -> None:
        entry = state[reverse_paths[Path(path)]]
        entry["uid"] = uid
        entry["gid"] = gid

    def fake_chmod(path: Path, mode: int, **_kwargs: object) -> None:
        state[reverse_paths[Path(path)]]["mode"] = mode

    monkeypatch.setattr(bootstrap, "_collect_git_metadata", collect)
    monkeypatch.setattr(bootstrap, "_git_control_path", lambda label: paths[label])
    monkeypatch.setattr(bootstrap, "_read_authority_file", lambda path, **_kwargs: path.read_bytes())
    monkeypatch.setattr(bootstrap, "_assert_git_repository_trust", lambda **_kwargs: None)
    monkeypatch.setattr(bootstrap, "_fsync_dir", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(bootstrap.os, "chown", fake_chown)
    monkeypatch.setattr(bootstrap.os, "chmod", fake_chmod)

    expected = {"sha256": bootstrap._digest(entries), "entry_count": len(entries)}
    # Exact state after chown and before chmod on one file.
    state["git/config"].update(uid=0, gid=0, mode=0o644)
    bootstrap._normalize_git_metadata(backup, expected)
    assert all(
        (entry["uid"], entry["gid"], entry["mode"]) == bootstrap._normalized_git_metadata(entry) for entry in collect()
    )

    # Exact reverse state after rollback chown and before rollback chmod.
    state["repo"].update(uid=501, gid=20, mode=0o755)
    bootstrap._restore_git_metadata(backup, expected)
    assert collect() == entries

    state["git/config"]["mode"] = 0o640
    with pytest.raises(RuntimeError, match="unauthenticated partial state"):
        bootstrap._normalize_git_metadata(backup, expected)


def test_bootstrap_runtime_authority_requires_the_frozen_full_peer_bundle() -> None:
    assert bootstrap.RUNTIME_RELEASE_BUNDLE_FILES == {
        "release-manifest.json",
        "wheelhouse.tar",
        "dashboard-build.tar",
        "control-plane.tar",
        "source.bundle",
        bootstrap.PYTHON_RUNTIME_ARTIFACT_NAME,
    }
    source = BOOTSTRAP_PATH.read_text(encoding="utf-8")
    authority = source[source.index("def _runtime_authority") : source.index("def _atomic_write")]
    assert "{entry.name for entry in os.scandir(authority_root)}" in authority
    assert '"plan.json",\n        *RUNTIME_RELEASE_BUNDLE_FILES' in authority
    assert "release.verify_release_bundle(" in authority


@pytest.mark.parametrize(
    ("direction", "failpoint"),
    (("archive", "rename"), ("archive", "chown"), ("rollback", "rename"), ("rollback", "chown")),
)
def test_bootstrap_historical_env_move_adopts_exact_crash_prefixes(
    direction: str,
    failpoint: str,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    live_root = tmp_path / "repo"
    archive_root = tmp_path / "backup/historical-env"
    live_root.mkdir()
    archive_root.mkdir(parents=True)
    original_owner = (1001, 1002)
    archive_owner = (0, 0)
    original_mode = 0o644
    archive_mode = 0o600
    live = live_root / ".env.previous"
    archived = archive_root / ".env.previous"
    source, destination = (live, archived) if direction == "archive" else (archived, live)
    source_owner = original_owner if direction == "archive" else archive_owner
    source_mode = original_mode if direction == "archive" else archive_mode
    target_owner = archive_owner if direction == "archive" else original_owner
    target_mode = archive_mode if direction == "archive" else original_mode
    payload = b"SECRET=value\n"
    source.write_bytes(payload)
    source.chmod(source_mode)
    owners = {source: source_owner}
    original_read = bootstrap._read_regular_any_owner
    real_rename = os.rename
    real_chmod = os.chmod
    injected = False

    def synthetic_read(path: Path):  # type: ignore[no-untyped-def]
        raw, info = original_read(path)
        uid, gid = owners[Path(path)]
        return raw, SimpleNamespace(
            st_uid=uid,
            st_gid=gid,
            st_mode=info.st_mode,
            st_nlink=info.st_nlink,
            st_size=info.st_size,
            st_dev=info.st_dev,
            st_ino=info.st_ino,
        )

    def interrupted_rename(old: Path, new: Path) -> None:
        nonlocal injected
        real_rename(old, new)
        owners[Path(new)] = owners.pop(Path(old))
        if failpoint == "rename" and not injected:
            injected = True
            raise OSError("injected rename acknowledgement loss")

    def interrupted_chown(path: Path, uid: int, gid: int, **_kwargs: object) -> None:
        nonlocal injected
        owners[Path(path)] = (uid, gid)
        if failpoint == "chown" and not injected:
            injected = True
            raise OSError("injected chown acknowledgement loss")

    def portable_chmod(path: Path, mode: int, **_kwargs: object) -> None:
        real_chmod(path, mode)

    monkeypatch.setattr(bootstrap, "_read_regular_any_owner", synthetic_read)
    monkeypatch.setattr(bootstrap, "_fsync_dir", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(bootstrap.os, "rename", interrupted_rename)
    monkeypatch.setattr(bootstrap.os, "chown", interrupted_chown)
    monkeypatch.setattr(bootstrap.os, "chmod", portable_chmod)
    entry = {
        "name": source.name,
        "sha256": bootstrap._digest_bytes(payload),
        "size": len(payload),
        "uid": original_owner[0],
        "gid": original_owner[1],
        "mode": original_mode,
    }
    arguments = {
        "source_owner": source_owner,
        "source_mode": source_mode,
        "target_owner": target_owner,
        "target_mode": target_mode,
        "direction": direction,
    }

    with pytest.raises(OSError, match="acknowledgement loss"):
        bootstrap._transition_historical_env(entry, source, destination, **arguments)
    assert not source.exists() and destination.exists()
    bootstrap._transition_historical_env(entry, source, destination, **arguments)
    assert not source.exists() and destination.read_bytes() == payload
    assert owners[destination] == target_owner
    assert stat.S_IMODE(destination.stat().st_mode) == target_mode


def test_bootstrap_bytecode_archive_and_restore_are_idempotent(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    repository = tmp_path / "repo"
    backup = tmp_path / "backup"
    cache = repository / "pkg/__pycache__"
    cache.mkdir(parents=True)
    backup.mkdir()
    (cache / "module.cpython-313.pyc").write_bytes(b"cached-module")
    (repository / "loose.pyc").write_bytes(b"loose-bytecode")
    ignored = repository / "venv/lib/python3.13/site-packages/pkg/__pycache__"
    ignored.mkdir(parents=True)
    (ignored / "ignored.pyc").write_bytes(b"venv-bytecode")

    def local_atomic(path: Path, payload: bytes, *, mode: int = 0o600, **_kwargs: object) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)
        path.chmod(mode)

    monkeypatch.setattr(bootstrap, "REPO_DIR", repository)
    monkeypatch.setattr(bootstrap, "_secure_dir", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(bootstrap, "_secure_regular", lambda path, **_kwargs: path.lstat())
    monkeypatch.setattr(bootstrap, "_fsync_dir", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(bootstrap, "_fsync_private_tree", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(bootstrap, "_atomic_write", local_atomic)
    monkeypatch.setattr(
        bootstrap,
        "_read_authority_file",
        lambda path, **_kwargs: path.read_bytes(),
    )
    monkeypatch.setattr(
        bootstrap,
        "_read_authority_json",
        lambda path, **_kwargs: (json.loads(path.read_bytes()), path.read_bytes()),
    )
    monkeypatch.setattr(bootstrap.os, "chown", lambda *_args, **_kwargs: None)

    expected = bootstrap._repo_bytecode_manifest()
    assert {entry["path"] for entry in expected if entry["type"] == "file"} == {
        "loose.pyc",
        "pkg/__pycache__/module.cpython-313.pyc",
    }
    bootstrap._archive_repo_bytecode(backup, expected)
    assert bootstrap._repo_bytecode_manifest() == []
    bootstrap._archive_repo_bytecode(backup, expected)
    bootstrap._restore_repo_bytecode(backup, expected)
    assert bootstrap._repo_bytecode_manifest() == expected
    bootstrap._restore_repo_bytecode(backup, expected)
    assert bootstrap._repo_bytecode_manifest() == expected
