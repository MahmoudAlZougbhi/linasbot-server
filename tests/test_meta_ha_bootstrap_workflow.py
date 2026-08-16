"""Closed contracts for the protected, receipt-bound Meta HA bootstrap workflow."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

import pytest
import yaml

from scripts.ha import bootstrap_meta_ha_contract as bootstrap

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/bootstrap-meta-ha.yml"
NODE01_KEY = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIM21a0E0v4XBUVRgai2Z4Zcr+GSDVsztarkAoDRBQ+77"
EXPECTED_INPUTS = {
    "OPERATION",
    "TARGET_SHA",
    "RUNTIME_TRANSACTION_ID",
    "RUNTIME_PLAN_SHA256",
    "RUNTIME_ARTIFACT_ID",
    "RUNTIME_ARTIFACT_API_SHA256",
    "EXPECTED_NODE01_SHA",
    "EXPECTED_NODE02_SHA",
    "EXPECTED_PG_STATE_SHA256",
    "LB_ATTESTATION_BASE64",
    "LB_ATTESTATION_SHA256",
    "LB_READY_PROJECTION_SHA256",
    "BOOTSTRAP_PLAN_SHA256",
    "BOOTSTRAP_TRANSACTION_ID",
    "BOOTSTRAP_JOURNAL_SHA256",
    "CONFIRMATION",
    "PROTECTION_CONFIRM",
}


def test_bootstrap_workflow_is_protected_serialized_and_closed() -> None:
    source = WORKFLOW.read_text(encoding="utf-8")
    parsed = yaml.safe_load(source)
    job = parsed["jobs"]["bootstrap"]
    assert parsed["concurrency"] == {"group": "meta-social-cutover", "cancel-in-progress": False}
    assert job["environment"] == "meta-social-cutover"
    assert "github.ref == 'refs/heads/main'" in str(job["if"])
    assert "appleboy/" not in source
    assert "/usr/bin/ssh" in source
    assert "/usr/bin/scp" in source
    assert "actions/checkout@11d5960a326750d5838078e36cf38b85af677262" in source
    assert "persist-credentials: false" in source
    bridge = ROOT / "scripts/ha/python_runtime_provision_workflow_bootstrap.py"
    bridge_sha = hashlib.sha256(bridge.read_bytes()).hexdigest()
    assert source.count(bridge_sha) == 2
    assert "git fetch" not in source and "git checkout" not in source and "origin/main" not in source
    input_region = source[source.index("    inputs:") : source.index("concurrency:")]
    names = set(re.findall(r"^      ([A-Z][A-Z0-9_]+):$", input_region, flags=re.MULTILINE))
    assert names == EXPECTED_INPUTS
    assert "HOST" not in names and "COMMAND" not in names
    assert "options: [probe, install-lb, plan, apply, rollback-interrupted, recovery-status, recover-decided]" in source


def test_bootstrap_workflow_uses_only_retained_receipt_bound_control() -> None:
    source = WORKFLOW.read_text(encoding="utf-8")
    required = (
        "python_runtime_provision_workflow_bootstrap.py",
        '"$TRUSTED_BRIDGE" bootstrap',
        '"$RUNTIME_TRANSACTION_ID" "$RUNTIME_PLAN_SHA256"',
        '"$RUNTIME_ARTIFACT_ID" "$RUNTIME_ARTIFACT_API_SHA256" "$TARGET_SHA"',
        'run_bootstrap cluster-probe --target-sha "$TARGET_SHA"',
        "run_bootstrap install-lb-ready-attestation",
        'run_bootstrap plan "${COMMON_ARGS[@]}"',
        'run_bootstrap apply "${COMMON_ARGS[@]}"',
        "run_bootstrap recovery-status",
        "run_bootstrap recover-rollback",
        "run_bootstrap recover-decided",
        "--expected-node01-sha",
        "--expected-node02-sha",
        "--peer-host 10.106.0.4",
        "--drain-seconds 30",
    )
    for contract in required:
        assert contract in source
    assert "/opt/linasbot/scripts" not in source
    assert "scripts/ha/bootstrap_meta_ha_contract.py" not in source
    assert "source.bundle" not in source
    assert "deploy_meta_release_ha.sh" not in source
    assert "systemctl" not in source
    assert "git -C" not in source


def test_bootstrap_workflow_attestation_transport_is_data_only_and_digest_bound() -> None:
    source = WORKFLOW.read_text(encoding="utf-8")
    assert "TRANSFER_FILES=(transfer/workflow-bootstrap.py)" in source
    assert 'if [ "$OPERATION" = install-lb ] || [ "$OPERATION" = apply ]; then' in source
    assert "TRANSFER_FILES+=(transfer/lb-attestation.json)" in source
    assert '-- "${TRANSFER_FILES[@]}" "$SSH_USER@$NODE01_HOST:$UPLOAD/"' in source
    assert "base64.b64decode(encoded, validate=True)" in source
    assert "hashlib.sha256(raw).hexdigest() != expected" in source
    assert "duplicate JSON key" in source
    assert "LB attestation is not canonical JSON" in source
    assert 'os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)' in source
    assert "trusted workflow bridge parent is unsafe" in source
    assert "run_bootstrap install-lb-ready-attestation" in source
    assert '<"$TRUSTED_LB"' in source


def test_bootstrap_apply_installs_fresh_attestation_in_the_same_protected_run() -> None:
    source = WORKFLOW.read_text(encoding="utf-8")
    gate = source[source.index('if [ "$OPERATION" = probe ]') : source.index("- name: Stage exact")]
    apply_gate = gate[gate.index('elif [ "$OPERATION" = apply ]') : gate.index("rollback-interrupted")]
    assert '[ -n "$LB_ATTESTATION_BASE64" ]' in apply_gate
    assert '[[ "$LB_ATTESTATION_SHA256" =~ ^[0-9a-f]{64}$ ]]' in apply_gate
    assert '[[ "$LB_READY_PROJECTION_SHA256" =~ ^[0-9a-f]{64}$ ]]' in apply_gate
    script = source[source.index("install_lb_attestation()") :]
    apply_case = script[script.index("apply)") : script.index("rollback-interrupted)")]
    assert apply_case.index("install_lb_attestation") < apply_case.index("run_bootstrap apply")
    assert "INSTALL_CONFIRM=" in script
    assert '--confirm "$INSTALL_CONFIRM"' in script


def test_bootstrap_workflow_pins_fixed_node01_transport_and_leaves_node02_to_coordinator() -> None:
    source = WORKFLOW.read_text(encoding="utf-8")
    assert "NODE01_HOST=139.59.167.62" in source
    assert NODE01_KEY in source
    for name in ("SSH_USER", "SSH_PRIVATE_KEY"):
        assert f"secrets.{name}" in source
    assert "secrets.SSH_HOST" not in source
    assert "SSH_NODE02_USER" not in source
    assert "SSH_NODE02_PRIVATE_KEY" not in source
    assert "NODE02_SSH=(" not in source
    assert "ssh-keyscan" not in source
    assert "StrictHostKeyChecking=yes" in source
    assert "HostKeyAlgorithms=ssh-ed25519" in source
    assert "GlobalKnownHostsFile=/dev/null" in source
    assert "UserKnownHostsFile=$SSH_ROOT/node01.known_hosts" in source
    assert '"${NODE01_SSH[@]}" /usr/bin/true' in source
    assert '"$SSH_USER@$NODE01_HOST"' in source
    assert "--peer-host 10.106.0.4" in source
    helper = (ROOT / "scripts/ha/bootstrap_meta_ha_contract.py").read_text(encoding="utf-8")
    assert '"StrictHostKeyChecking=yes"' in helper
    assert '"private_ip": "10.106.0.4"' in helper
    for forbidden in (
        "StrictHostKeyChecking=no",
        "StrictHostKeyChecking=accept-new",
        "UserKnownHostsFile=/dev/null",
        "curl ",
        "wget ",
    ):
        assert forbidden not in source


def test_bootstrap_workflow_has_both_closed_recovery_lanes() -> None:
    source = WORKFLOW.read_text(encoding="utf-8")
    assert 'elif [ "$OPERATION" = rollback-interrupted ]' in source
    assert '[[ "$BOOTSTRAP_TRANSACTION_ID" =~ ^[0-9a-f]{32}$ ]]' in source
    assert '"ROLLBACK_META_HA_${TX_PREFIX^^}_${PLAN_PREFIX^^}"' in source
    assert 'run_bootstrap recover-rollback --target-sha "$TARGET_SHA"' in source
    assert '--peer-host 10.106.0.4 --confirm "$CONFIRMATION"' in source
    assert 'elif [ "$OPERATION" = recover-decided ]' in source
    assert "^RECOVER_BOOTSTRAP_[0-9A-F]{12}_[0-9A-F]{12}_TO_(COMMIT|ROLLBACK)$" in source
    assert 'run_bootstrap recover-decided --journal-sha256 "$BOOTSTRAP_JOURNAL_SHA256"' in source


def test_initial_operations_require_current_main_but_recovery_accepts_retained_target() -> None:
    source = WORKFLOW.read_text(encoding="utf-8")
    gate = source[source.index('case "$OPERATION" in') : source.index("REQUIRED_REVIEWERS=")]
    assert 'probe | install-lb | plan | apply) [ "$TARGET_SHA" = "$DISPATCH_SHA" ]' in gate
    assert "rollback-interrupted | recovery-status | recover-decided) ;;" in gate
    assert gate.count('"$TARGET_SHA" = "$DISPATCH_SHA"') == 1
    assert '"$RUNTIME_ARTIFACT_ID" "$RUNTIME_ARTIFACT_API_SHA256" "$TARGET_SHA"' in source


def test_cluster_probe_proves_both_nodes_and_emits_only_safe_authorities(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    shared = {"qg_target_sha": "a" * 40, "plan_sha256": "b" * 64}

    def probe(node_id: str, expected_sha: str) -> dict[str, object]:
        return {
            "previous_sha": expected_sha,
            "runtime_authority": {"shared": shared},
            "live_units": {"api": "same"},
            "pg": {"state_sha256": "c" * 64, "row_count": 3},
            "nested_runtime": {"portable_content": "same"},
        }

    monkeypatch.setattr(bootstrap, "_helper_source", lambda: (b"helper", "d" * 64))
    monkeypatch.setattr(bootstrap, "_assert_exact_helper", lambda *_args: None)
    monkeypatch.setattr(bootstrap, "_node_probe", probe)
    monkeypatch.setattr(
        bootstrap,
        "_remote",
        lambda *_args: json.dumps(probe("node02", "e" * 40), separators=(",", ":")),
    )
    monkeypatch.setattr(
        bootstrap._nested_evidence,
        "portable_content_identity",
        lambda value: value["portable_content"],
    )
    args = bootstrap.build_parser().parse_args(
        [
            "cluster-probe",
            "--target-sha",
            "a" * 40,
            "--expected-node01-sha",
            "f" * 40,
            "--expected-node02-sha",
            "e" * 40,
        ]
    )
    assert bootstrap._cluster_probe(args) == 0
    output = capsys.readouterr().out
    assert "target_sha=" + "a" * 40 in output
    assert "node01_previous_sha=" + "f" * 40 in output
    assert "node02_previous_sha=" + "e" * 40 in output
    assert "postgres_state_sha256=" + "c" * 64 in output
    assert "python_runtime_plan_sha256=" + "b" * 64 in output
    assert "row_count" not in output


def test_cluster_probe_fails_closed_on_cross_node_pg_divergence(monkeypatch: pytest.MonkeyPatch) -> None:
    shared = {"qg_target_sha": "a" * 40, "plan_sha256": "b" * 64}
    local = {
        "previous_sha": "f" * 40,
        "runtime_authority": {"shared": shared},
        "live_units": {},
        "pg": {"state_sha256": "c" * 64},
        "nested_runtime": {},
    }
    peer = {**local, "previous_sha": "e" * 40, "pg": {"state_sha256": "d" * 64}}
    monkeypatch.setattr(bootstrap, "_helper_source", lambda: (b"helper", "1" * 64))
    monkeypatch.setattr(bootstrap, "_assert_exact_helper", lambda *_args: None)
    monkeypatch.setattr(bootstrap, "_node_probe", lambda *_args: local)
    monkeypatch.setattr(bootstrap, "_remote", lambda *_args: json.dumps(peer))
    args = bootstrap.build_parser().parse_args(
        [
            "cluster-probe",
            "--target-sha",
            "a" * 40,
            "--expected-node01-sha",
            "f" * 40,
            "--expected-node02-sha",
            "e" * 40,
        ]
    )
    with pytest.raises(RuntimeError, match="identical authoritative PostgreSQL"):
        bootstrap._cluster_probe(args)


def test_cluster_probe_fails_closed_on_full_live_unit_divergence(monkeypatch: pytest.MonkeyPatch) -> None:
    shared = {"qg_target_sha": "a" * 40, "plan_sha256": "b" * 64}
    local = {
        "previous_sha": "f" * 40,
        "runtime_authority": {"shared": shared},
        "live_units": {"linasbot.service": {"sha256": "1" * 64, "size": 10, "mode": 0o644}},
        "pg": {"state_sha256": "c" * 64},
        "nested_runtime": {},
    }
    peer = {
        **local,
        "previous_sha": "e" * 40,
        "live_units": {"linasbot.service": {"sha256": "2" * 64, "size": 10, "mode": 0o644}},
    }
    monkeypatch.setattr(bootstrap, "_helper_source", lambda: (b"helper", "1" * 64))
    monkeypatch.setattr(bootstrap, "_assert_exact_helper", lambda *_args: None)
    monkeypatch.setattr(bootstrap, "_node_probe", lambda *_args: local)
    monkeypatch.setattr(bootstrap, "_remote", lambda *_args: json.dumps(peer))
    args = bootstrap.build_parser().parse_args(
        [
            "cluster-probe",
            "--target-sha",
            "a" * 40,
            "--expected-node01-sha",
            "f" * 40,
            "--expected-node02-sha",
            "e" * 40,
        ]
    )
    with pytest.raises(RuntimeError, match="identical rollback-safe canonical unit baseline"):
        bootstrap._cluster_probe(args)
