"""Safety contract for one-incident orphan-maintenance recovery."""

from __future__ import annotations

import ast
import os
import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "meta-app-a-login-config-maintenance-recover.yml"
PINNED_SSH = "appleboy/ssh-action@7eaf76671a0d7eec5d98ee897acda4f968735a17"
BASELINE_SHA = "a2ba8d63265504ded18b6d4bd70219628c4d8533"
OLD_CONFIG_ID = "1369663304545819"
NEW_CONFIG_ID = "1021840664011530"
FAILED_RUN_ID = "32527312818"
FAILED_RUN_START = "1787346694"
MARKER_PROVENANCE = "1787350550"
CONFIRM = f"RECOVER_ORPHAN_MAINTENANCE_{BASELINE_SHA}"
REDIRECT = "https://www.linasaibot.com/oauth/meta/callback"
PUBLIC_READY = "https://www.linasaibot.com/api/ready"
DRONE_STOP = (
    "DRONE_SSH_PREV_COMMAND_EXIT_CODE=$? ; "
    "if [ $DRONE_SSH_PREV_COMMAND_EXIT_CODE -ne 0 ]; then "
    "exit $DRONE_SSH_PREV_COMMAND_EXIT_CODE; fi;"
)
CONFLICTS = (
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
SYNCS = (
    "transaction.json",
    "env.before",
    "workers.before.json",
    "prestage.authority.json",
)
DROPINS = (
    "90-meta-ha-maintenance.conf",
    "92-meta-controlled-failover.conf",
    "95-linasbot-credential-rekey-guard.conf",
)
HASH92 = "ccd1d423d6624d28fc7f8984f8fb13824ece04af5a140e770d2c2ffd67b537e9"
HASH93 = "25c89c8dc130caacd7b8e1861b07c6c829444a860bca8d298e560133380aff07"
HASH95 = "b47ed84bb59ce2569c5fd4b936faa2d3fddf0fb408492b1d60ba820a463f3278"
FORBIDDEN = (
    "--recover-only",
    "--register-prestage-backup",
    "--finalize",
    "sync_meta_env_to_peer",
    "prod_apply_meta_app_a_login_config.sh",
    "atomic_update_env",
    "systemctl restart",
    "systemctl reload",
    "git checkout",
    "git reset",
    "git pull",
    "git fetch",
    "META_HA_STAGE_ONLY",
    NEW_CONFIG_ID,
    "secrets.META_APP_A_FACEBOOK_LOGIN_CONFIG_ID",
)


def _payload() -> dict:
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))


def _job() -> dict:
    return _payload()["jobs"]["recover"]


def _step(name: str) -> dict:
    return next(step for step in _job()["steps"] if step["name"] == name)


def _script() -> str:
    script = _step("Recover orphaned HA maintenance markers")["with"]["script"]
    assert isinstance(script, str)
    return script


def _helper_python() -> str:
    script = _script()
    marker = "HELPER=$(cat <<'PY'\n"
    start = script.index(marker) + len(marker)
    return script[start : script.index("\nPY\n", start)]


def _drone_ssh_script_stop(script: str) -> str:
    commands: list[str] = []
    for raw in script.split("\n"):
        cmd = raw.strip()
        if not cmd:
            continue
        commands.append(cmd)
        if not cmd.endswith("\\"):
            commands.append(DRONE_STOP)
    return "\n".join(commands) + "\n"


def test_recovery_workflow_is_main_only_protected_and_bound() -> None:
    source = WORKFLOW.read_text(encoding="utf-8")
    job = _job()
    trigger = _payload()[True]
    assert "if" not in job
    assert job["environment"] == "meta-social-cutover"
    assert _payload()["concurrency"] == {"group": "meta-social-cutover", "cancel-in-progress": False}
    assert _payload()["permissions"] == {"contents": "read"}
    for key in ("BASELINE_SHA", "EXPECTED_OLD_CONFIG_ID", "FAILED_RUN_ID", "CONTROL_SHA", "CONFIRM"):
        assert trigger["workflow_dispatch"]["inputs"][key]["required"] is True
    assert trigger["workflow_dispatch"]["inputs"]["CONFIRM"]["description"].endswith(CONFIRM)
    assert PINNED_SSH in source
    assert "script_stop: false" in source
    assert "script_stop: true" not in source
    assert "EXPECTED_RELEASE_SHA: ${{ github.sha }}" not in source
    assert "REQUIRED_CONTROL_SHA: ${{ github.sha }}" in source
    assert "GITHUB_REF_VALUE: ${{ github.ref }}" in source
    assert FAILED_RUN_ID in source
    assert FAILED_RUN_START in source
    assert MARKER_PROVENANCE in source
    assert BASELINE_SHA in source
    assert OLD_CONFIG_ID in source
    assert REDIRECT in source
    assert PUBLIC_READY in source
    for fragment in FORBIDDEN:
        assert fragment not in source, fragment


def test_wrong_recovery_inputs_fail_red(tmp_path: Path) -> None:
    gate = _step("Reject mismatched recovery inputs")["run"]
    good = {
        **os.environ,
        "BASELINE_SHA": BASELINE_SHA,
        "EXPECTED_OLD_CONFIG_ID": OLD_CONFIG_ID,
        "FAILED_RUN_ID": FAILED_RUN_ID,
        "CONTROL_SHA": "cafebabe",
        "CONFIRM": CONFIRM,
        "REQUIRED_CONTROL_SHA": "cafebabe",
        "GITHUB_REF_VALUE": "refs/heads/main",
    }

    def run(env: dict[str, str]) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["/bin/bash", "-c", gate], check=False, capture_output=True, text=True, env=env, cwd=tmp_path
        )

    assert run(good).returncode == 0
    for env in (
        {**good, "CONTROL_SHA": "deadbeef"},
        {**good, "GITHUB_REF_VALUE": "refs/heads/fix/branch"},
        {**good, "BASELINE_SHA": "0" * 40},
        {**good, "FAILED_RUN_ID": "1"},
        {**good, "EXPECTED_OLD_CONFIG_ID": NEW_CONFIG_ID},
        {**good, "CONFIRM": f"RECOVER_APP_A_LOGIN_CONFIG_MAINTENANCE_{BASELINE_SHA}"},
    ):
        assert run(env).returncode != 0


def test_extracted_remote_script_and_helper_are_syntactically_valid() -> None:
    script = _script()
    parsed = subprocess.run(["/bin/bash", "-n"], input=script, check=False, capture_output=True, text=True)
    assert parsed.returncode == 0, parsed.stderr
    ast.parse(_helper_python())
    assert "set -euo pipefail" in script.splitlines()[0]
    assert "exec 9>/run/lock/linasbot-meta-live.lock" in script
    assert "export LINAS_PRODUCTION_MUTATION_LOCK_FD=9" in script
    assert script.count("exec 9>") == 1
    assert script.count("flock -x 9") == 1


def test_script_stop_rewrite_would_corrupt_helper_heredoc() -> None:
    rewritten = _drone_ssh_script_stop(_script())
    start = rewritten.index("HELPER=$(cat <<'PY'\n") + len("HELPER=$(cat <<'PY'\n")
    helper = rewritten[start : rewritten.index("\nPY\n", start)]
    assert "DRONE_SSH_PREV_COMMAND_EXIT_CODE" in helper
    try:
        ast.parse(helper)
    except SyntaxError:
        return
    raise AssertionError("script_stop rewrite must corrupt the helper heredoc")


def test_two_node_source_audit_uses_corrected_pathspec() -> None:
    script = _script()
    helper = _helper_python()
    assert ":(top,glob)*.py" in helper
    assert 'ls-files", "-z", "--others", "--exclude-standard"' in helper
    assert '"--ignored"' in helper
    assert 'out.split(b"\\0")' in helper
    assert "found+=" not in script
    assert "hp audit" in script
    assert script.count("hp audit") >= 2
    assert "hp node" in script and "node01" in script and "node02" in script


def test_precheck_invariants_bind_old_config_and_exact_lists() -> None:
    script = _script()
    source = WORKFLOW.read_text(encoding="utf-8")
    assert "login config or redirect is not the exact old Meta state" in script
    assert "live process Meta environment does not match .env" in _helper_python()
    assert "META_DELETION_NODE_ID" in script
    conflict_line = next(line for line in script.splitlines() if "CONFLICTS=" in line)
    sync_line = next(line for line in script.splitlines() if line.strip().startswith("SYNCS="))
    dropin_line = next(line for line in script.splitlines() if line.strip().startswith("DROPINS="))
    for artifact in CONFLICTS:
        assert artifact in conflict_line
        assert artifact not in sync_line
    for artifact in SYNCS:
        assert artifact in sync_line
        assert artifact not in conflict_line
    for dropin in DROPINS:
        assert dropin in dropin_line
    assert "orphan-maintenance-recovery.phase" in script
    assert "linas-orphan-maintenance-recovery-v1" in script
    assert "0:0:600" in script
    assert source.count("verify_meta_release_ha.sh") == 1
    assert "cluster-release-only" not in source


def test_canonical_90_absent_and_92_93_95_static_hashed_on_api_and_template() -> None:
    helper = _helper_python()
    script = _script()
    body = helper[helper.index('elif cmd == "dropins":') : helper.index('elif cmd == "write-phase":')]
    assert HASH92 in body and HASH93 in body and HASH95 in body
    assert "0o644" in body
    assert "st_nlink != 1" in body
    assert 'absent(p + "/90-meta-ha-maintenance.conf")' in body
    assert 'absent(p + "/93-cpython-pycache-prefix.conf")' not in body
    assert 'hashed(p + "/92-meta-controlled-failover.conf", h92)' in body
    assert 'hashed(p + "/93-cpython-pycache-prefix.conf", h93)' in body
    assert 'hashed(p + "/95-linasbot-credential-rekey-guard.conf", h95)' in body
    assert "/etc/systemd/system/linasbot.service.d" in body
    assert "/etc/systemd/system/linasbot-worker@.service.d" in body
    assert script.count("hp dropins") == 2
    local = script.index("hp dropins")
    peer = script.index("hp dropins", local + 1)
    assert local < script.index('hp node "$REPO_DIR/.env" node02') < peer


def test_instance_unauthorized_90_92_93_95_dropins_remain_absent() -> None:
    helper = _helper_python()
    body = helper[helper.index('elif cmd == "dropins":') : helper.index('elif cmd == "write-phase":')]
    assert 'f"/etc/systemd/system/linasbot-worker@{q}.service.d/{n}"' in body
    for name in (
        "90-meta-ha-maintenance.conf",
        "92-meta-controlled-failover.conf",
        "93-cpython-pycache-prefix.conf",
        "95-linasbot-credential-rekey-guard.conf",
    ):
        assert name in body
    instance = body[body.index("high_priority") :]
    assert "hashed(" not in instance
    assert "absent(" in instance


def test_fail_closed_trap_rearms_before_first_unlink_and_proves_maintenance() -> None:
    script = _script()
    helper = _helper_python()
    restore_fn = script.index("restore_s0() {")
    restore_body = script[restore_fn : script.index("fail_closed_cleanup() {")]
    per = restore_body.index('hp empty "$PER"')
    peer_per = restore_body.index('peer_hp empty "$PER"', per)
    vol = restore_body.index('hp empty "$VOL"', peer_per)
    peer_vol = restore_body.index('peer_hp empty "$VOL"', vol)
    assert restore_body.count("|| rc=1") >= 6
    assert per < peer_per < vol < peer_vol
    trap_fn = script.index("fail_closed_cleanup() {")
    arm = script.index("trap fail_closed_cleanup EXIT")
    first_unlink = script.index('peer_hp unlink "$VOL"')
    assert restore_fn < trap_fn < arm < first_unlink
    assert "os.lstat(path)" in helper
    assert "os.fstat(fd)" in helper
    assert "st_nlink != 1" in helper
    assert "O_NOFOLLOW" in helper
    assert "os.fchmod(fd, 0o600)" in helper
    assert "os.fchown(fd, 0, 0)" in helper
    assert "os.fsync(fd)" in helper


def test_peer_then_local_durable_unlink_public_wait_and_strict_verify_order() -> None:
    script = _script()
    arm = script.index("trap fail_closed_cleanup EXIT")
    peer_vol = script.index('peer_hp unlink "$VOL"', arm)
    peer_per = script.index('peer_hp unlink "$PER"', peer_vol)
    span_maint = script.index("span_public 503 ready-maint", peer_per)
    local_vol = script.index('hp unlink "$VOL"', span_maint)
    local_per = script.index('hp unlink "$PER"', local_vol)
    phase_s2 = script.index("PHASE=S2", local_per)
    both_ready = script.index('hp probe "$R" 200 ready-ok', phase_s2)
    strict = script.index('verify_meta_release_ha.sh" "$REQUIRED_SHA"', both_ready)
    span_ok = script.index("span_public 200 ready-ok", strict)
    disarm = script.index("trap - EXIT", span_ok)
    complete = script.index("RECOVERY_COMPLETE=true", disarm)
    assert (
        arm
        < peer_vol
        < peer_per
        < span_maint
        < local_vol
        < local_per
        < phase_s2
        < both_ready
        < strict
        < span_ok
        < disarm
        < complete
    )
    helper = _helper_python()
    unlink_fn = helper.index("def durable_unlink(path, empty=True):")
    assert helper.index("os.unlink(path)", unlink_fn) < helper.index("fsync_dir(os.path.dirname(path))", unlink_fn)
    assert 'elif cmd == "unlink":' in helper
    assert "unlink-phase" not in script
    assert 'hp unlink "$PHASE_FILE"' not in script
    assert 'k.startswith("META_")' in helper
    assert "live != expected" in helper
    assert "def process_old" not in helper
    assert helper.count("def process_meta") == 1


def test_s1_resume_spans_public_before_any_local_unlink() -> None:
    script = _script()
    s1 = script.index('if [ "$PHASE" = "S1" ]; then')
    then_at = script.index("then", s1)
    head = script[then_at + len("then") :].lstrip()
    assert head.startswith("span_public 503 ready-maint")
    span = script.index("span_public 503 ready-maint", s1)
    local_vol = script.index('hp unlink "$VOL"', s1)
    local_per = script.index('hp unlink "$PER"', local_vol)
    assert s1 < span < local_vol < local_per
    assert "unlink" not in script[s1:span]


def test_public_span_loop_and_s2_receipt_order() -> None:
    script = _script()
    span = script[script.index("span_public() {") : script.index('prove_release "$REPO_DIR"')]
    assert "while :; do" in span
    assert "DRAIN_SECONDS" in span
    assert 'peer_hp probe "$R" 200 ready-ok' in span
    assert 'hp probe "$R" "$code" "$mode"' in span
    assert 'hp probe "$PUB" 200 ready-ok' in span
    s0 = script.index('if [ "$PHASE" = "S0" ]; then')
    s1 = script.index('if [ "$PHASE" = "S1" ]; then', s0)
    complete = script.index("RECOVERY_COMPLETE=true")
    assert "span_public 503 ready-maint" not in script[s0:s1]
    assert "span_public 503 ready-maint" in script[s1:complete]
    assert "span_public 200 ready-ok" in script[s1:complete]
    assert script.index("span_public 503 ready-maint") < script.index('hp unlink "$VOL"', s1)
    assert script.index("PHASE=S2", s1) < script.index("span_public 200 ready-ok")
    assert script.index("span_public 200 ready-ok") < complete
    assert 'sleep "$DRAIN_SECONDS"' not in script
    assert "unlink-phase" not in script
    assert script.rindex("PHASE=S2") < complete
    assert 'hp unlink "$PHASE_FILE"' not in script


def test_admitted_resume_states_and_invalid_combinations() -> None:
    script = _script()
    assert '[ "$lv" -eq 1 ] && [ "$lp" -eq 1 ] && [ "$pv" -eq 1 ] && [ "$pp" -eq 1 ]' in script
    assert '[ "$lv" -eq 1 ] && [ "$lp" -eq 1 ] && [ "$pv" -eq 0 ] && [ "$pp" -eq 0 ]' in script
    assert '[ "$lv" -eq 0 ] && [ "$lp" -eq 0 ] && [ "$pv" -eq 0 ] && [ "$pp" -eq 0 ]' in script
    assert "hp marker" in script
    assert "peer_hp marker" in script
    assert MARKER_PROVENANCE in script
    assert FAILED_RUN_START in script
    assert '[ "$SAVED_PHASE" != "S0" ] && [ "$SAVED_PHASE" != "S1" ]' in script
    assert '[ "$SAVED_PHASE" != "S1" ] && [ "$SAVED_PHASE" != "S2" ]' in script
    assert script.count("marker/phase combination is not an admitted recovery state") >= 2
    assert "unbound split marker state" in script
    assert "PHASE=S0" in script and "PHASE=S1" in script and "PHASE=S2" in script
    assert "write-phase" in script and "read-phase" in script


def test_receipt_is_sanitized_and_contains_no_secrets() -> None:
    source = WORKFLOW.read_text(encoding="utf-8")
    receipt = _step("Emit sanitized recovery receipt")["run"]
    script = _script()
    assert "outcome=recovered" in receipt
    assert "control_sha=$CONTROL_SHA" in receipt
    assert "baseline=$BASELINE_SHA" in receipt
    assert "failed_run_id=$FAILED_RUN_ID" in receipt
    assert "GITHUB_STEP_SUMMARY" in receipt
    assert OLD_CONFIG_ID not in receipt
    assert NEW_CONFIG_ID not in source
    assert "secrets." not in receipt
    assert "print(config)" not in script
    assert "META_APP_A_FACEBOOK_LOGIN_CONFIG_ID" not in receipt
    assert "failed_run_id=$REQUIRED_RUN_ID" in script


def test_write_phase_uses_atomic_temp_fsync_rename() -> None:
    helper = _helper_python()
    body = helper[helper.index('elif cmd == "write-phase":') : helper.index('elif cmd == "audit":')]
    assert ".tmp" in body
    assert "os.rename(tmp, path)" in body
    assert "os.fsync(fd)" in body
    assert "os.lseek" not in body
    assert "os.ftruncate" not in body


def test_bound_partial_restore_write_s0_exits_before_unlink() -> None:
    script = _script()
    unbound = script.index("unbound split marker state")
    unbound_exit = script.index("exit 1", unbound)
    bound = script.index("bound partial marker pair crash state")
    restore = script.index("restore_s0", bound)
    write_s0 = script.index(
        'hp write-phase "$PHASE_FILE" "$PHASE_SCHEMA" "$REQUIRED_SHA" "$REQUIRED_RUN_ID" "$REQUIRED_CONTROL_SHA" S0',
        restore,
    )
    stop = script.index("exit 1", write_s0)
    first_unlink = script.index('peer_hp unlink "$VOL"')
    assert unbound_exit < bound < restore < write_s0 < stop < first_unlink
    assert "restore_s0" not in script[unbound:unbound_exit]
    assert "hp empty" not in script[unbound:unbound_exit]
    assert 'if [ "$lv" -eq 1 ]; then hp marker' in script[unbound_exit:restore]
    assert 'if [ "$lp" -eq 1 ]; then hp marker' in script[unbound_exit:restore]
    assert 'if [ "$pv" -eq 1 ]; then peer_hp marker' in script[unbound_exit:restore]
    assert 'if [ "$pp" -eq 1 ]; then peer_hp marker' in script[unbound_exit:restore]
    assert "unlink" not in script[restore:stop]
    assert script.index('if [ "$PHASE" = "S0" ]; then', stop) < first_unlink


def test_bound_partial_arms_fail_closed_before_restore_then_disarms() -> None:
    script = _script()
    bound = script.index("bound partial marker pair crash state")
    arm = script.index("trap fail_closed_cleanup EXIT", bound)
    restore = script.index("restore_s0", bound)
    write_s0 = script.index(
        'hp write-phase "$PHASE_FILE" "$PHASE_SCHEMA" "$REQUIRED_SHA" "$REQUIRED_RUN_ID" "$REQUIRED_CONTROL_SHA" S0',
        restore,
    )
    disarm = script.index("trap - EXIT", write_s0)
    stop = script.index("exit 1", disarm)
    first_unlink = script.index('peer_hp unlink "$VOL"')
    assert bound < arm < restore < write_s0 < disarm < stop < first_unlink
    assert "unlink" not in script[arm:stop]


def test_bound_partial_present_markers_use_recent_not_drain_age() -> None:
    script = _script()
    helper = _helper_python()
    unbound_exit = script.index("exit 1", script.index("unbound split marker state"))
    restore = script.index("restore_s0", script.index("bound partial marker pair crash state"))
    branch = script[unbound_exit:restore]
    assert 'hp marker "$VOL" recent "' in branch
    assert 'hp marker "$PER" recent "' in branch
    assert 'peer_hp marker "$VOL" recent "' in branch
    assert 'peer_hp marker "$PER" recent "' in branch
    assert ' marker "$VOL" drain ' not in branch
    assert ' marker "$PER" drain ' not in branch
    marker = helper[helper.index('elif cmd == "marker":') : helper.index('elif cmd == "node":')]
    assert 'mode != "recent"' in marker
    assert "int(st.st_mtime) < int(start)" in marker
    assert "int(now) - int(st.st_mtime) < int(drain)" in marker
    all_present = script[
        script.index('[ "$lv" -eq 1 ] && [ "$lp" -eq 1 ] && [ "$pv" -eq 1 ] && [ "$pp" -eq 1 ]') : script.index(
            "PHASE=S0"
        )
    ]
    assert 'hp marker "$VOL" drain "' in all_present
    assert " recent " not in all_present


def test_source_audit_parses_nul_paths_without_joining_adjacent_records(tmp_path: Path) -> None:
    helper = _helper_python()
    script = _script()
    assert 'ls-files", "-z"' in helper
    assert 'out.split(b"\\0")' in helper
    assert "found+=" not in script
    first, second = b"scripts/helper", b"mod.py"
    assert (first + second).endswith(b".py")
    parts = (first + b"\0" + second).split(b"\0")
    assert parts[0] == first
    assert not first.endswith((b".py", b".sh", b".bash"))
    repo = tmp_path / "repo"
    (repo / "scripts").mkdir(parents=True)
    (repo / "scripts" / "ok.sh").write_text("#!/bin/bash\n", encoding="utf-8")
    (repo / ".gitignore").write_text("venv/\n", encoding="utf-8")
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    subprocess.run(["git", "-C", str(repo), "add", "."], check=True)
    env = {
        **os.environ,
        "GIT_AUTHOR_NAME": "test",
        "GIT_AUTHOR_EMAIL": "t@e.invalid",
        "GIT_COMMITTER_NAME": "test",
        "GIT_COMMITTER_EMAIL": "t@e.invalid",
    }
    subprocess.run(["git", "-C", str(repo), "commit", "-q", "-m", "fixture"], check=True, env=env)
    (repo / "scripts" / "helper").write_text("not-python\n", encoding="utf-8")
    (repo / "venv" / "lib").mkdir(parents=True)
    (repo / "venv" / "lib" / "pkg.py").write_text("x=1\n", encoding="utf-8")
    allowed = subprocess.run(
        [sys.executable, "-c", helper, "audit", str(repo)], check=False, capture_output=True, text=True
    )
    assert allowed.returncode == 0, allowed.stderr
    (repo / "scripts" / "shadow.py").write_text("x=1\n", encoding="utf-8")
    blocked = subprocess.run(
        [sys.executable, "-c", helper, "audit", str(repo)], check=False, capture_output=True, text=True
    )
    assert blocked.returncode != 0
    assert "shadow the authorized release" in blocked.stderr
