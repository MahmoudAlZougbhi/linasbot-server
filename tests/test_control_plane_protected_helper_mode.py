"""Protected HA helper mode is part of the control-plane artifact contract."""

from __future__ import annotations

import io
import stat
import subprocess
import tarfile
from pathlib import Path

import pytest

from scripts.ha import release_artifact_contract as contract

ROOT = Path(__file__).resolve().parents[1]
HELPER = "scripts/ha/deploy_meta_release_ha.sh"
DEPLOY_WORKFLOW = ROOT / ".github" / "workflows" / "deploy.yml"


def _control_tree(root: Path, *, helper_mode: int) -> None:
    for relative in contract.CONTROL_PLANE_FILES:
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes((ROOT / relative).read_bytes())
        if relative in contract.CONTROL_PLANE_EXECUTABLE_FILES:
            path.chmod(helper_mode)
        else:
            path.chmod(0o644)


def _member(name: str, *, mode: int = 0o644, payload: bytes = b"x", kind: str = "file") -> tarfile.TarInfo:
    member = tarfile.TarInfo(name)
    member.uid = 0
    member.gid = 0
    member.uname = ""
    member.gname = ""
    member.mtime = 0
    if kind == "dir":
        member.type = tarfile.DIRTYPE
        member.mode = 0o755
        member.size = 0
        return member
    if kind == "symlink":
        member.type = tarfile.SYMTYPE
        member.mode = 0o777
        member.linkname = "target"
        member.size = 0
        return member
    member.type = tarfile.REGTYPE
    member.mode = mode
    member.size = len(payload)
    return member


def test_git_tracks_protected_control_plane_helpers_as_executable() -> None:
    assert contract.CONTROL_PLANE_EXECUTABLE_FILES <= set(contract.CONTROL_PLANE_FILES)
    assert HELPER in contract.CONTROL_PLANE_EXECUTABLE_FILES
    listing = subprocess.check_output(
        ["git", "ls-files", "-s", "--", *sorted(contract.CONTROL_PLANE_EXECUTABLE_FILES)],
        cwd=ROOT,
        text=True,
    )
    rows = [line for line in listing.splitlines() if line]
    assert len(rows) == len(contract.CONTROL_PLANE_EXECUTABLE_FILES)
    for line in rows:
        assert line.startswith("100755 "), line


def test_control_plane_archive_stores_protected_helper_as_regular_0755(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    _control_tree(source, helper_mode=0o755)
    archive = tmp_path / "control-plane.tar"
    evidence = contract.create_archive(source, archive)
    verified = contract.verify_archive(
        archive,
        evidence.archive_sha256,
        evidence.tree_sha256,
        expected_paths=contract.CONTROL_PLANE_MEMBERS,
    )
    assert verified == evidence
    contract.assert_control_plane_protected_helpers(archive)
    with tarfile.open(archive, "r:") as bundle:
        member = bundle.getmember(HELPER)
        assert member.isreg()
        assert not member.issym()
        assert stat.S_IMODE(member.mode) == 0o755


def test_protected_helper_mode_is_included_in_tree_digest(tmp_path: Path) -> None:
    executable = tmp_path / "exec"
    unexecutable = tmp_path / "noexec"
    executable.mkdir()
    unexecutable.mkdir()
    _control_tree(executable, helper_mode=0o755)
    _control_tree(unexecutable, helper_mode=0o644)
    first = contract.create_archive(executable, tmp_path / "exec.tar")
    second = contract.create_archive(unexecutable, tmp_path / "noexec.tar")
    assert first.archive_sha256 != second.archive_sha256
    assert first.tree_sha256 != second.tree_sha256
    contract.assert_control_plane_protected_helpers(tmp_path / "exec.tar")
    with pytest.raises(contract.ContractError, match="0755 regular file"):
        contract.assert_control_plane_protected_helpers(tmp_path / "noexec.tar")


def test_protected_helper_symlink_and_unsafe_modes_are_rejected(tmp_path: Path) -> None:
    symlink_archive = tmp_path / "symlink.tar"
    with tarfile.open(symlink_archive, "w", format=tarfile.PAX_FORMAT) as bundle:
        bundle.addfile(_member("scripts", kind="dir"))
        bundle.addfile(_member("scripts/ha", kind="dir"))
        bundle.addfile(_member(HELPER, kind="symlink"))
    with pytest.raises(contract.ContractError, match="unsafe object"):
        contract.verify_archive(symlink_archive)

    unsafe_archive = tmp_path / "unsafe.tar"
    payload = b"helper"
    with tarfile.open(unsafe_archive, "w", format=tarfile.PAX_FORMAT) as bundle:
        bundle.addfile(_member("scripts", kind="dir"))
        bundle.addfile(_member("scripts/ha", kind="dir"))
        bundle.addfile(_member(HELPER, mode=0o777, payload=payload), io.BytesIO(payload))
    with pytest.raises(contract.ContractError, match="unsafe object"):
        contract.verify_archive(unsafe_archive)


def test_copy_control_plane_rejects_non_executable_protected_helper(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from scripts.ha import release_artifact_cli as producer

    monkeypatch.setattr(producer, "CONTROL_PLANE_FILES", (HELPER,))
    monkeypatch.setattr(producer, "CONTROL_PLANE_EXECUTABLE_FILES", frozenset({HELPER}))
    source = tmp_path / "repo"
    source.mkdir()
    helper = source / HELPER
    helper.parent.mkdir(parents=True)
    helper.write_bytes(b"#!/bin/sh\n")
    helper.chmod(0o644)
    digest = contract.sha256_file(helper)
    with pytest.raises(contract.ContractError, match="tracked executable"):
        producer._copy_control_plane(source, tmp_path / "out", {HELPER: (digest, False)})


def test_commit_exact_still_rejects_helper_that_is_not_0755() -> None:
    text = DEPLOY_WORKFLOW.read_text(encoding="utf-8")
    assert "if not member.isfile() or member.mode != 0o755 or not 1 <= member.size <= (4 << 20):" in text
    assert "protected deploy helper member is unsafe" in text
    helper_gate = text.split("protected deploy helper member is unsafe", 1)[0][-400:]
    assert "0o644" not in helper_gate
