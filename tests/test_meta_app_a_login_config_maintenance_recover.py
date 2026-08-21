"""Safety contract for the bound App A login-config maintenance recovery."""

from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "meta-app-a-login-config-maintenance-recover.yml"
PINNED_SSH = "appleboy/ssh-action@7eaf76671a0d7eec5d98ee897acda4f968735a17"
BASELINE_SHA = "a2ba8d63265504ded18b6d4bd70219628c4d8533"
OLD_CONFIG_ID = "1369663304545819"
CONFIRM = f"RECOVER_APP_A_LOGIN_CONFIG_MAINTENANCE_{BASELINE_SHA}"
REDIRECT = "https://www.linasaibot.com/oauth/meta/callback"


def _payload() -> dict:
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))


def _script() -> str:
    script = _payload()["jobs"]["recover"]["steps"][0]["with"]["script"]
    assert isinstance(script, str)
    return script


def test_recovery_workflow_is_main_only_protected_and_narrowly_bound() -> None:
    source = WORKFLOW.read_text(encoding="utf-8")
    payload = _payload()
    job = payload["jobs"]["recover"]
    trigger = payload[True]
    assert trigger == {
        "workflow_dispatch": {
            "inputs": {
                "BASELINE_SHA": {
                    "description": f"Must equal {BASELINE_SHA}",
                    "required": True,
                    "type": "string",
                },
                "EXPECTED_OLD_CONFIG_ID": {
                    "description": f"Must equal {OLD_CONFIG_ID}",
                    "required": True,
                    "type": "string",
                },
                "CONFIRM": {
                    "description": f"Type {CONFIRM}",
                    "required": True,
                    "type": "string",
                },
            }
        }
    }
    assert "on:\n  workflow_dispatch:" in source
    assert "push:" not in source
    assert "pull_request:" not in source
    assert payload["concurrency"] == {
        "group": "meta-social-cutover",
        "cancel-in-progress": False,
    }
    assert job["environment"] == "meta-social-cutover"
    assert "github.ref == 'refs/heads/main'" in str(job["if"])
    assert BASELINE_SHA in str(job["if"])
    assert OLD_CONFIG_ID in str(job["if"])
    assert CONFIRM in str(job["if"])
    assert PINNED_SSH in source
    assert "appleboy/ssh-action@v" not in source
    assert "script_stop: false" in source
    assert "script_stop: true" not in source
    assert "EXPECTED_RELEASE_SHA: ${{ github.sha }}" not in source
    assert source.count(BASELINE_SHA) >= 4
    assert source.count(OLD_CONFIG_ID) >= 3


def test_recovery_script_proves_baseline_then_unlinks_in_fail_open_order() -> None:
    script = _script()
    source = WORKFLOW.read_text(encoding="utf-8")
    assert 'test "$(id -u)" -eq 0 && test "$(id -g)" -eq 0' in script
    assert "exec 9>/run/lock/linasbot-meta-live.lock" in script
    assert "flock -x 9" in script
    assert "export LINAS_PRODUCTION_MUTATION_LOCK_FD=9" in script
    assert "REPO_DIR=/opt/linasbot" in script
    assert 'PEER_HOST="${LINAS_HA_PEER_HOST:-10.106.0.4}"' in script
    assert "MAINTENANCE_FILE=/run/linasbot-maintenance" in script
    assert "META_HA_STATE_ROOT=/var/lib/linasbot/meta-ha" in script
    assert "0:0:600" in script
    assert "test ! -s" in script
    assert "transaction.json" in script
    assert "env.before" in script
    assert "workers.before.json" in script
    assert "prestage.authority.json" in script
    assert "--recover-only" in script
    assert "[meta-ha-env] recovery_required=false" in script
    assert OLD_CONFIG_ID in script
    assert REDIRECT in script
    assert "os.fsync(fd)" in script
    assert "atomic_update_env" not in script
    assert "systemctl restart" not in script
    assert "git checkout" not in script
    assert "git fetch" not in source
    assert "git show" not in source
    unlink_start = script.index("PEER_UNLINK=")
    peer_volatile = script.index("'$MAINTENANCE_FILE'", unlink_start)
    peer_persistent = script.index("'$PERSISTENT_MAINTENANCE_FILE'", peer_volatile)
    local_volatile = script.index('fsync_unlink "$MAINTENANCE_FILE"')
    local_persistent = script.index('fsync_unlink "$PERSISTENT_MAINTENANCE_FILE"')
    ready = script.index('http://127.0.0.1:8003/api/ready)" = "200"')
    verify = script.index('verify_meta_release_ha.sh" "$REQUIRED_SHA"')
    public_lb = script.index("https://www.linasaibot.com/api/ready")
    assert peer_volatile < peer_persistent < local_volatile < local_persistent < ready < verify < public_lb
    assert script.index("--recover-only") < unlink_start
    assert source.count("verify_meta_release_ha.sh") == 1
    assert "atomic_update_env" not in source
    assert "META_APP_A_FACEBOOK_LOGIN_CONFIG_ID=" not in script.split("dotenv_values", 1)[0]
