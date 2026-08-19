"""HA deploy-version lives under the root-owned meta-ha private-deploy dir."""

from __future__ import annotations

import os
import stat
import subprocess
import sys
from pathlib import Path

from tests.test_ha_deploy_transaction import _embedded_python, _helper

PARENT_UNSAFE = "private state parent is unsafe"
LEGACY = '"$REPO_DIR/data/.deploy_version"'


def _write_python() -> str:
    return _embedded_python("write_private_state")


def _adapt_owner(code: str) -> str:
    uid = os.getuid()
    gid = os.getgid()
    return (
        code.replace("info.st_uid != 0", f"info.st_uid != {uid}")
        .replace("info.st_gid != 0", f"info.st_gid != {gid}")
        .replace("current.st_uid != 0", f"current.st_uid != {uid}")
        .replace("current.st_gid != 0", f"current.st_gid != {gid}")
        .replace("os.fchown(descriptor, 0, 0)", f"os.fchown(descriptor, {uid}, {gid})")
    )


def _run(code: str, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-B", "-I", "-S", "-c", code, *args],
        capture_output=True,
        text=True,
        check=False,
    )


def test_write_private_state_parent_gate_is_unchanged() -> None:
    source = _write_python()
    assert "not stat.S_ISDIR(info.st_mode)" in source
    assert "stat.S_ISLNK(info.st_mode)" in source
    assert "info.st_uid != 0" in source
    assert "info.st_gid != 0" in source
    assert "stat.S_IMODE(info.st_mode) & 0o022" in source
    assert f'raise SystemExit("{PARENT_UNSAFE}")' in source


def test_non_root_parent_is_rejected(tmp_path: Path) -> None:
    parent = tmp_path / "private-deploy"
    parent.mkdir(mode=0o700)
    target = parent / "deploy-version"
    result = _run(_write_python(), str(target), "123")
    assert result.returncode != 0
    assert PARENT_UNSAFE in result.stderr
    assert not target.exists()


def test_symlink_parent_is_rejected(tmp_path: Path) -> None:
    real = tmp_path / "real"
    real.mkdir(mode=0o700)
    parent = tmp_path / "private-deploy"
    parent.symlink_to(real)
    target = parent / "deploy-version"
    result = _run(_adapt_owner(_write_python()), str(target), "123")
    assert result.returncode != 0
    assert PARENT_UNSAFE in result.stderr
    assert not (real / "deploy-version").exists()


def test_group_or_world_writable_parent_is_rejected(tmp_path: Path) -> None:
    parent = tmp_path / "private-deploy"
    parent.mkdir()
    parent.chmod(0o775)
    target = parent / "deploy-version"
    result = _run(_adapt_owner(_write_python()), str(target), "123")
    assert result.returncode != 0
    assert PARENT_UNSAFE in result.stderr
    assert not target.exists()


def test_root_owned_mode_0700_parent_succeeds(tmp_path: Path) -> None:
    parent = tmp_path / "private-deploy"
    parent.mkdir()
    parent.chmod(0o700)
    target = parent / "deploy-version"
    result = _run(_adapt_owner(_write_python()), str(target), "1710000000")
    assert result.returncode == 0, result.stderr
    assert target.read_text(encoding="ascii") == "1710000000\n"
    info = target.stat()
    assert stat.S_IMODE(info.st_mode) == 0o600
    assert info.st_nlink == 1


def test_helper_stores_deploy_version_under_meta_ha_private_deploy() -> None:
    source = _helper()
    assert LEGACY not in source
    assert "PRIVATE_DEPLOY_DIR=$META_HA_STATE_ROOT/private-deploy" in source
    assert "DEPLOY_VERSION_FILE=$PRIVATE_DEPLOY_DIR/deploy-version" in source
    ensure = source[source.index("ensure_private_deploy_dir() {") : source.index("assert_path_absent() {")]
    assert 'install -d -o root -g root -m 0700 "$PRIVATE_DEPLOY_DIR"' in ensure
    assert "$REPO_DIR/data" not in ensure
    assert "/opt/linasbot/data" not in ensure


def test_activate_rollback_and_recovery_use_the_same_ha_path() -> None:
    source = _helper()
    activate = source[source.index("activate_impl() {") : source.index("start_saved_runtime_disabled() {")]
    rollback = source[source.index("rollback_impl() {") : source.index("node_activate() {")]
    recover = source[source.index("recover_deployment() {") : source.index("retry_distinct_reconciliation() {")]
    assert 'snapshot_live_deploy_version "$generation_root"' in activate
    assert 'write_live_deploy_version "$deploy_version"' in activate
    assert LEGACY not in activate
    assert 'restore_live_deploy_version "$generation_root"' in rollback
    assert rollback.count('restore_live_deploy_version "$generation_root"') >= 2
    assert LEGACY not in rollback
    assert 'copy_private_file_durable "$DEPLOY_VERSION_FILE" "$previous"' in source
    assert 'copy_private_file_durable "$previous" "$DEPLOY_VERSION_FILE"' in source
    assert 'node_recover_rollback "$previous_sha" "$tx_dir"' in recover
    assert 'rollback_impl "$previous_sha" "$tx_dir"' in source
    assert LEGACY not in recover


def test_copy_and_unlink_keep_the_same_parent_gate() -> None:
    copy = _embedded_python("copy_private_file_durable")
    unlink = _embedded_python("unlink_live_deploy_version")
    for block in (copy, unlink):
        assert "st_uid != 0" in block
        assert "st_gid != 0" in block
        assert "S_ISLNK(" in block
        assert "S_IMODE(" in block
        assert "& 0o022" in block
        assert PARENT_UNSAFE in block
    assert "S_IMODE(parent_info.st_mode) != 0o700" in unlink


def test_steady_does_not_require_manual_data_ownership_change() -> None:
    source = _helper()
    live = source[source.index("write_live_deploy_version() {") : source.index("copy_private_file_durable() {")]
    activate = source[source.index("activate_impl() {") : source.index("start_saved_runtime_disabled() {")]
    assert 'write_private_state "$DEPLOY_VERSION_FILE"' in live
    assert "$REPO_DIR/data" not in live
    assert "chown" not in live
    assert "chmod" not in live
    assert LEGACY not in activate
    assert 'write_private_state "$REPO_DIR/data/.deploy_version"' not in source
    assert "chown" not in activate
