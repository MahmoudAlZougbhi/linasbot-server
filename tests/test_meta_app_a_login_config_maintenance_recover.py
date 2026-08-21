"""Safety contract for resuming the approved App A login-config transaction."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import subprocess
import sys
from pathlib import Path
from textwrap import dedent

import yaml

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "meta-app-a-login-config-maintenance-recover.yml"
SYNC = ROOT / "scripts" / "ha" / "sync_meta_env_to_peer.py"
PINNED_SSH = "appleboy/ssh-action@7eaf76671a0d7eec5d98ee897acda4f968735a17"
BASELINE_SHA = "a2ba8d63265504ded18b6d4bd70219628c4d8533"
OLD_CONFIG_ID = "1369663304545819"
NEW_CONFIG_ID = "1021840664011530"
FAILED_RUN_ID = "32527312818"
FAILED_RUN_START = "1787346694"
CONFIRM = f"RECOVER_APP_A_LOGIN_CONFIG_MAINTENANCE_{BASELINE_SHA}"
REDIRECT = "https://www.linasaibot.com/oauth/meta/callback"
UNRELATED_CONFLICTS = (
    "bootstrap.active",
    "bootstrap.coordinator.json",
    "deploy.active",
    "deploy-node.active",
    "controlled-failover.active",
    "registry-nfs-retire.active",
    "python-runtime-provision.active",
    "python-runtime-provision.coordinator.json",
    "rekey/runtime.guard",
)
SYNC_ARTIFACTS = (
    "transaction.json",
    "env.before",
    "workers.before.json",
    "prestage.authority.json",
)
RECOVER_TERMINALS = (
    "[meta-ha-env] recovery_required=false",
    "[meta-ha-env] recovered_worker_finalization=true",
    "[meta-ha-env] recovered_prestage_workers=true",
    "[meta-ha-env] recovered_pre_quiescence_backup=true",
    "[meta-ha-env] recovered_outcome=committed",
    "[meta-ha-env] recovered_outcome=rolled_back",
)


def _payload() -> dict:
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))


def _job() -> dict:
    return _payload()["jobs"]["recover"]


def _step(name: str) -> dict:
    return next(step for step in _job()["steps"] if step["name"] == name)


def _script() -> str:
    script = _step("Resume the approved App A login-config transaction")["with"]["script"]
    assert isinstance(script, str)
    return script


def _local_admission_code() -> str:
    script = _script()
    start = script.index("<<'PY'\n") + len("<<'PY'\n")
    end = script.index("\nPY\n", start)
    return dedent(script[start:end])


def _hmac_meta(env_text: str) -> str:
    values = {}
    for line in env_text.splitlines():
        if "=" not in line or line.lstrip().startswith("#"):
            continue
        key, value = line.split("=", 1)
        values[key] = value
    meta = {key: value for key, value in values.items() if key.startswith("META_") and key != "META_DELETION_NODE_ID"}
    payload = json.dumps(meta, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return hmac.new(BASELINE_SHA.encode("ascii"), payload, hashlib.sha256).hexdigest()


def test_recovery_workflow_is_main_only_protected_and_bound() -> None:
    source = WORKFLOW.read_text(encoding="utf-8")
    job = _job()
    trigger = _payload()[True]
    assert job["if"] == "github.ref == 'refs/heads/main'"
    assert job["environment"] == "meta-social-cutover"
    assert _payload()["concurrency"] == {
        "group": "meta-social-cutover",
        "cancel-in-progress": False,
    }
    assert trigger["workflow_dispatch"]["inputs"]["FAILED_RUN_ID"]["required"] is True
    assert trigger["workflow_dispatch"]["inputs"]["CONTROL_SHA"]["required"] is True
    assert trigger["workflow_dispatch"]["inputs"]["CONFIRM"]["description"].endswith(CONFIRM)
    assert PINNED_SSH in source
    assert "script_stop: false" in source
    assert "script_stop: true" not in source
    assert "EXPECTED_RELEASE_SHA: ${{ github.sha }}" not in source
    assert "REQUIRED_CONTROL_SHA: ${{ github.sha }}" in source
    assert 'META_HA_STAGE_ONLY: "true"' in source
    assert FAILED_RUN_ID in source
    assert FAILED_RUN_START in source
    assert "1787346728" not in source
    assert BASELINE_SHA in source
    assert OLD_CONFIG_ID in source
    assert NEW_CONFIG_ID in source
    assert "os.unlink" not in source
    assert "fsync_unlink" not in source


def test_wrong_recovery_inputs_fail_the_protected_job(tmp_path: Path) -> None:
    gate = _step("Reject mismatched recovery inputs")["run"]
    env = {
        **os.environ,
        "BASELINE_SHA": BASELINE_SHA,
        "EXPECTED_OLD_CONFIG_ID": OLD_CONFIG_ID,
        "FAILED_RUN_ID": FAILED_RUN_ID,
        "CONTROL_SHA": "deadbeef",
        "CONFIRM": CONFIRM,
        "REQUIRED_CONTROL_SHA": "cafebabe",
        "META_APP_A_FACEBOOK_LOGIN_CONFIG_ID": NEW_CONFIG_ID,
    }
    rejected = subprocess.run(
        ["/bin/bash", "-c", gate],
        check=False,
        capture_output=True,
        text=True,
        env=env,
        cwd=tmp_path,
    )
    assert rejected.returncode != 0
    accepted = subprocess.run(
        ["/bin/bash", "-c", gate],
        check=False,
        capture_output=True,
        text=True,
        env={**env, "CONTROL_SHA": "cafebabe"},
        cwd=tmp_path,
    )
    assert accepted.returncode == 0
    bad_secret = subprocess.run(
        ["/bin/bash", "-c", gate],
        check=False,
        capture_output=True,
        text=True,
        env={**env, "CONTROL_SHA": "cafebabe", "META_APP_A_FACEBOOK_LOGIN_CONFIG_ID": OLD_CONFIG_ID},
        cwd=tmp_path,
    )
    assert bad_secret.returncode != 0


def test_recover_only_accepts_documented_terminals() -> None:
    script = _script()
    sync_source = SYNC.read_text(encoding="utf-8")
    case = script[script.index('case "$RECOVERY_TERMINAL" in') : script.index("esac")]
    for terminal in RECOVER_TERMINALS:
        assert f'print("{terminal}")' in sync_source or f'print(f"{terminal.split("=")[0]}={{outcome}}")' in sync_source
        assert terminal in case
    assert 'print("[meta-ha-env] recovery_required=false")' in sync_source
    assert 'print("[meta-ha-env] recovered_worker_finalization=true")' in sync_source
    assert 'print("[meta-ha-env] recovered_prestage_workers=true")' in sync_source
    assert 'print("[meta-ha-env] recovered_pre_quiescence_backup=true")' in sync_source
    assert 'print(f"[meta-ha-env] recovered_outcome={outcome}")' in sync_source
    assert 'return "committed"' in sync_source or 'return "committed"' in sync_source
    assert 'return "rolled_back"' in sync_source or 'return "rolled_back"' in sync_source


def test_post_recover_admits_old_and_new_config(tmp_path: Path) -> None:
    code = _local_admission_code()
    assert "sys.argv[2]" in code and "sys.argv[3]" in code
    assert "print(" in code
    assert OLD_CONFIG_ID not in code
    assert NEW_CONFIG_ID not in code

    def run_env(config_id: str) -> subprocess.CompletedProcess[str]:
        env_path = tmp_path / f"{config_id}.env"
        env_path.write_text(
            f"META_APP_A_FACEBOOK_LOGIN_CONFIG_ID={config_id}\n"
            f"META_OAUTH_REDIRECT_URI={REDIRECT}\n"
            "META_HA_LB_DRAIN_SECONDS=45\n",
            encoding="utf-8",
        )
        return subprocess.run(
            [sys.executable, "-c", code, str(env_path), OLD_CONFIG_ID, NEW_CONFIG_ID, REDIRECT, BASELINE_SHA],
            check=False,
            capture_output=True,
            text=True,
        )

    no_state = run_env(OLD_CONFIG_ID)
    rolled_back = run_env(OLD_CONFIG_ID)
    committed = run_env(NEW_CONFIG_ID)
    rejected = run_env("9999999999999999")
    assert no_state.returncode == 0, no_state.stderr
    assert rolled_back.returncode == 0, rolled_back.stderr
    assert committed.returncode == 0, committed.stderr
    assert rejected.returncode != 0
    assert "admitted recover state" in rejected.stderr
    assert no_state.stdout.strip() == _hmac_meta(
        f"META_APP_A_FACEBOOK_LOGIN_CONFIG_ID={OLD_CONFIG_ID}\n"
        f"META_OAUTH_REDIRECT_URI={REDIRECT}\n"
        "META_HA_LB_DRAIN_SECONDS=45\n"
    )
    assert committed.stdout.strip() == _hmac_meta(
        f"META_APP_A_FACEBOOK_LOGIN_CONFIG_ID={NEW_CONFIG_ID}\n"
        f"META_OAUTH_REDIRECT_URI={REDIRECT}\n"
        "META_HA_LB_DRAIN_SECONDS=45\n"
    )
    assert OLD_CONFIG_ID not in no_state.stdout
    assert NEW_CONFIG_ID not in committed.stdout


def test_recovery_remote_script_is_rerunnable_and_ordered() -> None:
    script = _script()
    source = WORKFLOW.read_text(encoding="utf-8")
    parsed = subprocess.run(
        ["/bin/bash", "-n"],
        input=script,
        check=False,
        capture_output=True,
        text=True,
    )
    assert parsed.returncode == 0, parsed.stderr
    assert 'test "$(id -u)" -eq 0 && test "$(id -g)" -eq 0' in script
    assert "exec 9>/run/lock/linasbot-meta-live.lock" in script
    assert "export LINAS_PRODUCTION_MUTATION_LOCK_FD=9" in script
    assert "fail_closed_cleanup() {" in script
    assert "HA maintenance retained after uncertain transaction" in script
    assert REDIRECT in script
    assert 'CONFLICT_ARTIFACTS="' in script
    conflict_line = next(line for line in script.splitlines() if line.strip().startswith("CONFLICT_ARTIFACTS="))
    sync_line = next(line for line in script.splitlines() if line.strip().startswith("SYNC_ARTIFACTS="))
    for artifact in UNRELATED_CONFLICTS:
        assert artifact in conflict_line
        assert artifact in script
    for artifact in SYNC_ARTIFACTS:
        assert artifact not in conflict_line
        assert artifact in sync_line
    assert "os.unlink" not in script
    assert "atomic_update_env" not in source
    assert "systemctl restart" not in script
    assert "git checkout" not in source
    assert "DRAIN_SECONDS=" in script
    assert "META_HA_LB_DRAIN_SECONDS" in script
    assert FAILED_RUN_START in script
    ready_503 = script.index('= "503"')
    arm = script.index("MAINTENANCE_ARMED=true")
    trap = script.index("trap fail_closed_cleanup EXIT")
    recover = script.index("--recover-only")
    terminal = script.index('case "$RECOVERY_TERMINAL" in')
    sync_absent = script.index("for artifact in $SYNC_ARTIFACTS")
    admitted = script.index("login config or redirect is not an admitted recover state")
    parity = script.index('test "$CONFIG_PROOF" = "$PEER_PROOF"')
    release_only = script.index("cluster-release-only")
    register = script.index("--register-prestage-backup")
    backup = script.index('ENV_BACKUP="$META_HA_STATE_ROOT/env.before"')
    apply_script = script.index("prod_apply_meta_app_a_login_config.sh")
    sync = script.index("--local-prestage-backup")
    finalize = script.index("--finalize", sync)
    strict = script.rindex('verify_meta_release_ha.sh" "$REQUIRED_SHA"')
    complete = script.index("TRANSACTION_COMPLETE=true")
    disarmed = script.rindex("MAINTENANCE_ARMED=false")
    assert (
        ready_503
        < arm
        < trap
        < recover
        < terminal
        < sync_absent
        < admitted
        < parity
        < release_only
        < register
        < backup
        < apply_script
        < sync
        < finalize
        < strict
        < complete
        < disarmed
    )
    assert source.count("verify_meta_release_ha.sh") == 2
    assert script.index("for artifact in $CONFLICT_ARTIFACTS") < trap
