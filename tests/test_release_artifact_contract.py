"""Release artifact determinism, safety, and closed-manifest tests."""

from __future__ import annotations

import copy
import io
import json
import os
import stat
import subprocess
import tarfile
from pathlib import Path

import pytest

from scripts.ha import release_archive_contract as archive_contract
from scripts.ha import release_artifact_cli as producer
from scripts.ha import release_artifact_contract as contract
from scripts.ha import release_source_bundle as source_bundle

TARGET_SHA = "a" * 40
TARGET_TREE_SHA = "b" * 40
REPOSITORY = "owner/repository"
WORKFLOW_REF = f"{REPOSITORY}/{contract.WORKFLOW_PATH}@refs/heads/main"


def _python_identity() -> dict[str, str]:
    return {
        "implementation": "CPython",
        "version": contract.PYTHON_VERSION,
        "pip_version": contract.PIP_VERSION,
        "cache_tag": contract.PYTHON_CACHE_TAG,
        "platform": contract.PYTHON_PLATFORM,
        "machine": contract.PYTHON_MACHINE,
        "runtime_artifact_name": contract.PYTHON_RUNTIME_NAME,
        "runtime_artifact_url": contract.PYTHON_RUNTIME_URL,
        "runtime_artifact_sha256": contract.PYTHON_RUNTIME_SHA256,
        "runtime_executable_name": "python3.13",
        "runtime_executable_sha256": contract.PYTHON_EXECUTABLE_SHA256,
        "runtime_tree_sha256": contract.PYTHON_RUNTIME_TREE_SHA256,
        "runtime_libpython_name": contract.PYTHON_LIBPYTHON_NAME,
        "runtime_libpython_sha256": contract.PYTHON_LIBPYTHON_SHA256,
    }


def _payload(name: str, evidence: contract.ArchiveEvidence) -> dict[str, object]:
    return {
        "archive": name,
        "archive_sha256": evidence.archive_sha256,
        "tree_sha256": evidence.tree_sha256,
        "file_count": evidence.file_count,
        "total_size": evidence.total_size,
    }


def _manifest(
    wheelhouse: contract.ArchiveEvidence,
    dashboard: contract.ArchiveEvidence,
    control_plane: contract.ArchiveEvidence,
    source_sha256: str,
    source_size: int,
) -> dict[str, object]:
    return {
        "schema": contract.MANIFEST_SCHEMA,
        "repository": REPOSITORY,
        "workflow_path": contract.WORKFLOW_PATH,
        "workflow_ref": WORKFLOW_REF,
        "run_id": 123,
        "run_attempt": 2,
        "target_sha": TARGET_SHA,
        "source_locks": {
            "requirements_lock_sha256": "1" * 64,
            "requirements_dev_lock_sha256": "2" * 64,
            "dashboard_package_lock_sha256": "3" * 64,
        },
        "toolchains": {
            "python": _python_identity(),
            "node": {"version": contract.NODE_VERSION},
            "npm": {"version": contract.NPM_VERSION},
        },
        "payloads": {
            "wheelhouse": _payload("wheelhouse.tar", wheelhouse),
            "dashboard": _payload("dashboard-build.tar", dashboard),
            "control_plane": _payload("control-plane.tar", control_plane),
            "source_bundle": {
                "file": "source.bundle",
                "sha256": source_sha256,
                "size": source_size,
                "target_sha": TARGET_SHA,
                "target_tree_sha": TARGET_TREE_SHA,
                "advertised_ref": "HEAD",
            },
            "python_runtime": {
                "file": contract.PYTHON_RUNTIME_NAME,
                "sha256": contract.PYTHON_RUNTIME_SHA256,
                "size": 123,
            },
        },
    }


def _sample_tree(root: Path) -> None:
    (root / "assets").mkdir(parents=True)
    (root / "index.html").write_text("hello\n", encoding="utf-8")
    executable = root / "assets" / "app.js"
    executable.write_text("asset\n", encoding="utf-8")
    executable.chmod(0o700)


def _control_tree(root: Path) -> None:
    for relative in contract.CONTROL_PLANE_FILES:
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"{relative}\n", encoding="utf-8")
        if relative in contract.CONTROL_PLANE_EXECUTABLE_FILES:
            path.chmod(0o755)


def _normalized_tar(path: Path, members: list[tarfile.TarInfo]) -> None:
    with tarfile.open(path, "w", format=tarfile.PAX_FORMAT) as bundle:
        for member in members:
            member.uid = 0
            member.gid = 0
            member.uname = ""
            member.gname = ""
            member.mtime = 0
            payload = io.BytesIO(b"x" * member.size) if member.isreg() else None
            bundle.addfile(member, payload)


def _regular(name: str, *, size: int = 1) -> tarfile.TarInfo:
    member = tarfile.TarInfo(name)
    member.type = tarfile.REGTYPE
    member.mode = 0o644
    member.size = size
    return member


def test_archive_is_byte_deterministic_and_extracts_exact_modes_under_umask(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    _sample_tree(source)
    first = contract.create_archive(source, tmp_path / "first.tar")
    os.utime(source / "index.html", (1_700_000_000, 1_700_000_000))
    (source / "index.html").chmod(0o600)
    second = contract.create_archive(source, tmp_path / "second.tar")

    assert first == second
    assert (tmp_path / "first.tar").read_bytes() == (tmp_path / "second.tar").read_bytes()
    assert contract.verify_archive(tmp_path / "first.tar", first.archive_sha256, first.tree_sha256) == first

    previous_umask = os.umask(0o077)
    try:
        contract.extract_archive(
            tmp_path / "first.tar",
            tmp_path / "extracted",
            first.archive_sha256,
            first.tree_sha256,
        )
    finally:
        os.umask(previous_umask)
    assert stat.S_IMODE((tmp_path / "extracted" / "assets").stat().st_mode) == 0o755
    assert stat.S_IMODE((tmp_path / "extracted" / "index.html").stat().st_mode) == 0o644
    assert stat.S_IMODE((tmp_path / "extracted" / "assets" / "app.js").stat().st_mode) == 0o755


def test_archive_source_rejects_symlinks_and_special_objects(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    target = source / "target"
    target.write_text("payload", encoding="utf-8")
    (source / "alias").symlink_to(target)
    with pytest.raises(contract.ContractError, match="link or special"):
        contract.create_archive(source, tmp_path / "symlink.tar")
    (source / "alias").unlink()
    os.mkfifo(source / "fifo")
    with pytest.raises(contract.ContractError, match="link or special"):
        contract.create_archive(source, tmp_path / "fifo.tar")


@pytest.mark.parametrize("name", ["../escape", "/absolute", "dir\\windows", "line\nbreak"])
def test_archive_verifier_rejects_unsafe_paths(tmp_path: Path, name: str) -> None:
    archive = tmp_path / "unsafe.tar"
    _normalized_tar(archive, [_regular(name)])
    with pytest.raises(contract.ContractError, match="unsafe path"):
        contract.verify_archive(archive)


def test_archive_verifier_rejects_links_duplicates_and_non_normalized_metadata(tmp_path: Path) -> None:
    link = tarfile.TarInfo("alias")
    link.type = tarfile.SYMTYPE
    link.mode = 0o777
    link.linkname = "target"
    _normalized_tar(tmp_path / "link.tar", [link])
    with pytest.raises(contract.ContractError, match="unsafe object"):
        contract.verify_archive(tmp_path / "link.tar")

    _normalized_tar(tmp_path / "duplicate.tar", [_regular("same"), _regular("same")])
    with pytest.raises(contract.ContractError, match="duplicate"):
        contract.verify_archive(tmp_path / "duplicate.tar")

    member = _regular("file")
    member.uid = 12
    with tarfile.open(tmp_path / "owner.tar", "w") as bundle:
        bundle.addfile(member, io.BytesIO(b"x"))
    with pytest.raises(contract.ContractError, match="not normalized"):
        contract.verify_archive(tmp_path / "owner.tar")


def test_secure_file_evidence_rejects_symlink_and_inode_swap(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    victim = tmp_path / "victim"
    replacement = tmp_path / "replacement"
    victim.write_bytes(b"first")
    replacement.write_bytes(b"second")
    alias = tmp_path / "alias"
    alias.symlink_to(victim)
    with pytest.raises(contract.ContractError, match="regular file"):
        contract.file_evidence(alias)

    original_open = archive_contract.os.open
    swapped = False

    def swapping_open(path: object, flags: int, *args: object, **kwargs: object) -> int:
        nonlocal swapped
        if not swapped and Path(path) == victim:
            os.replace(replacement, victim)
            swapped = True
        return original_open(path, flags, *args, **kwargs)

    monkeypatch.setattr(archive_contract.os, "open", swapping_open)
    with pytest.raises(contract.ContractError, match="changed while opening"):
        contract.file_evidence(victim)


def test_safe_copy_rejects_symlink_without_touching_its_target(tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    outside.write_text("do-not-touch", encoding="utf-8")
    source = tmp_path / "source"
    source.symlink_to(outside)
    with pytest.raises(contract.ContractError, match="regular file"):
        contract.copy_regular(source, tmp_path / "copied")
    assert outside.read_text(encoding="utf-8") == "do-not-touch"
    assert not (tmp_path / "copied").exists()


def test_manifest_is_canonical_closed_and_pins_exact_runtime(tmp_path: Path) -> None:
    tree = tmp_path / "tree"
    tree.mkdir()
    (tree / "file").write_bytes(b"payload")
    wheel = contract.create_archive(tree, tmp_path / "wheelhouse.tar")
    dashboard = contract.create_archive(tree, tmp_path / "dashboard-build.tar")
    control_root = tmp_path / "control"
    control_root.mkdir()
    _control_tree(control_root)
    control = contract.create_archive(control_root, tmp_path / "control-plane.tar")
    source = tmp_path / "source.bundle"
    source.write_bytes(b"bundle")
    source_sha = contract.sha256_file(source)
    manifest = _manifest(wheel, dashboard, control, source_sha, source.stat().st_size)

    contract.write_manifest(tmp_path / "release-manifest.json", manifest)
    raw = (tmp_path / "release-manifest.json").read_bytes()
    assert raw == contract.canonical_json(manifest)
    assert b"artifact_id" not in raw and b"artifact_digest" not in raw
    assert (
        contract.load_manifest(
            tmp_path / "release-manifest.json",
            expected_repository=REPOSITORY,
            expected_workflow_ref=WORKFLOW_REF,
            expected_run_id=123,
            expected_run_attempt=2,
            expected_target_sha=TARGET_SHA,
        )
        == manifest
    )

    unpinned = copy.deepcopy(manifest)
    unpinned["toolchains"]["python"]["runtime_executable_sha256"] = "f" * 64
    with pytest.raises(contract.ContractError, match="Python toolchain"):
        contract.validate_manifest(unpinned)
    extra = copy.deepcopy(manifest)
    extra["artifact_id"] = 99
    with pytest.raises(contract.ContractError, match="not closed"):
        contract.validate_manifest(extra)


def test_manifest_secure_read_rejects_symlink_and_noncanonical_json(tmp_path: Path) -> None:
    target = tmp_path / "target.json"
    target.write_text("{}\n", encoding="utf-8")
    alias = tmp_path / "release-manifest.json"
    alias.symlink_to(target)
    with pytest.raises(contract.ContractError, match="regular file"):
        contract.load_manifest(alias)
    alias.unlink()
    alias.write_text(json.dumps({"schema": "wrong"}, indent=2), encoding="utf-8")
    with pytest.raises(contract.ContractError, match="not canonical"):
        contract.load_manifest(alias)


def _git(repository: Path, *arguments: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repository), *arguments],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return result.stdout


def _git_repository(path: Path) -> str:
    path.mkdir()
    _git(path, "init")
    for key in ("core.ignorecase", "core.precomposeunicode"):
        subprocess.run(
            ["git", "-C", str(path), "config", "--unset-all", key],
            check=False,
            capture_output=True,
        )
    (path / "tracked").write_text("one\n", encoding="utf-8")
    _git(path, "add", "tracked")
    _git(
        path,
        "-c",
        "user.email=release@example.invalid",
        "-c",
        "user.name=Release Test",
        "commit",
        "-m",
        "first",
    )
    (path / "tracked").write_text("two\n", encoding="utf-8")
    _git(
        path,
        "-c",
        "user.email=release@example.invalid",
        "-c",
        "user.name=Release Test",
        "commit",
        "-am",
        "second",
    )
    return _git(path, "rev-parse", "HEAD").strip()


def test_source_bundle_has_one_exact_head_and_complete_history(tmp_path: Path) -> None:
    repository = tmp_path / "repository"
    target_sha = _git_repository(repository)
    bundle = tmp_path / "source.bundle"
    evidence = producer._create_source_bundle(repository, bundle, target_sha)
    assert evidence["target_sha"] == target_sha
    assert evidence["advertised_ref"] == "HEAD"
    assert _git(repository, "bundle", "list-heads", str(bundle)) == f"{target_sha} HEAD\n"


@pytest.mark.parametrize("dirty_kind", ["tracked", "untracked"])
def test_source_bundle_rejects_a_dirty_checkout(tmp_path: Path, dirty_kind: str) -> None:
    repository = tmp_path / "repository"
    target_sha = _git_repository(repository)
    if dirty_kind == "tracked":
        (repository / "tracked").write_text("dirty\n", encoding="utf-8")
    else:
        (repository / "untracked").write_text("dirty\n", encoding="utf-8")
    with pytest.raises(contract.ContractError, match="clean HEAD"):
        producer._create_source_bundle(repository, tmp_path / "source.bundle", target_sha)


@pytest.mark.parametrize("authority", ["grafts", "alternates", "replace-config"])
def test_source_bundle_rejects_non_object_database_authority(tmp_path: Path, authority: str) -> None:
    repository = tmp_path / "repository"
    target_sha = _git_repository(repository)
    git_dir = Path(_git(repository, "rev-parse", "--git-dir").strip())
    git_dir = repository / git_dir
    if authority == "grafts":
        (git_dir / "info" / "grafts").write_text("forbidden\n", encoding="utf-8")
    elif authority == "alternates":
        (git_dir / "objects" / "info" / "alternates").write_text("/tmp/forbidden\n", encoding="utf-8")
    else:
        _git(repository, "config", "core.useReplaceRefs", "false")
    with pytest.raises(contract.ContractError, match="forbidden"):
        producer._create_source_bundle(repository, tmp_path / "source.bundle", target_sha)


@pytest.mark.parametrize(
    "key,value", [("core.worktree", "/tmp"), ("core.fsmonitor", "/bin/false"), ("include.path", "/tmp/config")]
)
def test_source_bundle_rejects_any_unreviewed_local_config(tmp_path: Path, key: str, value: str) -> None:
    repository = tmp_path / "repository"
    target_sha = _git_repository(repository)
    _git(repository, "config", key, value)
    with pytest.raises(contract.ContractError, match="forbidden local Git config"):
        producer._create_source_bundle(repository, tmp_path / "source.bundle", target_sha)


def test_source_bundle_rejects_local_attributes_even_when_status_is_clean(tmp_path: Path) -> None:
    repository = tmp_path / "repository"
    target_sha = _git_repository(repository)
    git_dir = repository / _git(repository, "rev-parse", "--git-dir").strip()
    (git_dir / "info" / "attributes").write_text(
        "tracked text eol=crlf\n",
        encoding="utf-8",
    )
    (repository / "tracked").unlink()
    _git(repository, "checkout", "--", "tracked")
    assert (repository / "tracked").read_bytes() == b"two\r\n"
    assert _git(repository, "status", "--porcelain=v1") == ""

    with pytest.raises(contract.ContractError, match="attribute authority"):
        source_bundle.assert_clean_checkout(repository, tmp_path, target_sha)


@pytest.mark.parametrize("flag", ["--assume-unchanged", "--skip-worktree"])
def test_source_bundle_rejects_hidden_index_flags(tmp_path: Path, flag: str) -> None:
    repository = tmp_path / "repository"
    target_sha = _git_repository(repository)
    _git(repository, "update-index", flag, "tracked")
    (repository / "tracked").write_text("hidden change\n", encoding="utf-8")
    assert _git(repository, "status", "--porcelain=v1") == ""

    with pytest.raises(contract.ContractError, match="index flags"):
        source_bundle.assert_clean_checkout(repository, tmp_path, target_sha)


def test_control_plane_copy_is_bound_to_raw_target_blob_not_worktree_projection(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = tmp_path / "repository"
    target_sha = _git_repository(repository)
    authority = source_bundle.target_regular_file_authority(
        repository,
        tmp_path,
        target_sha,
        ("tracked",),
    )
    assert authority["tracked"] == (
        __import__("hashlib").sha256(b"two\n").hexdigest(),
        False,
    )
    monkeypatch.setattr(producer, "CONTROL_PLANE_FILES", ("tracked",))
    destination = tmp_path / "control"
    producer._copy_control_plane(repository, destination, authority)
    assert (destination / "tracked").read_bytes() == b"two\n"

    _git(repository, "update-index", "--assume-unchanged", "tracked")
    (repository / "tracked").write_text("hidden change\n", encoding="utf-8")
    with pytest.raises(contract.ContractError, match="differs from its source authority"):
        producer._copy_control_plane(repository, tmp_path / "rejected", authority)


def test_source_bundle_disables_system_git_attributes(tmp_path: Path) -> None:
    environment = source_bundle._git_environment(tmp_path)
    assert environment["GIT_ATTR_NOSYSTEM"] == "1"
