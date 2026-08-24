"""Global serialization contracts for privileged non-Meta production writers."""

from __future__ import annotations

import os
import subprocess
import threading
import time
from pathlib import Path

import pytest
import yaml

from scripts.ha import production_mutation_guard as guard
from scripts.ha.cluster_runtime_env_contract import (
    load_projection,
    projection_evidence,
    validate_evidence_pair,
    verify_process_environment,
)
from scripts.ha.production_env_cas import atomic_update_env_cas

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"
PINNED_SSH = "appleboy/ssh-action@7eaf76671a0d7eec5d98ee897acda4f968735a17"

SERIALIZED_LIVE_WORKFLOWS = (
    "cm-production-cutover.yml",
    "wa-app-review-connection-source-migrate.yml",
)
META_ENV_LIVE_WORKFLOWS = (
    "instagram-login-secrets-apply.yml",
    "meta-app-a-login-config-apply.yml",
    "meta-multi-app-secrets-apply.yml",
    "meta-social-secrets-apply.yml",
    "meta-webhook-nginx-setup.yml",
    "whatsapp-cloud-phase1-apply.yml",
)
DISABLED_ENV_WORKFLOWS = (
    "copilot-v2-flags-apply.yml",
    "dashboard-auth-secret-apply.yml",
    "model-routing-policy-apply.yml",
    "openai-api-key-apply.yml",
    "resend-secrets-apply.yml",
)
DISABLED_PRIVILEGED_WORKFLOWS = ("ha-infra-ssh-bootstrap.yml",)
READ_ONLY_SSH_WORKFLOWS = (
    "cm-linas-content-audit.yml",
    "prod-preflight-readonly.yml",
    "subscription-exempt-probe.yml",
    "wa-cloud-webhook-readonly-probe.yml",
)


def test_live_non_meta_writers_share_the_meta_cutover_lane_and_exact_runner() -> None:
    for name in SERIALIZED_LIVE_WORKFLOWS:
        path = WORKFLOWS / name
        source = path.read_text(encoding="utf-8")
        parsed = yaml.safe_load(source)
        assert parsed["concurrency"] == {
            "group": "meta-social-cutover",
            "cancel-in-progress": False,
        }, name
        job = next(iter(parsed["jobs"].values()))
        assert job["environment"] == "meta-social-cutover", name
        assert "github.ref == 'refs/heads/main'" in str(job["if"]), name
        assert PINNED_SSH in source, name
        assert "EXPECTED_RELEASE_SHA: ${{ github.sha }}" in source, name
        assert "production_mutation_guard.py" in source, name
        assert '--expected-sha "$EXPECTED_RELEASE_SHA"' in source, name
        assert "origin/main" not in source, name
        assert "git fetch" not in source, name
        assert "git show" not in source, name
        assert "git checkout" not in source, name
        assert "scp-action" not in source, name
        assert "appleboy/ssh-action@v" not in source, name


def test_meta_env_writers_require_main_ref_inherited_lock_and_tx_bound_stage_authority() -> None:
    for name in META_ENV_LIVE_WORKFLOWS:
        source = (WORKFLOWS / name).read_text(encoding="utf-8")
        parsed = yaml.safe_load(source)
        job = next(iter(parsed["jobs"].values()))
        assert "github.ref == 'refs/heads/main'" in str(job["if"]), name
        assert job["environment"] == "meta-social-cutover", name
        assert parsed["concurrency"] == {"group": "meta-social-cutover", "cancel-in-progress": False}, name
        assert "export LINAS_PRODUCTION_MUTATION_LOCK_FD=9" in source, name
        if name == "whatsapp-cloud-phase1-apply.yml":
            remote = (ROOT / "scripts/ha/whatsapp_phase1_apply_remote.sh").read_text(encoding="utf-8")
            lib = (ROOT / "scripts/ha/whatsapp_phase1_apply_lib.sh").read_text(encoding="utf-8")
            combined = source + remote + lib
            assert "--register-prestage-backup" in combined, name
            assert "commit_via_restart=true" in combined, name
        else:
            assert "--register-prestage-backup" in source, name
            assert "--local-prestage-backup" in source, name
        assert 'sudo -E "$REPO_DIR/venv/bin/python" "$REPO_DIR/scripts/ha/sync_meta_env_to_peer.py"' not in source


def test_node01_only_environment_workflows_are_hard_disabled_without_secrets_or_ssh() -> None:
    for name in DISABLED_ENV_WORKFLOWS:
        source = (WORKFLOWS / name).read_text(encoding="utf-8")
        parsed = yaml.safe_load(source)
        assert str(parsed["name"]).startswith("BLOCKED -"), name
        assert parsed["concurrency"] == {
            "group": "meta-social-cutover",
            "cancel-in-progress": False,
        }, name
        job = next(iter(parsed["jobs"].values()))
        assert job["environment"] == "meta-social-cutover", name
        assert "two-node env backup" in source, name
        assert "exit 1" in source, name
        assert "secrets." not in source, name
        assert "ssh-action" not in source, name
        assert "scp-action" not in source, name
        assert "actions/checkout" not in source, name


def test_root_ssh_bootstrap_is_hard_disabled_without_interpolated_key_or_remote_access() -> None:
    for name in DISABLED_PRIVILEGED_WORKFLOWS:
        source = (WORKFLOWS / name).read_text(encoding="utf-8")
        parsed = yaml.safe_load(source)
        assert str(parsed["name"]).startswith("BLOCKED -"), name
        assert parsed["concurrency"] == {
            "group": "meta-social-cutover",
            "cancel-in-progress": False,
        }, name
        job = next(iter(parsed["jobs"].values()))
        assert job["environment"] == "meta-social-cutover", name
        assert "authorized_keys changes require" in source
        assert "exit 1" in source
        assert "agent_pubkey" not in source
        assert "authorized_keys" not in source.replace("authorized_keys changes require", "")
        assert "secrets." not in source
        assert "ssh-action" not in source


def test_read_only_production_ssh_workflows_use_immutable_action_revisions() -> None:
    for name in READ_ONLY_SSH_WORKFLOWS:
        source = (WORKFLOWS / name).read_text(encoding="utf-8")
        assert "appleboy/ssh-action@v" not in source, name
        assert PINNED_SSH in source, name


def test_direct_registry_db_writers_require_common_lock_collision_and_release_gates() -> None:
    for name in ("import_meta_registry_to_postgres.py", "meta_registry_pg_snapshot.py"):
        source = (ROOT / "scripts" / "ha" / name).read_text(encoding="utf-8")
        assert "acquire_direct_production_mutation_lock" in source, name
        assert "--expected-release-sha" in source, name
        assert "mutation_lock_fd" in source, name
        assert "reviewed two-node release/env/drain coordinator" in source, name
    retirement = (ROOT / "scripts/ha/retire_meta_registry_nfs_ha.py").read_text(encoding="utf-8")
    assert "import_meta_registry_to_postgres" not in retirement
    assert "meta_registry_pg_snapshot" not in retirement


def test_registry_restore_apply_stops_before_snapshot_or_database_access(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from scripts.ha import meta_registry_pg_snapshot as snapshot
    from scripts.ha import production_mutation_guard

    called = False

    def forbidden_restore(_args: object) -> int:
        nonlocal called
        called = True
        return 0

    monkeypatch.setattr(snapshot, "_require_root", lambda: None)
    monkeypatch.setattr(snapshot, "_restore_command", forbidden_restore)
    monkeypatch.setattr(
        production_mutation_guard,
        "acquire_direct_production_mutation_lock",
        lambda **_kwargs: os.open(tmp_path / "mutation.lock", os.O_RDWR | os.O_CREAT, 0o600),
    )
    result = snapshot.main(
        [
            "restore",
            str(tmp_path / "never-read.enc"),
            "--apply",
            "--expected-release-sha",
            "a" * 40,
            "--env-file",
            "/opt/linasbot/.env",
            "--recovery-key-file",
            str(tmp_path / "never-read-key.env"),
        ]
    )
    assert result == 2
    assert not called
    assert "signed, current, both-node-drained coordinator" in capsys.readouterr().err


def test_legacy_two_node_env_and_infra_mutators_are_retired_fail_closed() -> None:
    for name in (
        "apply_resend_secrets_both_nodes.sh",
        "managed_pg_cutover_dsn.sh",
        "close_divergence_node01.sh",
        "close_divergence_node02.sh",
    ):
        source = (ROOT / "scripts" / "ha" / name).read_text(encoding="utf-8")
        prefix = "\n".join(source.splitlines()[:10])
        assert "BLOCKED:" in prefix, name
        assert "exit 2" in prefix, name


def test_cm_env_restart_phases_are_explicitly_blocked_but_db_data_phases_remain_guarded() -> None:
    source = (WORKFLOWS / "cm-production-cutover.yml").read_text(encoding="utf-8")
    for phase in (
        "enable_publish_keep_legacy",
        "cutover_published",
        "rollback_legacy",
        "enable_faq_canonical",
        "disable_linas_legacy_bridge",
        "preserve_durable_flags",
        "verify_durable_bridge",
    ):
        assert phase in source
    assert "TWO_NODE_ENV_PHASES" in source
    assert "generic two-node env backup/sync/restart/rollback proof" in source
    for script in (
        "scripts/prod_cm_migrate_and_validate.sh",
        "scripts/prod_cm_publish.sh",
        "scripts/prod_cm_publish_faq_only.sh",
        "scripts/prod_cm_rollback_version.sh",
        "scripts/prod_cm_import_prices.sh",
        "scripts/prod_cm_repair_linas_prices_publish.sh",
    ):
        assert f"guarded {script}" in source


def test_guard_inventory_blocks_every_unsafe_single_node_env_entrypoint() -> None:
    expected = {
        "scripts/prod_apply_copilot_v2_flags.sh",
        "scripts/prod_apply_dashboard_auth.sh",
        "scripts/prod_apply_model_routing_policy.sh",
        "scripts/prod_apply_openai_api_key.sh",
        "scripts/prod_apply_resend_secrets.sh",
        "scripts/prod_cm_apply_flags.sh",
        "scripts/prod_cm_cutover.sh",
        "scripts/prod_cm_preserve_durable_flags.sh",
        "scripts/prod_cm_rollback.sh",
        "scripts/prod_cm_set_linas_bridge_flag.sh",
        "scripts/prod_cm_verify_durable_bridge.sh",
        "scripts/prod_whatsapp_cloud_phase1_ops.sh",
    }
    assert guard.TWO_NODE_ENV_TRANSACTION_REQUIRED == expected
    assert expected <= guard.ALLOWED_SCRIPTS


def test_guarded_child_environment_uses_canonical_values_not_stale_ambient(tmp_path: Path) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text("DATABASE_URL=canonical-db\nOPENAI_API_KEY=canonical-key\n", encoding="utf-8")
    child = guard._build_child_environment(
        expected_sha="a" * 40,
        script="scripts/prod_cm_publish.sh",
        lock_fd=9,
        ambient={
            "PATH": "/bin",
            "DATABASE_URL": "stale-db",
            "OPENAI_API_KEY": "stale-key",
            "PHASE": "publish",
            "UNRELATED_STALE_CONFIG": "must-not-pass",
        },
        env_path=env_path,
    )
    assert child["DATABASE_URL"] == "canonical-db"
    assert child["OPENAI_API_KEY"] == "canonical-key"
    assert "PHASE" not in child
    assert "UNRELATED_STALE_CONFIG" not in child
    assert child["PATH"] == guard.FIXED_CHILD_ENV["PATH"]


@pytest.mark.parametrize(
    "poisoned",
    (
        "BASH_ENV",
        "PYTHONPATH",
        "PYTHONHOME",
        "PYTHONPYCACHEPREFIX",
        "PYTHONPLATLIBDIR",
        "LD_PRELOAD",
        "LD_AUDIT",
        "PATH",
        "NODE_OPTIONS",
        "BASH_FUNC_hook%%",
    ),
)
def test_guarded_child_environment_rejects_execution_control_poisoning(tmp_path: Path, poisoned: str) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text(f"DATABASE_URL=canonical-db\n{poisoned}=/tmp/hook\n", encoding="utf-8")
    with pytest.raises(RuntimeError, match="execution-control"):
        guard._build_child_environment(
            expected_sha="a" * 40,
            script="scripts/prod_cm_publish.sh",
            lock_fd=9,
            ambient={"PATH": "/attacker"},
            env_path=env_path,
        )


def test_script_scoped_control_environment_preserves_cm_rollback_target(tmp_path: Path) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text("DATABASE_URL=canonical-db\n", encoding="utf-8")
    child = guard._build_child_environment(
        expected_sha="a" * 40,
        script="scripts/prod_cm_rollback_version.sh",
        lock_fd=9,
        ambient={
            "CM_ROLLBACK_CONTENT_VERSION_ID": "version-123",
            "CM_RUNTIME_MODE_VALUE": "must-not-cross-script-boundary",
        },
        env_path=env_path,
    )
    assert child["CM_ROLLBACK_CONTENT_VERSION_ID"] == "version-123"
    assert "CM_RUNTIME_MODE_VALUE" not in child

    rollback = (ROOT / "scripts/prod_cm_rollback_version.sh").read_text(encoding="utf-8")
    assert "^v_[0-9a-f]{12,64}$" in rollback
    assert "<<'PY'" in rollback
    assert "content_version_id=target" in rollback
    assert 'content_version_id="${TARGET}"' not in rollback


def test_full_cluster_runtime_projection_matches_with_only_reviewed_node_local_differences(
    tmp_path: Path,
) -> None:
    node01_path = tmp_path / "node01.env"
    node02_path = tmp_path / "node02.env"
    common = "OPENAI_API_KEY=secret-value\nCM_RUNTIME_MODE=published\nRESEND_FROM_EMAIL=a@example.com\n"
    node01_path.write_text(common + "META_DELETION_NODE_ID=node01\nLINAS_HA_PEER_HOST=10.106.0.4\n", encoding="utf-8")
    node02_path.write_text(common + "META_DELETION_NODE_ID=node02\nLINAS_HA_PEER_HOST=10.106.0.3\n", encoding="utf-8")
    node01_path.chmod(0o600)
    node02_path.chmod(0o600)
    node01 = load_projection(node01_path, node_id="node01", owner_uid=os.geteuid(), owner_gid=os.getegid())
    node02 = load_projection(node02_path, node_id="node02", owner_uid=os.geteuid(), owner_gid=os.getegid())
    assert node01 == node02
    proof01 = projection_evidence(node01, node_id="node01", expected_sha="a" * 40)
    proof02 = projection_evidence(node02, node_id="node02", expected_sha="a" * 40)
    validate_evidence_pair(proof01, proof02, expected_sha="a" * 40)
    serialized = str(proof01)
    assert "secret-value" not in serialized
    assert "OPENAI_API_KEY" not in serialized


def test_full_cluster_runtime_projection_rejects_divergence_poison_and_extra_node_local_key(
    tmp_path: Path,
) -> None:
    base = tmp_path / "base.env"
    divergent = tmp_path / "divergent.env"
    base.write_text(
        "OPENAI_API_KEY=one\nMETA_DELETION_NODE_ID=node01\nLINAS_HA_PEER_HOST=10.106.0.4\n",
        encoding="utf-8",
    )
    divergent.write_text(
        "OPENAI_API_KEY=two\nMETA_DELETION_NODE_ID=node02\nLINAS_HA_PEER_HOST=10.106.0.3\n",
        encoding="utf-8",
    )
    base.chmod(0o600)
    divergent.chmod(0o600)
    left = load_projection(base, node_id="node01", owner_uid=os.geteuid(), owner_gid=os.getegid())
    right = load_projection(divergent, node_id="node02", owner_uid=os.geteuid(), owner_gid=os.getegid())
    with pytest.raises(RuntimeError, match="divergent"):
        validate_evidence_pair(
            projection_evidence(left, node_id="node01", expected_sha="a" * 40),
            projection_evidence(right, node_id="node02", expected_sha="a" * 40),
            expected_sha="a" * 40,
        )

    base.write_text(
        "OPENAI_API_KEY=one\nBASH_ENV=/tmp/hook\nMETA_DELETION_NODE_ID=node01\nLINAS_HA_PEER_HOST=10.106.0.4\n",
        encoding="utf-8",
    )
    with pytest.raises(RuntimeError, match="execution-control"):
        load_projection(base, node_id="node01", owner_uid=os.geteuid(), owner_gid=os.getegid())

    base.write_text(
        "OPENAI_API_KEY=one\nMETA_DELETION_NODE_ID=node01\nLINAS_HA_PEER_HOST=10.106.0.3\n",
        encoding="utf-8",
    )
    with pytest.raises(RuntimeError, match="node-local"):
        load_projection(base, node_id="node01", owner_uid=os.geteuid(), owner_gid=os.getegid())


def test_runtime_process_projection_detects_stale_application_value(tmp_path: Path) -> None:
    process = tmp_path / "environ"
    projection = {"OPENAI_API_KEY": "expected", "CM_RUNTIME_MODE": "published"}
    process.write_bytes(
        b"OPENAI_API_KEY=expected\0CM_RUNTIME_MODE=published\0"
        b"META_DELETION_NODE_ID=node01\0LINAS_HA_PEER_HOST=10.106.0.4\0"
        b"PYTHONUNBUFFERED=1\0PYTHONDONTWRITEBYTECODE=1\0"
        b"PATH=/opt/linasbot/venv/bin:/usr/local/bin:/usr/bin:/bin\0"
    )
    verify_process_environment(projection, process, node_id="node01")
    process.write_bytes(
        b"OPENAI_API_KEY=stale\0CM_RUNTIME_MODE=published\0"
        b"META_DELETION_NODE_ID=node01\0LINAS_HA_PEER_HOST=10.106.0.4\0"
        b"PYTHONUNBUFFERED=1\0PYTHONDONTWRITEBYTECODE=1\0"
        b"PATH=/opt/linasbot/venv/bin:/usr/local/bin:/usr/bin:/bin\0"
    )
    with pytest.raises(RuntimeError, match="stale or divergent"):
        verify_process_environment(projection, process, node_id="node01")


@pytest.mark.parametrize(
    "extra",
    [
        "WHATSAPP_DISABLED=true",
        "META_REGISTRY_BACKEND=file",
        "OPENAI_API_BASE=shadow",
        "SYSTEMD_LOG_LEVEL=debug",
    ],
)
def test_runtime_process_projection_rejects_extra_application_or_behavior_key(tmp_path: Path, extra: str) -> None:
    process = tmp_path / "environ"
    projection = {"OPENAI_API_KEY": "expected"}
    process.write_bytes(
        (
            "OPENAI_API_KEY=expected\0"
            "META_DELETION_NODE_ID=node01\0LINAS_HA_PEER_HOST=10.106.0.4\0"
            "PYTHONUNBUFFERED=1\0PYTHONDONTWRITEBYTECODE=1\0"
            "PATH=/opt/linasbot/venv/bin:/usr/local/bin:/usr/bin:/bin\0"
            f"{extra}\0"
        ).encode()
    )
    with pytest.raises(RuntimeError, match="unauthorized extra"):
        verify_process_environment(projection, process, node_id="node01")


def test_runtime_process_projection_accepts_only_closed_systemd_metadata(tmp_path: Path) -> None:
    process = tmp_path / "environ"
    projection = {"OPENAI_API_KEY": "expected"}
    process.write_bytes(
        b"OPENAI_API_KEY=expected\0META_DELETION_NODE_ID=node01\0"
        b"LINAS_HA_PEER_HOST=10.106.0.4\0PYTHONUNBUFFERED=1\0"
        b"PYTHONDONTWRITEBYTECODE=1\0"
        b"PATH=/opt/linasbot/venv/bin:/usr/local/bin:/usr/bin:/bin\0"
        b"HOME=/root\0USER=root\0LOGNAME=root\0SHELL=/bin/bash\0"
        b"LANG=C.UTF-8\0LC_ALL=C.UTF-8\0PWD=/opt/linasbot\0"
        b"INVOCATION_ID=0123456789abcdef0123456789abcdef\0"
        b"JOURNAL_STREAM=8:12345\0SYSTEMD_EXEC_PID=123\0"
    )
    verify_process_environment(projection, process, node_id="node01")


def test_runtime_process_projection_requires_complete_exact_verification_authority(
    tmp_path: Path,
) -> None:
    process = tmp_path / "environ"
    projection = {"OPENAI_API_KEY": "expected"}
    common = (
        "OPENAI_API_KEY=expected\0META_DELETION_NODE_ID=node01\0"
        "LINAS_HA_PEER_HOST=10.106.0.4\0PYTHONUNBUFFERED=1\0"
        "PYTHONDONTWRITEBYTECODE=1\0"
        "PATH=/opt/linasbot/venv/bin:/usr/local/bin:/usr/bin:/bin\0"
    )
    process.write_bytes((common + "LINAS_HA_VERIFY_ONLY=true\0").encode())
    with pytest.raises(RuntimeError, match="stale or divergent"):
        verify_process_environment(
            projection,
            process,
            node_id="node01",
            transient_release_sha="a" * 40,
        )
    process.write_bytes(
        (
            common + "LINAS_HA_VERIFY_ONLY=true\0" + f"LINAS_HA_VERIFY_RELEASE_SHA={'a' * 40}\0DISABLE_API_DOCS=1\0"
        ).encode()
    )
    verify_process_environment(
        projection,
        process,
        node_id="node01",
        transient_release_sha="a" * 40,
    )


@pytest.mark.parametrize("key", ["PYTHONPATH", "LD_PRELOAD", "LD_AUDIT", "BASH_ENV", "MALLOC_TRACE"])
def test_runtime_process_projection_rejects_unit_injected_execution_controls(tmp_path: Path, key: str) -> None:
    process = tmp_path / "environ"
    projection = {"OPENAI_API_KEY": "expected"}
    process.write_bytes(
        (
            "OPENAI_API_KEY=expected\0"
            "META_DELETION_NODE_ID=node01\0LINAS_HA_PEER_HOST=10.106.0.4\0"
            f"{key}=/outside\0PATH=/usr/bin\0"
        ).encode()
    )
    with pytest.raises(RuntimeError, match="execution-control"):
        verify_process_environment(projection, process, node_id="node01")


def test_guard_rejects_all_known_and_future_shaped_ha_transaction_artifacts(tmp_path: Path) -> None:
    volatile = tmp_path / "run-maintenance"
    for relative in (
        "bootstrap.active",
        "deploy.active",
        "deploy-node.active",
        "transaction.json",
        "controlled-failover.active",
        "registry-nfs-retire.active",
        "rekey/runtime.guard",
        "future-owner.active",
        "nested/journal.json",
    ):
        state = tmp_path / "state"
        path = state / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("active\n", encoding="utf-8")
        with pytest.raises(RuntimeError):
            guard._require_no_ha_transaction(state, volatile_maintenance=volatile)
        path.unlink()
        for parent in sorted(path.parents, key=lambda item: len(item.parts), reverse=True):
            if parent == state or parent == tmp_path:
                break
            parent.rmdir()

    state = tmp_path / "state"
    state.mkdir(exist_ok=True)
    volatile.write_text("active\n", encoding="utf-8")
    with pytest.raises(RuntimeError):
        guard._require_no_ha_transaction(state, volatile_maintenance=volatile)


def test_guard_rejects_dangling_active_symlink(tmp_path: Path) -> None:
    state = tmp_path / "state"
    state.mkdir()
    (state / "registry-nfs-retire.active").symlink_to(state / "missing")
    with pytest.raises(RuntimeError):
        guard._require_no_ha_transaction(state, volatile_maintenance=tmp_path / "volatile")


def test_canonical_env_cas_preserves_unrelated_lines_and_collapses_target_duplicates(tmp_path: Path) -> None:
    path = tmp_path / ".env"
    path.write_text("# keep\nA=one\nTARGET=old\nTARGET=stale\nREMOVE=gone\n", encoding="utf-8")
    path.chmod(0o600)
    lock_path = tmp_path / "live.lock"
    lock_fd = guard._open_lock(lock_path)
    try:
        atomic_update_env_cas(
            path,
            {"TARGET": "new", "SECOND": "two"},
            lock_fd=lock_fd,
            lock_path=lock_path,
            remove_keys=frozenset({"REMOVE"}),
            owner_uid=os.geteuid(),
            owner_gid=os.getegid(),
        )
    finally:
        os.close(lock_fd)
    assert path.read_text(encoding="utf-8") == "# keep\nA=one\nTARGET=new\nSECOND=two\n"
    assert path.stat().st_mode & 0o777 == 0o600


def test_canonical_env_cas_refuses_a_stale_read_write_clobber(tmp_path: Path) -> None:
    path = tmp_path / ".env"
    path.write_text("A=one\n", encoding="utf-8")
    path.chmod(0o600)

    def concurrent_writer() -> None:
        path.write_text("A=peer-change\n", encoding="utf-8")

    lock_path = tmp_path / "live.lock"
    lock_fd = guard._open_lock(lock_path)
    try:
        with pytest.raises(RuntimeError, match="changed during mutation"):
            atomic_update_env_cas(
                path,
                {"A": "ours"},
                lock_fd=lock_fd,
                lock_path=lock_path,
                owner_uid=os.geteuid(),
                owner_gid=os.getegid(),
                before_compare=concurrent_writer,
            )
    finally:
        os.close(lock_fd)
    assert path.read_text(encoding="utf-8") == "A=peer-change\n"


def test_canonical_env_cas_rejects_insecure_mode_and_symlink(tmp_path: Path) -> None:
    path = tmp_path / ".env"
    path.write_text("A=one\n", encoding="utf-8")
    path.chmod(0o644)
    lock_path = tmp_path / "live.lock"
    lock_fd = guard._open_lock(lock_path)
    try:
        with pytest.raises(RuntimeError):
            atomic_update_env_cas(
                path,
                {"A": "two"},
                lock_fd=lock_fd,
                lock_path=lock_path,
                owner_uid=os.geteuid(),
                owner_gid=os.getegid(),
            )
        path.chmod(0o600)
        link = tmp_path / "linked.env"
        link.symlink_to(path)
        with pytest.raises(OSError):
            atomic_update_env_cas(
                link,
                {"A": "two"},
                lock_fd=lock_fd,
                lock_path=lock_path,
                owner_uid=os.geteuid(),
                owner_gid=os.getegid(),
            )
    finally:
        os.close(lock_fd)


def test_canonical_env_cas_requires_the_actively_held_common_lock(tmp_path: Path) -> None:
    path = tmp_path / ".env"
    path.write_text("A=one\n", encoding="utf-8")
    path.chmod(0o600)
    lock_path = tmp_path / "live.lock"
    descriptor = os.open(lock_path, os.O_RDWR | os.O_CREAT, 0o600)
    os.set_inheritable(descriptor, True)
    try:
        with pytest.raises(RuntimeError, match="does not own"):
            atomic_update_env_cas(
                path,
                {"A": "two"},
                lock_fd=descriptor,
                lock_path=lock_path,
                owner_uid=os.geteuid(),
                owner_gid=os.getegid(),
            )
    finally:
        os.close(descriptor)


def test_global_lock_excludes_a_second_mutation_until_release(tmp_path: Path) -> None:
    lock_path = tmp_path / "live.lock"
    owner = guard._open_lock(lock_path)
    contender_started = threading.Event()
    contender_acquired = threading.Event()
    contender_fd: list[int] = []

    def contend() -> None:
        contender_started.set()
        descriptor = guard._open_lock(lock_path)
        contender_fd.append(descriptor)
        contender_acquired.set()

    thread = threading.Thread(target=contend, daemon=True)
    thread.start()
    assert contender_started.wait(timeout=1)
    time.sleep(0.1)
    assert not contender_acquired.is_set()
    os.close(owner)
    assert contender_acquired.wait(timeout=2)
    os.close(contender_fd.pop())
    thread.join(timeout=2)


def _commit_fixture_repo(repo: Path, script_name: str = "scripts/prod_cm_backup.sh") -> str:
    script = repo / script_name
    script.parent.mkdir(parents=True)
    script.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    subprocess.run(["git", "-C", str(repo), "add", "."], check=True)
    env = {
        **os.environ,
        "GIT_AUTHOR_NAME": "test",
        "GIT_AUTHOR_EMAIL": "test@example.invalid",
        "GIT_COMMITTER_NAME": "test",
        "GIT_COMMITTER_EMAIL": "test@example.invalid",
    }
    subprocess.run(["git", "-C", str(repo), "commit", "-q", "-m", "fixture"], check=True, env=env)
    return subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def test_exact_release_gate_rejects_dirty_or_replaced_deployed_script(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    sha = _commit_fixture_repo(repo)
    script = guard._require_exact_release(repo, sha, "scripts/prod_cm_backup.sh")
    assert script.is_file()
    script.write_text("#!/usr/bin/env bash\nexit 9\n", encoding="utf-8")
    with pytest.raises(RuntimeError):
        guard._require_exact_release(repo, sha, "scripts/prod_cm_backup.sh")


def test_direct_registry_writers_share_lock_and_reject_ha_collision(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    script_name = "scripts/ha/import_meta_registry_to_postgres.py"
    sha = _commit_fixture_repo(repo, script_name)
    env_path = repo / ".env"
    env_path.write_text("DATABASE_URL=postgresql://db.invalid/app\n", encoding="utf-8")
    env_path.chmod(0o600)
    state = tmp_path / "state"
    state.mkdir()
    lock_path = tmp_path / "live.lock"
    volatile = tmp_path / "volatile"
    monkeypatch.setattr(guard.os, "geteuid", lambda: 0)
    monkeypatch.setattr(guard.os, "getegid", lambda: 0)
    monkeypatch.setattr(guard.os, "fchown", lambda *_args: None)

    owner = guard.acquire_direct_production_mutation_lock(
        expected_sha=sha,
        script=script_name,
        env_path=env_path,
        repo_dir=repo,
        canonical_env=env_path,
        state_root=state,
        volatile_maintenance=volatile,
        lock_path=lock_path,
        owner_uid=os.getuid(),
        owner_gid=os.getgid(),
    )
    acquired = threading.Event()
    contender_fd: list[int] = []

    def contend() -> None:
        contender_fd.append(
            guard.acquire_direct_production_mutation_lock(
                expected_sha=sha,
                script=script_name,
                env_path=env_path,
                repo_dir=repo,
                canonical_env=env_path,
                state_root=state,
                volatile_maintenance=volatile,
                lock_path=lock_path,
                owner_uid=os.getuid(),
                owner_gid=os.getgid(),
            )
        )
        acquired.set()

    thread = threading.Thread(target=contend, daemon=True)
    thread.start()
    time.sleep(0.1)
    assert not acquired.is_set()
    os.close(owner)
    assert acquired.wait(timeout=2)
    os.close(contender_fd.pop())
    thread.join(timeout=2)

    (state / "registry-nfs-retire.active").write_text("active\n", encoding="utf-8")
    with pytest.raises(RuntimeError, match="HA transaction"):
        guard.acquire_direct_production_mutation_lock(
            expected_sha=sha,
            script=script_name,
            env_path=env_path,
            repo_dir=repo,
            canonical_env=env_path,
            state_root=state,
            volatile_maintenance=volatile,
            lock_path=lock_path,
            owner_uid=os.getuid(),
            owner_gid=os.getgid(),
        )


def test_exact_release_gate_rejects_untracked_or_ignored_runtime_source(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    sha = _commit_fixture_repo(repo)
    untracked = repo / "services/shadow.py"
    untracked.parent.mkdir()
    untracked.write_text("raise RuntimeError('shadow')\n", encoding="utf-8")
    with pytest.raises(RuntimeError, match="shadow the authorized release"):
        guard._require_exact_release(repo, sha, "scripts/prod_cm_backup.sh")

    untracked.unlink()
    (repo / ".gitignore").write_text("services/ignored.py\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "add", ".gitignore"], check=True)
    env = {
        **os.environ,
        "GIT_AUTHOR_NAME": "test",
        "GIT_AUTHOR_EMAIL": "test@example.invalid",
        "GIT_COMMITTER_NAME": "test",
        "GIT_COMMITTER_EMAIL": "test@example.invalid",
    }
    subprocess.run(["git", "-C", str(repo), "commit", "-q", "-m", "ignore fixture"], check=True, env=env)
    sha = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    (repo / "services/ignored.py").write_text("raise RuntimeError('ignored')\n", encoding="utf-8")
    with pytest.raises(RuntimeError, match="shadow the authorized release"):
        guard._require_exact_release(repo, sha, "scripts/prod_cm_backup.sh")


def test_mutating_entrypoints_require_the_guard_and_use_only_the_canonical_env() -> None:
    scripts = (
        "prod_apply_copilot_v2_flags.sh",
        "prod_apply_dashboard_auth.sh",
        "prod_apply_model_routing_policy.sh",
        "prod_apply_openai_api_key.sh",
        "prod_apply_resend_secrets.sh",
        "prod_apply_whatsapp_cloud_phase1_flags.sh",
        "prod_cm_apply_flags.sh",
        "prod_cm_set_linas_bridge_flag.sh",
        "prod_whatsapp_cloud_migrate.sh",
    )
    for name in scripts:
        source = (ROOT / "scripts" / name).read_text(encoding="utf-8")
        assert "linas_require_production_mutation_guard" in source, name
        assert "linaslaserbot-2.7.22/.env" not in source, name
    for name in (
        "prod_apply_copilot_v2_flags.sh",
        "prod_apply_dashboard_auth.sh",
        "prod_apply_model_routing_policy.sh",
        "prod_apply_openai_api_key.sh",
        "prod_apply_resend_secrets.sh",
        "prod_apply_whatsapp_cloud_phase1_flags.sh",
        "prod_cm_apply_flags.sh",
        "prod_cm_set_linas_bridge_flag.sh",
    ):
        source = (ROOT / "scripts" / name).read_text(encoding="utf-8")
        assert "production_env_cas" in source, name


def test_shared_database_and_cm_data_entrypoints_reject_direct_unguarded_invocation() -> None:
    for name in (
        "prod_wa_connection_source_migrate.sh",
        "prod_whatsapp_cloud_phase1_ops.sh",
        "prod_whatsapp_cloud_migrate.sh",
        "prod_cm_backup.sh",
        "prod_cm_migrate_and_validate.sh",
        "prod_cm_publish.sh",
        "prod_cm_publish_faq_only.sh",
        "prod_cm_rollback_version.sh",
        "prod_cm_generic_tenant_proof.sh",
        "prod_cm_import_prices.sh",
        "prod_cm_repair_linas_prices_publish.sh",
    ):
        source = (ROOT / "scripts" / name).read_text(encoding="utf-8")
        assert "linas_require_production_mutation_guard" in source, name


def test_wa_schema_migration_runs_only_from_the_deployed_tree_and_canonical_env() -> None:
    workflow = (WORKFLOWS / "wa-app-review-connection-source-migrate.yml").read_text(encoding="utf-8")
    script = (ROOT / "scripts/prod_wa_connection_source_migrate.sh").read_text(encoding="utf-8")
    assert "SOURCE_REF" not in workflow
    assert "origin/main" not in workflow
    assert "git show" not in workflow
    assert "source /opt/linasbot/.env" not in script
    assert "dotenv_values(ENV_PATH, interpolate=False)" in script
    assert "LINAS_WHATSAPP_DATABASE_URL" in script
    assert "MIGRATE_APPLY" in script
    assert "APPLY_WA_CONNECTION_SOURCE_MIGRATION" in script
