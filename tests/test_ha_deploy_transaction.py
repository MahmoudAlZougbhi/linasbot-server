"""Static safety contracts for the owner-approved HA release transaction."""

from __future__ import annotations

import fcntl
import hashlib
import io
import json
import os
import subprocess
import sys
import tarfile
import textwrap
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / "scripts" / "ha" / "deploy_meta_release_ha.sh"
DEPLOY = ROOT / "deploy.sh"
WORKFLOW = ROOT / ".github" / "workflows" / "deploy.yml"
CLUSTER_ENV_HELPER = ROOT / "scripts" / "ha" / "cluster_runtime_env_contract.py"
PRODUCTION_GUARD = ROOT / "scripts" / "ha" / "production_mutation_guard.py"


def _helper() -> str:
    return HELPER.read_text(encoding="utf-8")


def _embedded_python(function_name: str) -> str:
    source = _helper()
    start = source.index(f"{function_name}() {{")
    marker = "<<'PY'\n"
    python_start = source.index(marker, start) + len(marker)
    python_end = source.index("\nPY\n}", python_start)
    return source[python_start:python_end]


def _workflow_python(step_id: str) -> str:
    workflow = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    step = next(value for value in workflow["jobs"]["deploy"]["steps"] if value.get("id") == step_id)
    run = step["run"]
    start = run.index("<<'PY'\n") + len("<<'PY'\n")
    end = run.index("\nPY\n", start)
    return run[start:end]


def test_workflow_runs_only_the_helper_from_the_exact_authorized_blob() -> None:
    source = WORKFLOW.read_text(encoding="utf-8")
    parsed = yaml.safe_load(source)

    assert parsed["concurrency"] == {
        "group": "meta-social-cutover",
        "cancel-in-progress": False,
    }
    job = parsed["jobs"]["deploy"]
    assert job["environment"] == "meta-social-cutover"
    assert job["timeout-minutes"] == 120
    gate_script = job["steps"][0]["run"]
    assert "environments/meta-social-cutover" in gate_script
    assert 'select(.type == "required_reviewers")' in gate_script
    assert '[ "$PREVENT_SELF_REVIEW" = true ]' in gate_script
    deploy_step = next(
        step
        for step in job["steps"]
        if step.get("uses") == "appleboy/ssh-action@7eaf76671a0d7eec5d98ee897acda4f968735a17"
    )
    assert deploy_step["uses"] == ("appleboy/ssh-action@7eaf76671a0d7eec5d98ee897acda4f968735a17")
    script = deploy_step["with"]["script"]
    assert "materialize_recovery_helper" in script
    assert "root_copy_exact" in script
    assert "os.O_EXCL" in script
    assert 'getattr(os, "O_NOFOLLOW", 0)' in script
    assert '"$HELPER_PATH" install-release-bundle-cluster' in script
    assert '"$HELPER_PATH" install-lb-attestation-cluster' in script
    assert '"$HELPER_PATH" orchestrate-confirmed' in script
    assert '"$HELPER_PATH" orchestrate-reconcile' in script
    assert '"$HELPER_PATH" commit-target-confirmed' in script
    assert '"$HELPER_PATH" recover-confirmed' in script
    assert '"$HELPER_PATH" retry-reconcile-confirmed' in script
    assert "git reset --hard" not in script
    assert "/tmp/linasbot-ha-deploy" not in script
    assert "sudo mktemp -d -p /run linasbot-ha-deploy.XXXXXXXX" in script
    assert "os.fchmod(destination_fd, mode)" in script
    assert "os.fchown(destination_fd, 0, 0)" in script
    assert "while view:" in script and "view = view[written:]" in script
    assert 'digest.hexdigest() != expected_sha' in script
    assert 'sudo unlink "$HELPER_PATH"' in script


def test_standalone_deploy_entrypoint_is_fail_closed_before_any_mutation() -> None:
    source = DEPLOY.read_text(encoding="utf-8")
    result = subprocess.run(
        ["/bin/bash", str(DEPLOY)],
        cwd=ROOT,
        text=True,
        capture_output=True,
        timeout=5,
        check=False,
    )
    assert result.returncode == 2
    assert "manual protected .github/workflows/deploy.yml" in result.stderr
    for forbidden in ("git ", "sudo ", "mktemp", "systemctl", "deploy_meta_release_ha.sh"):
        assert forbidden not in source


def test_workflow_yaml_has_no_duplicate_mapping_keys() -> None:
    document = yaml.compose(WORKFLOW.read_text(encoding="utf-8"))
    assert document is not None

    def visit(node: yaml.Node) -> None:
        if isinstance(node, yaml.MappingNode):
            keys = [key.value for key, _value in node.value]
            assert len(keys) == len(set(keys)), f"duplicate YAML mapping key: {keys}"
            for key, value in node.value:
                visit(key)
                visit(value)
        elif isinstance(node, yaml.SequenceNode):
            for value in node.value:
                visit(value)

    visit(document)


def test_workflow_authenticates_inline_authorities_before_loading_release_code(
    tmp_path: Path,
) -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")
    release_python = _workflow_python("release_contract")
    lb_python = _workflow_python("lb_contract")
    compile(release_python, "deploy-release-inline.py", "exec")
    compile(lb_python, "deploy-lb-inline.py", "exec")

    assert "actions/checkout" not in workflow
    assert "$GITHUB_WORKSPACE/scripts/ha" not in workflow
    assert "spec_from_file_location" not in lb_python
    assert "manage_do_lb_ready_healthcheck" not in lb_python
    assert release_python.index("hashlib.sha256(manifest_raw).hexdigest()") < release_python.index(
        "json.loads(manifest_raw.decode"
    )
    assert release_python.index("archive_digest.hexdigest()") < release_python.index(
        "sys.path.insert(0, str(bootstrap))"
    )

    checkout = tmp_path / "checkout"
    malicious = checkout / "scripts" / "ha"
    malicious.mkdir(parents=True)
    sentinel = tmp_path / "checkout-module-executed"
    side_effect = f"from pathlib import Path\nPath({str(sentinel)!r}).write_text('executed')\n"
    (malicious / "release_artifact_contract.py").write_text(side_effect, encoding="utf-8")
    (malicious / "manage_do_lb_ready_healthcheck.py").write_text(side_effect, encoding="utf-8")

    bundle = tmp_path / "bundle"
    bundle.mkdir()
    target = "a" * 40
    repository = "MahmoudAlZougbhi/linasbot-server"
    manifest = {
        "schema": "linasbot-release-manifest-v1",
        "repository": repository,
        "workflow_path": ".github/workflows/quality-gates.yml",
        "workflow_ref": (
            f"{repository}/.github/workflows/quality-gates.yml@refs/heads/main"
        ),
        "run_id": 17,
        "run_attempt": 2,
        "target_sha": target,
        "source_locks": {},
        "toolchains": {},
        "payloads": {
            "wheelhouse": {},
            "dashboard": {},
            "control_plane": {
                "archive": "control-plane.tar",
                "archive_sha256": "0" * 64,
                "tree_sha256": "1" * 64,
                "file_count": 1,
                "total_size": 1,
            },
            "source_bundle": {},
            "python_runtime": {},
        },
    }
    manifest_raw = (
        json.dumps(manifest, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode()
    (bundle / "release-manifest.json").write_bytes(manifest_raw)
    for name in (
        "wheelhouse.tar",
        "dashboard-build.tar",
        "control-plane.tar",
        "source.bundle",
        "cpython-3.13.15+20260814-x86_64-unknown-linux-gnu-install_only_stripped.tar.gz",
    ):
        (bundle / name).write_bytes(b"x")
    result = subprocess.run(
        [
            sys.executable,
            "-B",
            "-I",
            "-S",
            "-",
            str(bundle),
            str(tmp_path / "bootstrap-control"),
            str(tmp_path / "control"),
            target,
            "17",
            "2",
            hashlib.sha256(manifest_raw).hexdigest(),
            repository,
        ],
        cwd=checkout,
        input=release_python,
        text=True,
        capture_output=True,
        timeout=10,
        check=False,
    )
    assert result.returncode != 0
    assert "control-plane archive digest changed" in result.stderr
    assert not sentinel.exists()

    lb_result = subprocess.run(
        [
            sys.executable,
            "-B",
            "-I",
            "-S",
            "-",
            str(tmp_path / "lb-attestation.json"),
            "2" * 64,
            "3" * 64,
        ],
        cwd=checkout,
        env={**os.environ, "LB_ATTESTATION_BASE64": "not-strict-base64"},
        input=lb_python,
        text=True,
        capture_output=True,
        timeout=10,
        check=False,
    )
    assert lb_result.returncode != 0
    assert "strict base64" in lb_result.stderr
    assert not sentinel.exists()


def test_recovery_helper_publication_writes_all_bytes_after_short_writes() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")
    marker = workflow.index("view = memoryview(helper_bytes)", workflow.index("materialize_recovery_helper"))
    start = workflow.rfind("\n", 0, marker) + 1
    end = workflow.index("os.fsync(descriptor)", marker)
    exact_loop = textwrap.dedent(workflow[start:end])
    published = bytearray()

    class PartialWriteOS:
        @staticmethod
        def write(_descriptor: int, view: memoryview) -> int:
            count = min(3, len(view))
            published.extend(view[:count])
            return count

    helper_bytes = b"exact-artifact-helper-with-forced-short-writes"
    exec(exact_loop, {"helper_bytes": helper_bytes, "descriptor": 7, "os": PartialWriteOS})
    assert bytes(published) == helper_bytes


def test_provisioner_v2_wheelhouse_receipts_are_consumed_exactly(tmp_path: Path) -> None:
    from scripts.ha import python_runtime_provision_contract as provision

    manifest = {
        "schema": "linasbot-release-manifest-v1",
        "repository": provision.EXPECTED_REPOSITORY,
        "workflow_path": ".github/workflows/quality-gates.yml",
        "workflow_ref": provision.EXPECTED_WORKFLOW_REF,
        "run_id": 101,
        "run_attempt": 2,
        "target_sha": "a" * 40,
        "source_locks": {},
        "toolchains": {},
        "payloads": {
            "wheelhouse": {
                "archive": "wheelhouse.tar",
                "archive_sha256": "3" * 64,
                "tree_sha256": "4" * 64,
                "file_count": 78,
                "total_size": 123_456,
            },
            "dashboard": {},
            "control_plane": {},
            "source_bundle": {},
            "python_runtime": {},
        },
    }
    manifest_bytes = provision.canonical(manifest)
    plan = {
        "schema": 1,
        "format": provision.PLAN_FORMAT,
        "transaction_id": "",
        "required_nodes": list(provision.NODES),
        "runtime_path": str(provision.RUNTIME_PATH),
        "artifact_name": provision.release.PYTHON_RUNTIME_NAME,
        "artifact_sha256": provision.release.PYTHON_RUNTIME_SHA256,
        "runtime_tree_sha256": provision.release.PYTHON_RUNTIME_TREE_SHA256,
        "python_executable_sha256": provision.release.PYTHON_EXECUTABLE_SHA256,
        "libpython_sha256": provision.release.PYTHON_LIBPYTHON_SHA256,
        "control_plane_archive_sha256": "1" * 64,
        "control_plane_tree_sha256": "2" * 64,
        "wheelhouse_archive_sha256": "3" * 64,
        "wheelhouse_tree_sha256": "4" * 64,
        "wheelhouse_file_count": 78,
        "wheelhouse_total_size": 123_456,
        "runtime_archive_size": 1_000_000,
        "qg_repository": provision.EXPECTED_REPOSITORY,
        "qg_workflow_ref": provision.EXPECTED_WORKFLOW_REF,
        "qg_run_id": 101,
        "qg_run_attempt": 2,
        "qg_target_sha": "a" * 40,
        "qg_artifact_id": 202,
        "qg_artifact_api_sha256": "5" * 64,
        "qg_manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
    }
    plan["transaction_id"] = f"pyr_{provision.digest_json(plan)[:32]}"
    plan_sha = provision.digest_json(plan)
    node01 = provision.node_receipt(plan, plan_sha, "node01")
    node02 = provision.node_receipt(plan, plan_sha, "node02")
    node01_bytes = provision.canonical(node01)
    cluster = provision.cluster_receipt(
        plan,
        plan_sha,
        {
            "node01": hashlib.sha256(node01_bytes).hexdigest(),
            "node02": hashlib.sha256(provision.canonical(node02)).hexdigest(),
        },
    )
    local_path = tmp_path / "python-runtime-provisioned.json"
    cluster_path = tmp_path / "python-runtime-cluster.json"
    state_root = tmp_path / "state"
    authority = state_root / "python-runtime-transactions" / plan["transaction_id"] / "authority"
    for directory in (
        state_root,
        state_root / "python-runtime-transactions",
        authority.parent,
        authority,
    ):
        directory.mkdir(exist_ok=True)
        directory.chmod(0o700)
    (authority / "plan.json").write_bytes(provision.canonical(plan))
    (authority / "release-manifest.json").write_bytes(manifest_bytes)
    (authority / "plan.json").chmod(0o600)
    (authority / "release-manifest.json").chmod(0o600)

    def publish(local: dict[str, object], shared: dict[str, object]) -> None:
        local_path.write_bytes(provision.canonical(local))
        cluster_path.write_bytes(provision.canonical(shared))
        local_path.chmod(0o600)
        cluster_path.chmod(0o600)

    schema_python = _embedded_python("assert_python_runtime_contract")
    schema_python = schema_python[: schema_python.index("\ndef tree_digest")]
    schema_python = schema_python.replace(".st_uid != 0", f".st_uid != {os.geteuid()}").replace(
        ".st_gid != 0", f".st_gid != {os.getegid()}"
    )
    schema_args = [
        str(local_path),
        str(cluster_path),
        "node01",
        str(provision.RUNTIME_PATH),
        str(provision.RUNTIME_PATH / "bin/python3.13"),
        provision.release.PYTHON_VERSION,
        provision.release.PYTHON_CACHE_TAG,
        "cpython-313-x86_64-linux-gnu",
        provision.release.PYTHON_MACHINE,
        provision.release.PIP_VERSION,
        provision.release.PYTHON_RUNTIME_NAME,
        provision.release.PYTHON_RUNTIME_SHA256,
        provision.CPYTHON_SOURCE_SHA256,
        provision.release.PYTHON_EXECUTABLE_SHA256,
        provision.release.PYTHON_RUNTIME_TREE_SHA256,
        str(state_root),
    ]

    def validate_schema() -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, "-B", "-I", "-S", "-c", schema_python, *schema_args],
            text=True,
            capture_output=True,
            timeout=10,
            check=False,
        )

    publish(node01, cluster)
    accepted = validate_schema()
    assert accepted.returncode == 0, accepted.stderr

    missing = dict(node01)
    missing.pop("wheelhouse_archive_sha256")
    publish(missing, cluster)
    rejected_missing = validate_schema()
    assert rejected_missing.returncode != 0
    assert "schema is not closed" in rejected_missing.stderr

    extra_cluster = dict(cluster)
    extra_cluster["wheelhouse_unreviewed"] = "7" * 64
    publish(node01, extra_cluster)
    rejected_extra = validate_schema()
    assert rejected_extra.returncode != 0
    assert "schema is not closed" in rejected_extra.stderr

    mutated_node = dict(node01)
    mutated_cluster = dict(cluster)
    mutated_node["wheelhouse_tree_sha256"] = "7" * 64
    mutated_cluster["wheelhouse_tree_sha256"] = "7" * 64
    mutated_node_bytes = provision.canonical(mutated_node)
    mutated_cluster["node_receipt_sha256"] = {
        **cluster["node_receipt_sha256"],
        "node01": hashlib.sha256(mutated_node_bytes).hexdigest(),
    }
    publish(mutated_node, mutated_cluster)
    rejected_manifest_mismatch = validate_schema()
    assert rejected_manifest_mismatch.returncode != 0
    assert "retained Python runtime plan differs from its receipt" in rejected_manifest_mismatch.stderr


def test_both_nodes_preflight_before_any_stage_reset_restart_or_marker() -> None:
    source = _helper()
    orchestrate = source[source.index("orchestrate() {") :]
    local_preflight = orchestrate.index('local_preflight="$(node_preflight')
    peer_preflight = orchestrate.index('peer_preflight="$(')
    transaction_start = orchestrate.index("transaction_started=1")
    assert orchestrate.index('remote_node "$peer_host" preflight', peer_preflight) < transaction_start
    peer_marker = orchestrate.index('remote_node "$peer_host" mark-maintenance')
    peer_stage = orchestrate.index('remote_node "$peer_host" stage')
    first_activate = orchestrate.index('remote_node "$peer_host" activate')

    assert local_preflight < peer_preflight < transaction_start
    assert orchestrate.rindex("set +e", 0, local_preflight) < local_preflight
    assert orchestrate.index("local_preflight_rc=$?", local_preflight) < peer_preflight
    assert orchestrate.index("peer_preflight_rc=$?", peer_preflight) < transaction_start
    assert "both-node preflight failed" in orchestrate
    assert transaction_start < peer_marker < peer_stage < first_activate
    assert orchestrate.index('test "$previous_sha" = "$peer_previous_sha"') < transaction_start


def test_peer_is_staged_and_activated_drained_before_node01_cutover() -> None:
    source = _helper()
    orchestrate = source[source.index("orchestrate() {") :]
    peer_marker = orchestrate.index('remote_node "$peer_host" mark-maintenance')
    peer_stage = orchestrate.index('remote_node "$peer_host" stage')
    local_stage = orchestrate.index('backup_live_node "$target_sha" "$previous_sha" "$tx_dir"')
    peer_activate = orchestrate.index('remote_node "$peer_host" activate')
    local_marker = orchestrate.index("node_mark_maintenance", peer_activate)
    local_activate = orchestrate.index('node_activate "$target_sha"')
    peer_parity = orchestrate.index('remote_node "$peer_host" assert-drained "$target_sha"', local_activate)
    local_parity = orchestrate.index('node_assert_release_drained "$target_sha"', local_activate)
    awaiting_fresh_lb = orchestrate.index('update_deploy_journal "target-parity-awaiting-fresh-lb"')

    assert peer_marker < peer_stage < local_stage < peer_activate
    assert peer_activate < local_marker < local_activate
    assert local_activate < peer_parity < local_parity < awaiting_fresh_lb
    assert 'remote_node "$peer_host" clear-maintenance' not in orchestrate[awaiting_fresh_lb:]


def test_owner_gate_fixed_membership_and_peer_not_self_are_fail_closed() -> None:
    source = _helper()
    for contract in (
        "META_HA_LB_READY_HEALTHCHECK_APPROVED",
        "META_HA_LB_DRAIN_SECONDS",
        "LINAS_MAINTENANCE_DRAIN_FILE",
        "maintenance marker path must be the canonical persistent Meta HA marker",
        "/var/lib/linasbot/meta-ha/maintenance",
        "/run/linasbot-maintenance",
        "if not 30 <= drain <= 300:",
        "META_DELETION_NODE_ID",
        "META_DELETION_REQUIRED_NODES",
        'required != ["node01", "node02"]',
        "HA peer resolves to this node",
        "legacy linas_ai_bot service is active or enabled",
        "legacy port 8000 listener is active",
        "legacy nested runtime still exists",
        "ROLLBACK PARITY IS UNCERTAIN; maintenance remains fail-closed",
    ):
        assert contract in source


def test_initial_release_drain_does_not_require_target_code_to_be_live() -> None:
    source = _helper()
    preflight = source[source.index("node_preflight() {") : source.index("capture_service_state() {")]
    mark = source[source.index("install_nginx_maintenance_override() {") : source.index("node_ensure_maintenance() {")]

    # Preflight proves the currently running release and separately validates the
    # target Git object; it never asks the current runtime to claim target_sha.
    assert "assert_unit_contract linasbot" in preflight
    assert "assert_ready" in preflight
    assert "assert_lb_ready" in preflight
    assert 'assert_target_object "$target_sha"' in preflight
    assert "verify_meta_release_ha.sh" not in preflight

    # The first marker-aware deploy can drain an older runtime through a private,
    # recoverable nginx override on the owner-approved /api/ready path.
    assert "linasbot-ha-maintenance-override" in mark
    assert "maintenance-nginx.conf" in mark
    assert 'copy_private_file_durable "$live_config" "$backup"' in mark
    assert "return 503" in mark
    assert "restore_nginx_maintenance_override" in mark


def test_rollback_keeps_marker_unaware_old_api_stopped_until_parity() -> None:
    source = _helper()
    rollback = source[source.index("rollback_impl() {") : source.index("node_activate() {")]
    ensure = source[source.index("node_ensure_maintenance() {") : source.index("node_clear_maintenance() {")]

    nginx_restore = rollback.index('tar --numeric-owner -C / -xpf "$tx_dir/nginx.tar"')
    enforce_drain = rollback.index('node_ensure_maintenance "$tx_dir"', nginx_restore)
    assert nginx_restore < enforce_drain
    assert 'restore_service_state "$tx_dir"' not in rollback
    assert "assert_direct_port_unavailable" in rollback
    assert "! assert_direct_maintenance_readiness" in ensure
    assert "stop_runtime" in ensure
    assert 'install_nginx_maintenance_override "$tx_dir"' in ensure
    assert ensure.rindex("node_assert_runtime_drained") > ensure.index('install_nginx_maintenance_override "$tx_dir"')


def test_live_venv_is_never_removed_and_mutation_requires_maintenance() -> None:
    source = _helper()
    deploy = DEPLOY.read_text(encoding="utf-8")

    assert "rm -rf venv" not in source
    assert "rm -rf venv" not in deploy
    assert 'assert_secure_maintenance_marker "$MAINTENANCE_FILE"' in source
    assert 'assert_secure_maintenance_marker "$VOLATILE_MAINTENANCE_FILE"' in source
    assert source.index("stop_runtime\n") < source.index(
        'atomic_sibling_move "$REPO_DIR/venv" "$sibling_dir/live-venv"'
    )
    assert source.index('atomic_sibling_move "$REPO_DIR/venv" "$sibling_dir/live-venv"') < source.index(
        'git -C "$REPO_DIR" reset --hard "$target_sha"'
    )


def test_untracked_runtime_is_archived_and_rejected_at_every_runtime_boundary() -> None:
    source = _helper()
    preflight = source[source.index("node_preflight() {") : source.index("capture_service_state() {")]
    activate = source[source.index("activate_impl() {") : source.index("start_saved_runtime_disabled() {")]
    rollback = source[source.index("rollback_impl() {") : source.index("node_activate() {")]
    admission = source[source.index("node_clear_maintenance() {") : source.index("node_assert_release_drained() {")]

    assert 'audit_untracked_runtime "$BACKUP_ROOT/untracked-audit"' in preflight
    assert "preflight-${expected_node_id}" in preflight
    assert 'audit_untracked_runtime "$tx_dir" "pre-target-start"' in activate
    assert rollback.count('audit_untracked_runtime "$tx_dir" "pre-rollback-start"') == 2
    assert 'audit_untracked_runtime "$tx_dir" "pre-admission"' in admission
    assert 'git -C "$REPO_DIR" ls-files --others --exclude-standard' in source
    assert 'git -C "$REPO_DIR" ls-files --others --ignored --exclude-standard' in source
    assert "tests/__init__.py" not in source  # generic policy, not a one-off deletion
    assert "runtime-files.tar" in source
    assert 'chmod 0600 "$archive_path"' in source
    assert "preserved untracked runtime candidates without deletion" in source
    assert "target-owned runtime path before exact blob replacement" in source
    assert "target-untracked runtime blockers require owner remediation" in source
    assert all(not line.lstrip().startswith("rm ") for line in source.splitlines())


def test_known_live_preflight_blockers_are_encoded_fail_closed() -> None:
    source = _helper()
    assert 'test "$previous_sha" = "$peer_previous_sha"' in source
    assert "nodes do not share one previous SHA" in source
    assert "canonical .env must be root:root mode 0600" in source
    assert "legacy linas_ai_bot service is active or enabled" in source
    assert "legacy port 8000 listener is active" in source
    assert "untracked runtime blocker" in source


def test_live_runtime_moves_are_atomic_opt_siblings_with_verified_archive_fallback() -> None:
    source = _helper()
    assert "/opt/.linasbot-ha-rollback-%s" in source
    assert "stat -c '%d' \"$REPO_DIR\"" in source
    assert "atomic move would cross filesystem devices" in source
    assert 'mv -T -- "$source" "$destination"' in source
    assert 'atomic_sibling_move "$REPO_DIR/venv" "$sibling_dir/live-venv"' in source
    assert 'atomic_sibling_move "$sibling_dir/live-venv" "$REPO_DIR/venv"' in source
    assert '"$REPO_DIR/data" "$sibling_dir/failed-data-$generation_label"' in source
    assert 'mv "$REPO_DIR/venv" "$tx_dir/' not in source
    assert 'mv "$REPO_DIR/dashboard/build" "$tx_dir/' not in source
    assert "verify_archive" in source
    assert "rollback archive integrity check failed" in source
    assert 'verify_archive "$tx_dir/venv.tar"' in source
    assert 'verify_archive "$tx_dir/dashboard-build.tar"' in source


def test_recoverable_sensitive_backups_are_private_and_rollback_is_automatic() -> None:
    source = _helper()
    for archive in (
        "venv.tar",
        "data-pre-drain.tar",
        "data-quiesced.tar",
        "dashboard-build.tar",
        "nginx.tar",
        "systemd.tar",
    ):
        assert archive in source
    assert 'chmod 0600 "$archive"' in source
    assert 'chmod 0700 "$BACKUP_ROOT"' in source
    assert "rollback_transaction" in source
    assert "trap on_exit EXIT" in source
    assert "trap 'exit 130' INT" in source
    assert "trap 'exit 143' TERM" in source
    assert 'rollback_impl "$previous_sha" "$tx_dir"' in source
    assert 'remote_node "$peer_host" rollback "$peer_previous_sha" "$tx_dir"' in source


def test_traffic_is_reenabled_only_after_same_target_parity_while_drained() -> None:
    source = _helper()
    orchestrate = source[source.index("orchestrate() {") : source.index('case "${1:-}" in')]
    commit = source[source.index("commit_target_deployment() {") : source.index("orchestrate() {")]
    peer_drained = orchestrate.rindex('remote_node "$peer_host" assert-drained "$target_sha"')
    local_drained = orchestrate.rindex('node_assert_release_drained "$target_sha"')
    awaiting = orchestrate.index('update_deploy_journal "target-parity-awaiting-fresh-lb"')
    assert peer_drained < local_drained < awaiting
    assert "recover-admit" not in orchestrate

    fresh = commit.index('update_commit_journal "commit-lb-attested" rollback')
    reparity = commit.index('node_assert_release_drained "$target_sha"', fresh)
    decision = commit.index('update_commit_journal "target-parity-proven" commit', reparity)
    peer_admit = commit.index('remote_node "$peer_host" recover-admit "$target_sha"', decision)
    local_admit = commit.index('node_recover_admit "$target_sha"', peer_admit)
    cluster_verify = commit.index('verify_meta_release_ha.sh" "$target_sha" cluster', local_admit)
    assert fresh < reparity < decision < peer_admit < local_admit < cluster_verify


def test_direct_port_8003_is_the_real_drain_boundary_for_marker_unaware_releases() -> None:
    source = _helper()
    mark = source[source.index("node_mark_maintenance() {") : source.index("node_ensure_maintenance() {")]
    ensure = source[source.index("node_ensure_maintenance() {") : source.index("node_clear_maintenance() {")]
    orchestrate = source[source.index("orchestrate() {") :]

    assert mark.index('install_nginx_maintenance_override "$tx_dir"') < mark.index(
        "if ! assert_direct_maintenance_readiness"
    )
    assert mark.index("if ! assert_direct_maintenance_readiness") < mark.index("stop_runtime")
    assert "direct LB port 8003" in mark
    assert "assert_direct_port_unavailable" in ensure
    peer_mark = orchestrate.index('remote_node "$peer_host" mark-maintenance')
    peer_sleep = orchestrate.index('sleep "$drain_seconds"', peer_mark)
    peer_stage = orchestrate.index('remote_node "$peer_host" stage', peer_sleep)
    assert orchestrate.index('node_assert_release_ready "$previous_sha"', peer_mark) < peer_sleep
    assert orchestrate.index("assert_public_ready", peer_mark) < peer_sleep < peer_stage


def test_persistent_markers_and_systemd_boot_guards_survive_reboot_fail_closed() -> None:
    source = _helper()
    assert "META_HA_STATE_ROOT=/var/lib/linasbot/meta-ha" in source
    assert "MAINTENANCE_FILE=$META_HA_STATE_ROOT/maintenance" in source
    assert "VOLATILE_MAINTENANCE_FILE=/run/linasbot-maintenance" in source
    assert "DEPLOY_NODE_ACTIVE_FILE=$META_HA_STATE_ROOT/deploy-node.active" in source
    assert "ConditionPathExists=!/var/lib/linasbot/meta-ha/deploy-node.active" in source
    assert "ConditionPathExists=!/var/lib/linasbot/meta-ha/maintenance" in source
    assert "/etc/systemd/system/linasbot.service.d/90-meta-ha-maintenance.conf" in source
    assert "/etc/systemd/system/linasbot-worker@.service.d/90-meta-ha-maintenance.conf" in source
    mark = source[source.index("node_mark_maintenance() {") : source.index("node_ensure_maintenance() {")]
    assert mark.index("install_maintenance_boot_guard") < mark.index("arm_maintenance_markers")
    assert "Meta HA bootstrap transaction is active" in source
    assert "interrupted Meta HA bootstrap coordinator decision requires confirmed recovery" in source
    assert "Meta environment synchronization journal is active" in source


def test_guard_publication_and_rollback_admission_are_reboot_safe() -> None:
    source = _helper()
    disable = source[source.index("disable_runtime_autostart() {") : source.index("archive_path() {")]
    mark = source[source.index("node_mark_maintenance() {") : source.index("node_ensure_maintenance() {")]
    ensure = source[source.index("node_ensure_maintenance() {") : source.index("node_assert_runtime_drained() {")]
    clear = source[source.index("node_clear_maintenance() {") : source.index("node_assert_release_drained() {")]

    assert mark.index('capture_service_state "$tx_dir/predrain-service-state"') < mark.index(
        'arm_deploy_node_sentinel "$tx_dir"'
    )
    assert mark.index('install_maintenance_boot_guard "$tx_dir"') < mark.index(
        'arm_deploy_node_sentinel "$tx_dir"'
    )
    assert mark.index('arm_deploy_node_sentinel "$tx_dir"') < mark.index("disable_runtime_autostart")
    assert mark.index('install_maintenance_boot_guard "$tx_dir"') < mark.index("arm_maintenance_markers")
    assert ensure.index('install_maintenance_boot_guard "$tx_dir"') < ensure.index(
        'arm_deploy_node_sentinel "$tx_dir"'
    )
    assert ensure.index('arm_deploy_node_sentinel "$tx_dir"') < ensure.index("disable_runtime_autostart")
    assert ensure.index('install_maintenance_boot_guard "$tx_dir"') < ensure.index("arm_maintenance_markers")
    assert 'systemctl disable "${units[@]}"' in disable
    assert 'systemctl disable linasbot.service' not in disable

    capture = source[source.index("capture_service_state() {") : source.index("archive_path() {")]
    durable_dir = source[
        source.index("ensure_transaction_dir_durable() {") : source.index("python_bin() {")
    ]
    assert 'test "$(realpath -e /var/backups)" = /var/backups' in durable_dir
    assert 'test "$(realpath -e "$BACKUP_ROOT")" = "$BACKUP_ROOT"' in durable_dir
    assert 'test "$(realpath -e "$tx_dir")" = "$tx_dir"' in durable_dir
    assert 'run_system_python_control - "$tx_dir" "$BACKUP_ROOT" /var/backups' in durable_dir
    assert "os.fsync(descriptor)" in durable_dir
    assert mark.index('ensure_transaction_dir_durable "$tx_dir"') < mark.index(
        'capture_service_state "$tx_dir/predrain-service-state"'
    )
    assert ensure.index('ensure_transaction_dir_durable "$tx_dir"') < ensure.index(
        'validate_service_state_file "$tx_dir/predrain-service-state"'
    )
    assert "tempfile.mkstemp" in capture
    assert "os.fsync(fd)" in capture
    assert "os.replace(temporary, path)" in capture
    assert "os.fsync(directory)" in capture
    assert "validate_service_state_file" in capture
    assert "service rollback inventory is outside its closed schema" in capture
    assert mark.index("validate_service_state_file") < mark.index("disable_runtime_autostart")

    guard_publish = source[
        source.index("publish_boot_guard_atomic() {") : source.index(
            "install_maintenance_boot_guard() {"
        )
    ]
    assert "tempfile.mkstemp" in guard_publish
    assert "os.fsync(descriptor)" in guard_publish
    assert "os.replace(temporary, destination)" in guard_publish
    assert "os.fsync(directory)" in guard_publish
    assert "expected.startswith(current)" in guard_publish
    assert "unknown maintenance boot guard already exists" in guard_publish
    install_guard = source[
        source.index("install_maintenance_boot_guard() {") : source.index(
            "assert_maintenance_boot_guard_loaded() {"
        )
    ]
    assert 'publish_boot_guard_atomic "$candidate" "$destination"' in install_guard
    assert 'install -o root -g root -m 0644 "$candidate" "$destination"' not in install_guard

    # Both guard files are loaded before the sentinel can ever become durable,
    # so every disable-prefix/reboot boundary is fail-closed.
    sentinel_boundary = mark.index('arm_deploy_node_sentinel "$tx_dir"')
    disable_boundary = mark.index("disable_runtime_autostart")
    assert sentinel_boundary < disable_boundary
    prefix_after_sentinel = mark[sentinel_boundary:disable_boundary]
    for mutation in (
        "systemctl disable",
        "systemctl stop",
        "arm_maintenance_markers",
        "install_nginx_maintenance_override",
    ):
        assert mutation not in prefix_after_sentinel
    assert ensure.index('validate_service_state_file "$tx_dir/predrain-service-state"') < ensure.index(
        'arm_deploy_node_sentinel "$tx_dir"'
    )
    sentinel_recovery = ensure[ensure.index('if [ -e "$DEPLOY_NODE_ACTIVE_FILE"') :]
    assert 'if ! maintenance_boot_guard_is_loaded "$tx_dir"' in sentinel_recovery
    assert sentinel_recovery.index("verify_runtime_autostart_disabled") < sentinel_recovery.index(
        'install_maintenance_boot_guard "$tx_dir"'
    )
    assert sentinel_recovery.index("assert_direct_port_unavailable") < sentinel_recovery.index(
        'install_maintenance_boot_guard "$tx_dir"'
    )

    rollback = clear[clear.index("\n  else\n    test -z") :]
    disable = rollback.index("disable_runtime_autostart")
    remove_guard = rollback.index('remove_maintenance_boot_guard "$tx_dir"')
    start_disabled = rollback.index('start_saved_runtime_disabled "$rollback_state_file"')
    clear_marker = rollback.index("clear_maintenance_markers_durable")
    restore_enable = rollback.index('restore_saved_autostart "$rollback_state_file"')
    proof = rollback.index('write_admission_proof "$tx_dir" "$admission_sha"')
    sentinel_clear = rollback.index('clear_deploy_node_sentinel "$tx_dir"')
    saved_start = source[
        source.index("start_saved_runtime_disabled() {") : source.index("rollback_impl() {")
    ]
    assert 'install_maintenance_boot_guard "$tx_dir"' in saved_start
    assert disable < remove_guard < start_disabled < restore_enable < clear_marker
    assert clear_marker < proof < sentinel_clear
    recover = source[source.index("node_recover_admit() {") : source.index("node_recover_rollback() {")]
    assert 'admission_proof_is_exact "$tx_dir" "$expected_sha"' in recover
    assert recover.index('assert_deploy_node_sentinel "$tx_dir"') < recover.index(
        'clear_deploy_node_sentinel "$tx_dir"'
    )


def test_per_node_deploy_sentinel_is_transaction_bound_and_last_to_leave() -> None:
    source = _helper()
    sentinel = source[
        source.index("assert_deploy_node_sentinel() {") : source.index("admission_proof_is_exact() {")
    ]
    drained = source[source.index("node_assert_runtime_drained() {") : source.index("start_admitted_target_runtime() {")]
    clear = source[source.index("node_clear_maintenance() {") : source.index("node_assert_release_drained() {")]
    ready = source[source.index("node_assert_release_ready() {") : source.index("node_assert_exact_head() {")]
    dispatch = source[source.index("node_dispatch() {") : source.index("reject_self_peer() {")]

    assert 'test "$(stat -c \'%u:%g:%a\' "$DEPLOY_NODE_ACTIVE_FILE")" = "0:0:600"' in sentinel
    assert 'test "$(<"$DEPLOY_NODE_ACTIVE_FILE")" = "$tx_dir"' in sentinel
    assert "os.fchown(fd, 0, 0)" in sentinel
    assert "os.replace(temporary, path)" in sentinel
    assert 'test "$(stat -c \'%h\' "$DEPLOY_NODE_ACTIVE_FILE")" = "1"' in sentinel
    assert 'assert_deploy_node_sentinel "$tx_dir"' in drained
    assert clear.index('assert_deploy_node_sentinel "$tx_dir"') < clear.index(
        'remove_maintenance_boot_guard "$tx_dir"'
    )
    assert clear.index('write_admission_proof "$tx_dir" "$admission_sha"') < clear.index(
        'clear_deploy_node_sentinel "$tx_dir"'
    )
    assert 'assert_path_absent "$DEPLOY_NODE_ACTIVE_FILE"' in ready
    assert 'validate_tx_dir "${2:-}"' in dispatch
    assert 'node_assert_release_drained "$1" "$2"' in dispatch


def test_target_verification_keeps_boot_guard_and_workers_offline_until_parity() -> None:
    source = _helper()
    verify_start = source[source.index("start_target_runtime() {") : source.index("activate_impl() {")]
    final_start = source[
        source.index("start_admitted_target_runtime() {") : source.index("enable_admitted_target_autostart() {")
    ]
    enable_last = source[
        source.index("enable_admitted_target_autostart() {") : source.index("node_clear_maintenance() {")
    ]
    clear = source[source.index("node_clear_maintenance() {") : source.index("node_assert_release_drained() {")]
    orchestrate = source[source.index("orchestrate() {") : source.index('case "${1:-}" in')]

    assert "systemd-run" in verify_start
    assert "linasbot-ha-verify.service" in source
    assert "remove_maintenance_boot_guard" not in verify_start
    assert "systemctl disable --now linasbot.service" in verify_start
    assert 'systemctl disable --now "linasbot-worker@${queue}.service"' in verify_start
    assert 'systemctl start "linasbot-worker@${queue}.service"' not in verify_start
    assert '"$REPO_DIR/venv/bin/python" -B -I "$REPO_DIR/$RELEASE_VERIFY_REPO_PATH"' in verify_start
    assert '"$REPO_DIR/venv/bin/python" "$REPO_DIR/main.py"' not in verify_start
    assert "run_target_readiness_probe" in verify_start
    assert "LINAS_HA_VERIFY_ONLY=true" in verify_start
    assert "LINAS_HA_VERIFY_RELEASE_SHA=$target_sha" in verify_start
    assert "systemctl enable linasbot.service" not in final_start
    assert "systemctl start linasbot.service" not in enable_last
    assert "systemctl enable linasbot.service" in enable_last
    assert final_start.index("assert_unit_file_contract linasbot") < final_start.index(
        "systemctl start linasbot.service"
    )
    assert final_start.index('assert_unit_file_contract "linasbot-worker@${queue}.service"') < final_start.index(
        'systemctl start "linasbot-worker@${queue}.service"'
    )
    assert 'systemctl enable "linasbot-worker@${queue}.service"' not in final_start
    assert 'systemctl enable "linasbot-worker@${queue}.service"' in enable_last
    parity = orchestrate.index('update_deploy_journal "target-parity-awaiting-fresh-lb"')
    assert 'remote_node "$peer_host" clear-maintenance' not in orchestrate[parity:]
    assert clear.index("remove_maintenance_boot_guard") < clear.index("start_admitted_target_runtime")
    target = clear[: clear.index("\n  else\n    test -z")]
    assert target.index('start_admitted_target_runtime "$tx_dir"') < target.index(
        'write_pre_admission_proof "$tx_dir" "$admission_sha"'
    )
    assert target.index("enable_admitted_target_autostart") < target.index(
        'write_pre_admission_proof "$tx_dir" "$admission_sha"'
    )
    assert target.index('write_pre_admission_proof "$tx_dir" "$admission_sha"') < target.index(
        "clear_maintenance_markers_durable"
    )
    assert clear.index("clear_maintenance_markers_durable") < clear.index(
        'write_admission_proof "$tx_dir" "$admission_sha"'
    )
    assert clear.index('write_admission_proof "$tx_dir" "$admission_sha"') < clear.index(
        'clear_deploy_node_sentinel "$tx_dir"'
    )


def test_health_only_verifier_has_no_application_bootstrap_or_provider_routes() -> None:
    env = dict(os.environ)
    env.update(
        {
            "DISABLE_API_DOCS": "1",
            "ENVIRONMENT": "production",
            "PYTHONDONTWRITEBYTECODE": "1",
        }
    )
    script = """
import sys
from scripts.ha.release_verify_server import verification_app
app = verification_app()
assert {str(route.path) for route in app.routes} == {'/', '/api/health', '/api/ready'}
assert 'modules.event_handlers' not in sys.modules
assert 'storage.migrate_bootstrap' not in sys.modules
"""
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        timeout=20,
        check=False,
    )
    assert result.returncode == 0, result.stderr


def test_precommit_readiness_probe_is_bounded_collectable_and_non_routable() -> None:
    source = _helper()
    probe = source[
        source.index("run_target_readiness_probe() {") : source.index("assert_ready() {")
    ]
    assert "systemctl stop \"$VERIFY_READINESS_UNIT\"" in probe
    assert "systemctl reset-failed \"$VERIFY_READINESS_UNIT\"" in probe
    assert "LoadState" in probe and '"not-found"' in probe
    assert "--property=RuntimeMaxSec=45s" in probe
    assert "--property=TimeoutStartSec=45s" in probe
    assert "--property=TimeoutStopSec=5s" in probe
    assert "--property=SendSIGKILL=yes" in probe
    assert "release_readiness_probe.py" in source


def test_release_artifact_parity_hashes_venv_bytes_and_requires_hashed_lock() -> None:
    source = _helper()
    manifest = source[
        source.index("write_installed_distribution_manifest() {") : source.index(
            "release_artifact_evidence() {"
        )
    ]
    stage = source[source.index("backup_live_node() {") : source.index("normalize_prequiesced_activation_prefix() {")]
    activation = source[source.index("activate_impl() {") : source.index("start_saved_runtime_disabled() {")]
    assert '"schema": 2' in manifest
    assert '"venv_tree_sha256"' in manifest
    assert '"python_executable_sha256"' in manifest
    assert "file_hash.update(chunk)" in manifest
    assert 'os.readlink(path)' in manifest
    assert "requirements.lock" in source
    assert stage.count("--require-hashes") >= 1
    assert "--require-hashes" in activation
    assert "pip wheel" not in stage and "npm ci" not in stage and "npm run build" not in stage
    assert "requirements.txt" not in stage


def test_unit_contract_rejects_shadow_hooks_dropins_and_extra_environment() -> None:
    source = _helper()
    contract = source[source.index("assert_unit_file_contract() {") : source.index("assert_unit_contract() {")]
    for property_name in (
        "FragmentPath",
        "DropInPaths",
        "ExecStartPre",
        "ExecStartPost",
        "ExecCondition",
        "EnvironmentFiles",
        "Environment",
        "User",
    ):
        assert property_name in contract
    assert "canonical unit has a missing or unauthorized drop-in" in contract
    assert "canonical unit has an unauthorized direct environment assignment" in contract
    assert "92-meta-controlled-failover.conf" in contract
    assert "95-linasbot-credential-rekey-guard.conf" in contract


def test_precommit_and_serving_parity_rechecks_exact_clean_worktree() -> None:
    source = _helper()
    drained = source[source.index("node_assert_release_drained() {") : source.index("node_assert_serving_contract() {")]
    serving = source[source.index("node_assert_serving_contract() {") : source.index("node_assert_release_ready() {")]
    assert 'git -C "$REPO_DIR" diff --quiet "$expected_sha" --' in drained
    assert 'git -C "$REPO_DIR" diff --cached --quiet "$expected_sha" --' in drained
    assert "precommit-drained" in drained and "audit_untracked_runtime" in drained
    assert 'git -C "$REPO_DIR" diff --quiet "$expected_sha" --' in serving
    assert 'git -C "$REPO_DIR" diff --cached --quiet "$expected_sha" --' in serving


def test_terminal_success_disarms_fail_close_before_journal_unlink() -> None:
    source = _helper()
    for start, end in (
        ("recover_deployment() {", "retry_distinct_reconciliation() {"),
        ("commit_target_deployment() {", "orchestrate() {"),
    ):
        body = source[source.index(start) : source.index(end)]
        succeeded = body.rindex("transaction_succeeded=1")
        disarm = body.index("trap - EXIT INT TERM", succeeded)
        complete = body.index("complete", disarm)
        clear = body.index("clear_deploy_journal", disarm)
        assert succeeded < disarm < complete < clear
    for start, end in (
        ("retry_distinct_reconciliation() {", "deployment_recovery_status() {"),
        ("orchestrate() {", 'case "${1:-}" in'),
    ):
        body = source[source.index(start) : source.index(end)]
        awaiting = body.rindex('"target-parity-awaiting-fresh-lb"')
        succeeded = body.index("transaction_succeeded=1", awaiting)
        disarm = body.index("trap - EXIT INT TERM", succeeded)
        assert awaiting < succeeded < disarm
        assert "clear_deploy_journal" not in body[disarm:]


def test_activation_history_ack_loss_promotes_exact_successor_before_replay() -> None:
    source = _helper()
    state = source[source.index("activation_state_tool() {") : source.index("write_activation_phase() {")]
    rollback = source[source.index("rollback_impl() {") : source.index("node_activate() {")]
    assert "def adopt_pending_history_event" in state
    assert "activation history has ambiguous pending transitions" in state
    assert 'pending.get("sibling_artifacts") != sibling_artifacts()' in state
    assert "pending activation history event does not match live durable artifacts" in state
    assert "publish_state_pointer(encoded)" in state
    adopted = state.index("current = adopt_pending_history_event(current)")
    read_dispatch = state.index('if operation == "read":', adopted)
    write_dispatch = state.index('if operation != "write"', read_dispatch)
    assert adopted < read_dispatch < write_dispatch
    # rollback_impl reads the (possibly promoted) pointer before selecting any
    # preserve/extract action, so a durable restored event skips those effects.
    first_phase_read = rollback.index("read_activation_phase")
    first_partial_move = rollback.index("preserve_partial_restore")
    assert first_phase_read < first_partial_move


def test_interrupted_target_reset_has_durable_rollback_authority() -> None:
    source = _helper()
    activation = source[source.index("activate_impl() {") : source.index("start_saved_runtime_disabled() {")]
    rollback = source[source.index("rollback_impl() {") : source.index("node_activate() {")]
    state = source[source.index("activation_state_tool() {") : source.index("write_activation_phase() {")]

    clean_worktree = activation.index(
        'git -C "$REPO_DIR" diff --quiet "$previous_sha" --',
        activation.index("dashboard-moved"),
    )
    clean_index = activation.index(
        'git -C "$REPO_DIR" diff --cached --quiet "$previous_sha" --', clean_worktree
    )
    reset_authority = activation.index("target-reset-started", clean_index)
    stale_lock_recovery = activation.index(
        'recover_transaction_git_locks "$tx_dir" "$generation" target-reset', reset_authority
    )
    reset = activation.index('git -C "$REPO_DIR" reset --hard "$target_sha"', stale_lock_recovery)
    installed = activation.index("target-installed", reset)
    assert clean_worktree < clean_index < reset_authority < stale_lock_recovery < reset < installed

    assert '"dashboard-moved": "target-reset-started"' in state
    assert '"target-reset-started": "target-installed"' in state
    assert "forward = phases[:6]" in state
    assert (
        "quiesced | venv-moved | dashboard-moved | target-reset-started | "
        "target-installed | activated"
    ) in rollback
    dirty_case = rollback.index('case "$phase" in')
    dirty_guard = rollback[dirty_case : rollback.index("\n  esac", dirty_case)]
    # Once target-reset-started is durable, HEAD may still be the baseline while
    # the index/worktree is partially target-written. Rollback must reset from
    # authority instead of requiring that interrupted tree to be clean.
    assert "target-reset-started" not in dirty_guard
    rollback_reset = rollback.index('git -C "$REPO_DIR" reset --hard "$previous_sha"')
    assert rollback.index(
        'recover_transaction_git_locks "$tx_dir" "$generation" rollback-reset'
    ) < rollback_reset


def test_git_reset_lock_recovery_archives_closed_locks_across_repeated_kills(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    git_dir = repo / ".git"
    for relative in ("refs/heads", "logs/refs/heads"):
        (git_dir / relative).mkdir(parents=True, mode=0o700)
    live_lock = tmp_path / "meta-live.lock"
    live_lock.write_bytes(b"")
    live_lock.chmod(0o600)
    descriptor = os.open(live_lock, os.O_RDWR)
    fcntl.flock(descriptor, fcntl.LOCK_EX)
    tx_name = f"{'a' * 40}-20260814213000-123"
    tx_path = f"/var/backups/linasbot-ha/{tx_name}"
    symbolic_ref = "refs/heads/main"
    lock_paths = (
        git_dir / "index.lock",
        git_dir / "HEAD.lock",
        git_dir / "ORIG_HEAD.lock",
        git_dir / "logs/HEAD.lock",
        git_dir / "refs/heads/main.lock",
        git_dir / "logs/refs/heads/main.lock",
    )

    def make_live_locks(payload: bytes) -> None:
        for path in lock_paths:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(payload)
            path.chmod(0o644)

    def run_recovery() -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                sys.executable,
                "-c",
                _embedded_python("recover_transaction_git_locks"),
                str(repo),
                str(live_lock),
                tx_path,
                "1",
                "rollback-reset",
                symbolic_ref,
                str(descriptor),
                str(os.geteuid()),
                str(os.getegid()),
            ],
            pass_fds=(descriptor,),
            text=True,
            capture_output=True,
            check=False,
        )

    try:
        make_live_locks(b"first interrupted reset")
        first = run_recovery()
        assert first.returncode == 0, first.stderr
        assert all(not path.exists() for path in lock_paths)

        archive = git_dir / "linasbot-ha-orphan-locks" / tx_name / "g0001-rollback-reset"
        assert len(tuple(archive.glob("*-0001.bin"))) == len(lock_paths)
        assert all(path.stat().st_mode & 0o777 == 0o600 for path in archive.iterdir())

        # A second killed replay is preserved as the next immutable occurrence,
        # never confused with or allowed to overwrite the first one.
        make_live_locks(b"second interrupted reset")
        second = run_recovery()
        assert second.returncode == 0, second.stderr
        assert len(tuple(archive.glob("*-0002.bin"))) == len(lock_paths)

        # Power can persist rename before chmod/fsync. Exact 0644 bytes inside
        # the root-only archive are normalized durably on the next recovery.
        renamed_before_chmod = archive / "index-0003.bin"
        renamed_before_chmod.write_bytes(b"rename persisted before chmod")
        renamed_before_chmod.chmod(0o644)
        normalize = run_recovery()
        assert normalize.returncode == 0, normalize.stderr
        assert renamed_before_chmod.stat().st_mode & 0o777 == 0o600

        unknown = git_dir / "packed-refs.lock"
        unknown.write_bytes(b"not created by the closed reset contract")
        unknown.chmod(0o644)
        rejected = run_recovery()
        assert rejected.returncode != 0
        assert "unknown Git lock blocks exact recovery" in rejected.stderr
        assert unknown.read_bytes() == b"not created by the closed reset contract"
    finally:
        os.close(descriptor)


def test_git_common_directory_attribute_authority_is_rejected(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    common = tmp_path / "common"
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.name", "Test"], check=True)
    subprocess.run(
        ["git", "-C", str(repo), "config", "user.email", "test@example.invalid"],
        check=True,
    )
    (repo / "keep.txt").write_text("keep\n", encoding="utf-8")
    (repo / "omit.txt").write_text("omit\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "add", "keep.txt", "omit.txt"], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-qm", "fixture"], check=True)
    (repo / ".git").rename(common)
    (repo / ".git").mkdir()
    (repo / ".git/commondir").write_text(f"{common}\n", encoding="utf-8")
    for name in ("HEAD", "index"):
        (repo / f".git/{name}").write_bytes((common / name).read_bytes())
    (common / "info").mkdir(exist_ok=True)
    (common / "info/attributes").write_text("omit.txt export-ignore\n", encoding="utf-8")

    archive = subprocess.run(
        ["git", "-C", str(repo), "archive", "HEAD"],
        check=True,
        capture_output=True,
    ).stdout
    with tarfile.open(fileobj=io.BytesIO(archive), mode="r:") as payload:
        assert payload.getnames() == ["keep.txt"]

    trust = _helper()[
        _helper().index("assert_git_repository_trust() {") : _helper().index("current_head() {")
    ]
    assert '"$REPO_DIR/.git/commondir"' in trust
    assert "rev-parse --path-format=absolute --git-common-dir" in trust
    assert "rev-parse --git-path info/attributes" in trust


def test_release_import_ref_lock_recovery_is_repeatable_and_closed(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    git_dir = repo / ".git"
    ref_parent = git_dir / "refs/linasbot-release-artifacts"
    ref_parent.mkdir(parents=True)
    authority = tmp_path / "release-import-intents"
    authority.mkdir()
    intent = authority / "fixture.intent"
    intent.write_text("intent\n", encoding="utf-8")
    intent.chmod(0o600)
    live_lock = tmp_path / "meta-live.lock"
    live_lock.write_bytes(b"")
    live_lock.chmod(0o600)
    descriptor = os.open(live_lock, os.O_RDWR)
    fcntl.flock(descriptor, fcntl.LOCK_EX)
    target_sha = "a" * 40
    source_lock = ref_parent / f"{target_sha}.lock"
    python = _embedded_python("recover_release_import_ref_lock")
    python = python.replace(".st_uid != 0", ".st_uid != expected_uid")
    python = python.replace(".st_gid != 0", ".st_gid != expected_gid")
    python = python.replace("os.chown(directory, 0, 0)", "os.chown(directory, expected_uid, expected_gid)")
    python = python.replace(
        'lock_fd = int(sys.argv[5])',
        'lock_fd = int(sys.argv[5])\nexpected_uid = int(sys.argv[6])\nexpected_gid = int(sys.argv[7])',
    )

    def recover() -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                sys.executable,
                "-c",
                python,
                str(repo),
                str(live_lock),
                target_sha,
                str(intent),
                str(descriptor),
                str(os.geteuid()),
                str(os.getegid()),
            ],
            pass_fds=(descriptor,),
            text=True,
            capture_output=True,
            check=False,
        )

    try:
        source_lock.write_bytes(b"first interrupted import")
        source_lock.chmod(0o644)
        first = recover()
        assert first.returncode == 0, first.stderr
        archive = git_dir / "linasbot-release-import-locks" / target_sha
        assert (archive / "ref-0001.bin").read_bytes() == b"first interrupted import"

        source_lock.write_bytes(b"second interrupted import")
        source_lock.chmod(0o644)
        second = recover()
        assert second.returncode == 0, second.stderr
        assert (archive / "ref-0002.bin").read_bytes() == b"second interrupted import"

        unknown = git_dir / "packed-refs.lock"
        unknown.write_bytes(b"unknown")
        unknown.chmod(0o644)
        source_lock.write_bytes(b"third")
        source_lock.chmod(0o644)
        rejected = recover()
        assert rejected.returncode != 0
        assert "unknown Git lock blocks release import" in rejected.stderr
        assert source_lock.read_bytes() == b"third"
    finally:
        os.close(descriptor)


def test_release_import_fsync_is_absolute_from_any_working_directory(tmp_path: Path) -> None:
    source = _helper()
    installer = source[source.index("install_release_bundle() {") : source.index("install_lb_ready_attestation() {")]
    assert 'fsync_tree "$REPO_DIR/.git"' in installer
    assert 'fsync_tree "$(git -C "$REPO_DIR" rev-parse --git-dir)"' not in installer
    unrelated = tmp_path / "unrelated"
    unrelated.mkdir()
    result = subprocess.run(
        ["/bin/bash", "-c", 'cd "$1" && test "$(dirname /opt/linasbot/.git)" = /opt/linasbot', "test", str(unrelated)],
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


def test_forward_and_rollback_admission_prove_exact_process_queue_and_live_env() -> None:
    source = _helper()
    proof = source[
        source.index("assert_exact_runtime_process_contract() {") : source.index("assert_ready() {")
    ]
    preflight = source[source.index("node_preflight() {") : source.index("capture_service_state() {")]
    rollback_start = source[
        source.index("start_saved_runtime_disabled() {") : source.index("rollback_impl() {")
    ]
    target_start = source[
        source.index("start_admitted_target_runtime() {") : source.index("node_clear_maintenance() {")
    ]
    serving = source[source.index("node_assert_serving_contract() {") : source.index("node_assert_release_ready() {")]

    assert '[python, "scripts/run_queue_worker.py", "--queue", queue]' in proof
    assert "live_argv != expected_argv" in proof
    assert 'expected["LINAS_WORKER_QUEUE"] = queue' in proof
    assert "live_environment.get(key) != value" in proof
    assert 'Path(os.path.realpath(proc / "exe"))' in proof
    assert "stable_pid != main_pid" in proof
    assert 'need_reload != "no"' in proof
    assert 'payload != {' in proof and '"role": "queue_readiness"' in proof
    assert "assert_exact_runtime_process_contract enabled" in preflight
    assert "assert_exact_runtime_process_contract disabled" in rollback_start
    assert "assert_exact_runtime_process_contract disabled" in target_start
    assert "assert_exact_runtime_process_contract enabled" in target_start
    assert "assert_exact_runtime_process_contract enabled" in serving
    assert "assert_active_runtime_process_env_contract" in preflight
    assert "assert_active_runtime_process_env_contract" in rollback_start
    assert target_start.count("assert_active_runtime_process_env_contract") >= 2
    assert '"/proc/$main_pid/environ"' in proof


def test_deploy_refuses_controlled_failover_and_registry_nfs_retirement_transactions() -> None:
    source = _helper()
    collision = source[source.index("assert_no_other_meta_transaction() {") : source.index("write_deploy_journal() {")]
    assert "CONTROLLED_FAILOVER_ACTIVE_FILE=$META_HA_STATE_ROOT/controlled-failover.active" in source
    assert "REGISTRY_NFS_RETIRE_ACTIVE_FILE=$META_HA_STATE_ROOT/registry-nfs-retire.active" in source
    assert 'assert_path_absent "$CONTROLLED_FAILOVER_ACTIVE_FILE"' in collision
    assert 'assert_path_absent "$REGISTRY_NFS_RETIRE_ACTIVE_FILE"' in collision
    assert 'assert_path_absent "$PYTHON_RUNTIME_PROVISION_ACTIVE_FILE"' in collision
    assert 'assert_path_absent "$PYTHON_RUNTIME_PROVISION_COORDINATOR_FILE"' in collision
    lb_install = source[
        source.index("assert_lb_attestation_install_collision_contract() {") : source.index(
            "install_lb_ready_attestation() {"
        )
    ]
    assert '"$PYTHON_RUNTIME_PROVISION_ACTIVE_FILE"' in lb_install
    assert '"$PYTHON_RUNTIME_PROVISION_COORDINATOR_FILE"' in lb_install


def test_deploy_proves_full_cluster_runtime_env_and_never_derives_node_local_values() -> None:
    source = _helper()
    projection = CLUSTER_ENV_HELPER.read_text(encoding="utf-8")
    activation = source[source.index("activate_impl() {") : source.index("start_saved_runtime_disabled() {")]
    orchestrate = source[source.index("orchestrate() {") : source.index('case "${1:-}" in')]
    recovery = source[source.index("recover_deployment() {") : source.index("retry_distinct_reconciliation() {")]
    helper_runner = source[
        source.index("materialize_cluster_env_helper() {") : source.index("current_head() {")
    ]

    assert '"META_DELETION_NODE_ID"' in projection
    assert '"LINAS_HA_PEER_HOST"' in projection
    assert "NODE_LOCAL_KEYS" in projection
    assert "OPENAI" not in projection and "RESEND" not in projection and "CM_" not in projection
    assert 'FORMAT = "linas-cluster-runtime-env-v1"' in projection
    assert 'remote_node "$peer_host" env-evidence' in helper_runner
    assert "compare_cluster_runtime_env_evidence" in helper_runner
    assert 'mktemp -d -p /run linasbot-cluster-env.XXXXXXXX' in helper_runner
    assert 'git -C "$REPO_DIR" rev-parse "$source_sha:$path"' in helper_runner
    assert 'git -C "$REPO_DIR" hash-object "$destination"' in helper_runner
    assert "run_system_python_control" in helper_runner
    assert '"$(python_bin)"' not in helper_runner
    assert "--process-environ" in helper_runner
    assert "prod_cm_preserve_durable_flags.sh" not in activation
    assert "prod_upsert_model_routing_env.py" not in activation
    assert "never derives node-local CM/model values" in activation
    assert orchestrate.count('assert_cluster_runtime_env_parity "$peer_host"') >= 4
    assert recovery.count('assert_cluster_runtime_env_parity "$peer_host"') >= 3
    preflight = source[source.index("node_preflight() {") : source.index("capture_service_state() {")]
    assert 'assert_active_runtime_process_env_contract "$target_sha" "$target_sha" "$expected_node_id"' in preflight
    both_preflights = orchestrate.index('if [ "$local_preflight_rc" -ne 0 ]')
    env_parity = orchestrate.index(
        'assert_cluster_runtime_env_parity "$peer_host" "$target_sha" "$target_sha"'
    )
    transaction_start = orchestrate.index("transaction_started=1")
    assert both_preflights < env_parity < transaction_start


def test_deploy_rejects_canonical_code_loader_environment_in_preflight_and_process_proof() -> None:
    source = _helper()
    projection = CLUSTER_ENV_HELPER.read_text(encoding="utf-8")
    guard = PRODUCTION_GUARD.read_text(encoding="utf-8")
    process = source[
        source.index("assert_exact_runtime_process_contract() {") : source.index("assert_ready() {")
    ]
    for blocker in ("PYTHONPATH", "PYTHONHOME", "LD_PRELOAD", '"LD_"', "BASH_ENV", "NODE_OPTIONS"):
        assert blocker in projection or blocker in guard
        assert blocker in process
    assert "execution-control key" in projection
    assert "forbidden code-loader control" in process


def test_deploy_has_durable_digest_bound_recovery_for_kill_and_ack_loss() -> None:
    source = _helper()
    orchestrate = source[source.index("orchestrate() {") : source.index('case "${1:-}" in')]
    recover = source[source.index("recover_deployment() {") : source.index("deployment_recovery_status() {")]

    assert "DEPLOY_ACTIVE_FILE=$META_HA_STATE_ROOT/deploy.active" in source
    assert 'os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)' in source
    assert 'phase != "preflight-proven" or decision != "rollback"' in source
    assert orchestrate.index('update_deploy_journal "preflight-proven"') < orchestrate.index("transaction_started=1")
    for phase in (
        "peer-mark-started",
        "peer-staged",
        "peer-activated",
        "node01-marked",
        "node01-activated",
        "target-parity-awaiting-fresh-lb",
    ):
        assert f'update_deploy_journal "{phase}"' in orchestrate
    commit = source[source.index("commit_target_deployment() {") : source.index("orchestrate() {")]
    assert 'update_commit_journal "commit-lb-attested" rollback' in commit
    assert commit.index('update_commit_journal "target-parity-proven" commit') < commit.index(
        'remote_node "$peer_host" recover-admit'
    )
    assert 'assert_commit_journal "target-parity-proven" commit' in commit
    assert "durable deployment commit decision cannot be reversed" in source
    assert orchestrate.index("refresh_durable_decision", orchestrate.index("rollback_transaction()")) < (
        orchestrate.index('if [ "$commit_decided" = "1" ]')
    )
    assert "durable commit decision was already recorded" in orchestrate
    assert "recover-confirmed)" in source
    assert "recovery-status)" in source
    assert "RECOVER_DEPLOY_" in recover
    assert 'remote_node "$peer_host" recover-admit' in recover
    assert 'remote_node "$peer_host" recover-rollback' in recover
    assert "both nodes were forced fail-closed" in recover


def test_distinct_drained_rollback_has_an_exact_retryable_reconciliation_path() -> None:
    source = _helper()
    recover = source[source.index("recover_deployment() {") : source.index("retry_distinct_reconciliation() {")]
    retry = source[
        source.index("retry_distinct_reconciliation() {") : source.index("deployment_recovery_status() {")
    ]
    status = source[source.index("deployment_recovery_status() {") : source.index("orchestrate() {")]
    dispatch = source[source.index('case "${1:-}" in') :]
    workflow = WORKFLOW.read_text(encoding="utf-8")

    assert 'update_recovery_journal "distinct-rollback-drained"' in recover
    assert "both remain drained pending a newly confirmed reconciliation" in recover
    assert 'test "$phase" = "distinct-rollback-drained"' in retry
    assert 'test "$decision" = "rollback"' in retry
    assert 'test "$previous_sha" != "$peer_previous_sha"' in retry
    assert "RETRY_DEPLOY_" in retry
    assert "_FROM_DISTINCT_DRAINED" in retry
    local_exact = retry.index('node_assert_exact_head "$previous_sha" "$tx_dir"')
    peer_exact = retry.index('remote_node "$peer_host" assert-head "$peer_previous_sha" "$tx_dir"')
    peer_stage = retry.index('remote_node "$peer_host" retry-stage "$target_sha" "$peer_previous_sha" "$tx_dir"')
    local_stage = retry.index('prepare_retry_stage "$target_sha" "$previous_sha" "$tx_dir"')
    peer_activate = retry.index('remote_node "$peer_host" activate "$target_sha" "$peer_previous_sha" "$tx_dir"')
    local_activate = retry.index('node_activate "$target_sha" "$previous_sha" "$tx_dir"')
    parity = retry.index('update_retry_journal "target-parity-awaiting-fresh-lb"')
    assert local_exact < peer_exact < peer_stage < local_stage < peer_activate < local_activate < parity
    assert 'remote_node "$peer_host" recover-admit "$target_sha" "$tx_dir"' not in retry
    assert 'node_recover_admit "$target_sha" "$tx_dir"' not in retry
    assert 'node_recover_rollback "$previous_sha" "$tx_dir"' in retry
    assert 'remote_node "$peer_host" recover-rollback' in retry
    assert 'update_retry_journal "distinct-rollback-drained"' in retry
    retry_stage = source[source.index("prepare_retry_stage() {") : source.index("stop_runtime() {")]
    assert "preserved incomplete stage before exact retry" in retry_stage
    assert 'mv -T -- "$entry" "$archive/$name"' in retry_stage
    assert 'backup_live_node "$target_sha" "$previous_sha" "$tx_dir"' in retry_stage
    assert "RETRY_CONFIRMATION=" in status
    assert "retry-reconcile-confirmed)" in dispatch

    assert "retry_reconcile_exact" in workflow
    assert "RETRY_RECONCILE_CONFIRM" in workflow
    assert '"$HELPER_PATH" retry-reconcile-confirmed' in workflow
    assert '[ "$NODE01_BASELINE_SHA" != "$NODE02_BASELINE_SHA" ]' in workflow
    assert "workflow_run:" not in workflow


def test_legacy_runtime_retirement_is_persistent_and_checked_at_admission() -> None:
    source = _helper()
    retirement = source[
        source.index("assert_legacy_retirement_contract() {") : source.index("assert_no_shadow_runtime() {")
    ]
    assert "/var/lib/linasbot/meta-ha/legacy-linas-ai-bot-retired" in retirement
    assert "LEGACY_RETIREMENT_GUARD" in retirement
    assert "90-linasbot-retired.conf" in source
    assert "ConditionPathExists=!/var/lib/linasbot/meta-ha/legacy-linas-ai-bot-retired" in retirement
    assert "systemctl is-enabled --quiet linas_ai_bot.service" in retirement
    assert "systemctl cat linas_ai_bot.service" in retirement
    assert "--property=NeedDaemonReload" in retirement
    assert source.count('assert_legacy_retirement_contract "$(configured_node_id)"') >= 5


def test_explicit_reconciliation_supports_distinct_exact_baselines_only_once() -> None:
    source = _helper()
    orchestrate = source[source.index("orchestrate() {") : source.index('case "${1:-}" in')]
    dispatch = source[source.index('case "${1:-}" in') :]

    assert "I_UNDERSTAND_RECONCILING_DISTINCT_HA_BASELINES" in source
    assert 'test "$expected_local_previous" != "$expected_peer_previous"' in orchestrate
    assert 'test "$previous_sha" = "$expected_local_previous"' in orchestrate
    assert 'test "$peer_previous_sha" = "$expected_peer_previous"' in orchestrate
    assert (
        'read_bootstrap_commit_proof "$expected_node_id" "$expected_bootstrap_plan" \\\n'
        '      "$python_runtime_cluster_sha"'
    ) in source
    assert "bootstrap.last-committed.json" in source
    assert 'validate_digest "$expected_bootstrap_plan"' in orchestrate
    steady = orchestrate[
        orchestrate.index("steady-confirmed)") : orchestrate.index("reconcile)")
    ]
    assert 'validate_digest "$expected_bootstrap_plan"' in steady
    assert 'test -z "$reconcile_confirmation"' in steady
    assert 'test -z "$expected_bootstrap_plan$reconcile_confirmation"' not in steady
    assert orchestrate.count('extract_contract_value BOOTSTRAP_PLAN_SHA') == 2
    assert 'rollback_impl "$previous_sha" "$tx_dir"' in orchestrate
    assert 'remote_node "$peer_host" rollback "$peer_previous_sha" "$tx_dir"' in orchestrate
    assert "both remain drained to prevent mixed-SHA serving" in orchestrate
    assert "orchestrate-reconcile)" in dispatch
    steady_dispatch = dispatch[
        dispatch.index("orchestrate-confirmed)") : dispatch.index("orchestrate-reconcile)")
    ]
    assert 'orchestrate "${2:-}" steady-confirmed "${3:-}" "${4:-}" "${5:-}" "" "${6:-}"' in steady_dispatch


def test_deploy_accepts_only_the_exact_bootstrap_v2_proof_bound_to_runtime(
    tmp_path: Path,
) -> None:
    code = _embedded_python("read_bootstrap_commit_proof")
    code = code.replace("info.st_uid != 0", "info.st_uid != os.getuid()")
    code = code.replace("info.st_gid != 0", "info.st_gid != os.getgid()")
    proof_path = tmp_path / "bootstrap.last-committed.json"
    plan_sha = "b" * 64
    runtime_cluster_sha = "c" * 64
    digest_keys = {
        "runtime_plan_sha256",
        "runtime_shared_sha256",
        "runtime_launcher_receipt_sha256",
        "qg_manifest_sha256",
        "control_plane_archive_sha256",
        "control_plane_tree_sha256",
        "wheelhouse_archive_sha256",
        "wheelhouse_tree_sha256",
        "requirements_lock_sha256",
        "runtime_tree_sha256",
        "target_unit_contract_sha256",
        "legacy_bytecode_manifest_sha256",
    }
    payload: dict[str, object] = {
        "schema": 2,
        "format": "linas-meta-ha-bootstrap-node-v2",
        "tx_id": "a" * 32,
        "plan_sha256": plan_sha,
        "node_id": "node01",
        "status": "committed",
        "runtime_transaction_id": "pyr_" + "d" * 32,
        "runtime_cluster_receipt_sha256": runtime_cluster_sha,
        "wheelhouse_file_count": 78,
        "wheelhouse_total_size": 1024,
        "repo_bytecode_absent": True,
        **{key: "e" * 64 for key in digest_keys},
    }

    def verify(candidate: dict[str, object], expected_runtime: str = runtime_cluster_sha) -> subprocess.CompletedProcess[str]:
        proof_path.write_bytes(
            json.dumps(candidate, sort_keys=True, separators=(",", ":")).encode() + b"\n"
        )
        proof_path.chmod(0o600)
        return subprocess.run(
            [
                sys.executable,
                "-B",
                "-I",
                "-S",
                "-c",
                code,
                str(proof_path),
                "node01",
                plan_sha,
                expected_runtime,
            ],
            capture_output=True,
            text=True,
            check=False,
        )

    assert verify(payload).returncode == 0
    assert verify({key: value for key, value in payload.items() if key != "repo_bytecode_absent"}).returncode != 0
    assert verify({**payload, "unknown": True}).returncode != 0
    assert verify({**payload, "repo_bytecode_absent": False}).returncode != 0
    assert verify(payload, "f" * 64).returncode != 0
