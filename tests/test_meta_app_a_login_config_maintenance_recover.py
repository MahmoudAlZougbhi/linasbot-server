"""Safety contract for resuming the approved App A login-config transaction."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "meta-app-a-login-config-maintenance-recover.yml"
PINNED_SSH = "appleboy/ssh-action@7eaf76671a0d7eec5d98ee897acda4f968735a17"
BASELINE_SHA = "a2ba8d63265504ded18b6d4bd70219628c4d8533"
OLD_CONFIG_ID = "1369663304545819"
NEW_CONFIG_ID = "1021840664011530"
FAILED_RUN_ID = "32527312818"
CONFIRM = f"RECOVER_APP_A_LOGIN_CONFIG_MAINTENANCE_{BASELINE_SHA}"
REDIRECT = "https://www.linasaibot.com/oauth/meta/callback"
CONFLICTS = (
    "transaction.json",
    "env.before",
    "workers.before.json",
    "prestage.authority.json",
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


def test_recovery_remote_script_parses_and_resumes_deployed_transaction() -> None:
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
    for artifact in CONFLICTS:
        assert artifact in script
    assert "os.unlink" not in script
    assert "atomic_update_env" not in source
    assert "systemctl restart" not in script
    assert "git checkout" not in source
    prechecks_done = script.index('test "$CONFIG_PROOF" = "$PEER_PROOF"')
    arm = script.index("MAINTENANCE_ARMED=true")
    trap = script.index("trap fail_closed_cleanup EXIT")
    recover = script.index("--recover-only")
    recovery_false = script.index("[meta-ha-env] recovery_required=false")
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
        prechecks_done
        < arm
        < trap
        < recover
        < recovery_false
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
    assert script.index('= "503"') < trap
