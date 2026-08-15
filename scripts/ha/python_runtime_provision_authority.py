#!/usr/bin/env python3
"""Durable nofollow authority publication for the Python runtime transaction."""

from __future__ import annotations

import json
import os
import stat
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any, Protocol

from scripts.ha import python_runtime_archive_contract as archive
from scripts.ha import python_runtime_provision_contract as contract
from scripts.ha import release_artifact_contract as release

ProvisionError = archive.ProvisionError
MAX_WHEELHOUSE_BYTES = 1024**3
MAX_RELEASE_PAYLOAD_BYTES = 1024**3


class Paths(Protocol):
    def tx_root(self, tx_id: str) -> Path: ...


def secure_state_file(path: Path, *, max_bytes: int = 1024 * 1024) -> bytes:
    temporary = path.parent / f".{path.name}.writing"
    if (path.exists() or path.is_symlink()) and (temporary.exists() or temporary.is_symlink()):
        published = path.lstat()
        staged = temporary.lstat()
        same_link = (
            (published.st_dev, published.st_ino) == (staged.st_dev, staged.st_ino)
            and published.st_nlink == 2
            and staged.st_nlink == 2
        )
        if same_link:
            for observed in (published, staged):
                if (
                    not stat.S_ISREG(observed.st_mode)
                    or stat.S_ISLNK(observed.st_mode)
                    or observed.st_uid != archive.EXPECTED_UID
                    or observed.st_gid != archive.EXPECTED_GID
                    or stat.S_IMODE(observed.st_mode) != 0o600
                ):
                    raise ProvisionError("durable linked write remnant is unsafe")
            temporary.unlink()
            archive.fsync_directory(path.parent)
    info = path.lstat()
    if stat.S_IMODE(info.st_mode) != 0o600:
        raise ProvisionError(f"durable state mode is unsafe: {path}")
    return bytes(archive.read_regular(path, max_bytes=max_bytes))


def load_json(path: Path) -> dict[str, Any]:
    raw = secure_state_file(path)
    try:
        payload = json.loads(raw.decode("utf-8", "strict"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ProvisionError("durable runtime state is invalid JSON") from exc
    if not isinstance(payload, dict) or contract.canonical(payload) != raw:
        raise ProvisionError("durable runtime state is not canonical")
    return payload


def _adopt_link(path: Path, temporary: Path, size: int) -> None:
    published = path.lstat()
    staged = temporary.lstat()
    if (
        (published.st_dev, published.st_ino) != (staged.st_dev, staged.st_ino)
        or not stat.S_ISREG(published.st_mode)
        or stat.S_ISLNK(published.st_mode)
        or published.st_uid != archive.EXPECTED_UID
        or published.st_gid != archive.EXPECTED_GID
        or stat.S_IMODE(published.st_mode) != 0o600
        or published.st_nlink != 2
        or staged.st_nlink != 2
        or published.st_size != size
    ):
        return
    temporary.unlink()
    archive.fsync_directory(path.parent)


def atomic_write(path: Path, payload: bytes, *, no_replace: bool = False) -> None:
    archive.secure_directory(path.parent, mode=0o700)
    temporary = path.parent / f".{path.name}.writing"
    if path.exists() or path.is_symlink():
        if temporary.exists() or temporary.is_symlink():
            _adopt_link(path, temporary, len(payload))
        current = secure_state_file(path, max_bytes=max(len(payload), 1024 * 1024))
        if no_replace:
            if current != payload:
                raise ProvisionError(f"durable file already exists: {path}")
            if temporary.exists() or temporary.is_symlink():
                secure_state_file(temporary, max_bytes=max(len(payload), 1024 * 1024))
                temporary.unlink()
                archive.fsync_directory(path.parent)
            return
    if temporary.exists() or temporary.is_symlink():
        try:
            complete = secure_state_file(temporary, max_bytes=max(len(payload), 1024 * 1024)) == payload
        except ProvisionError:
            complete = False
        if not complete:
            temporary.unlink()
            archive.fsync_directory(path.parent)
    descriptor = -1
    try:
        if not temporary.exists():
            descriptor = os.open(
                temporary,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
                0o600,
            )
            os.fchmod(descriptor, 0o600)
            os.fchown(descriptor, archive.EXPECTED_UID, archive.EXPECTED_GID)
            archive.write_all(descriptor, payload)
            os.fsync(descriptor)
            os.close(descriptor)
            descriptor = -1
            archive.fsync_directory(path.parent)
        if secure_state_file(temporary, max_bytes=max(len(payload), 1024 * 1024)) != payload:
            raise ProvisionError("durable temporary state differs before publication")
        if no_replace:
            try:
                os.link(temporary, path, follow_symlinks=False)
            except FileExistsError:
                if secure_state_file(path, max_bytes=max(len(payload), 1024 * 1024)) != payload:
                    raise ProvisionError(f"durable file already exists: {path}") from None
            archive.fsync_directory(path.parent)
        else:
            os.replace(temporary, path)
        os.chown(path, archive.EXPECTED_UID, archive.EXPECTED_GID, follow_symlinks=False)
        os.chmod(path, 0o600, follow_symlinks=False)
        temporary.unlink(missing_ok=True)
        archive.fsync_directory(path.parent)
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        temporary.unlink(missing_ok=True)


def _copy_regular(
    source: Path,
    destination: Path,
    *,
    expected_sha256: str,
    max_bytes: int,
    marker: str,
    boundary: Callable[[str], None],
) -> None:
    digest, size = archive.file_evidence(source, max_bytes=max_bytes)
    if digest != expected_sha256:
        raise ProvisionError("durable authority source digest is wrong")
    temporary = destination.parent / f".{destination.name}.copying"
    if destination.exists() or destination.is_symlink():
        if temporary.exists() or temporary.is_symlink():
            _adopt_link(destination, temporary, size)
        if archive.file_evidence(destination, max_bytes=max_bytes) != (digest, size):
            raise ProvisionError("durable authority snapshot conflicts with recovery state")
        if temporary.exists() or temporary.is_symlink():
            archive.file_evidence(temporary, max_bytes=max_bytes)
            temporary.unlink()
            archive.fsync_directory(destination.parent)
        return
    boundary(f"before_{marker}")
    if temporary.exists() or temporary.is_symlink():
        try:
            complete = archive.file_evidence(temporary, max_bytes=max_bytes) == (digest, size)
        except ProvisionError:
            complete = False
        if not complete:
            temporary.unlink()
            archive.fsync_directory(destination.parent)
    if not temporary.exists():
        descriptor = os.open(
            temporary,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
            0o600,
        )
        try:
            boundary(f"after_{marker}_temp_create")
            os.fchmod(descriptor, 0o600)
            os.fchown(descriptor, archive.EXPECTED_UID, archive.EXPECTED_GID)
            with archive.open_regular(source, max_bytes=max_bytes) as (handle, _before):
                for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                    archive.write_all(descriptor, chunk)
                    boundary(f"after_{marker}_chunk_write")
            os.fsync(descriptor)
            boundary(f"after_{marker}_file_fsync")
        finally:
            os.close(descriptor)
        if archive.file_evidence(temporary, max_bytes=max_bytes) != (digest, size):
            raise ProvisionError("durable authority temporary snapshot is incomplete")
        archive.fsync_directory(destination.parent)
        boundary(f"after_{marker}_temp_dir_fsync")
    try:
        os.link(temporary, destination, follow_symlinks=False)
    except FileExistsError:
        if archive.file_evidence(destination, max_bytes=max_bytes) != (digest, size):
            raise ProvisionError("durable authority snapshot publication conflicts") from None
    archive.fsync_directory(destination.parent)
    boundary(f"after_{marker}_publish")
    temporary.unlink(missing_ok=True)
    archive.fsync_directory(destination.parent)
    boundary(f"after_{marker}")


def snapshot_authority(
    paths: Paths,
    plan: Mapping[str, Any],
    plan_sha256: str,
    bundle: Path,
    *,
    boundary: Callable[[str], None],
) -> Path:
    contract.validate_plan(plan, plan_sha256)
    authority_root = paths.tx_root(str(plan["transaction_id"])) / "authority"
    archive.secure_directory(authority_root, mode=0o700, create=True)
    plan_path = authority_root / "plan.json"
    plan_raw = contract.canonical(plan)
    if plan_path.exists() or plan_path.is_symlink():
        if secure_state_file(plan_path) != plan_raw:
            raise ProvisionError("durable runtime plan snapshot conflicts")
    else:
        boundary("before_plan_snapshot")
        atomic_write(plan_path, plan_raw, no_replace=True)
        boundary("after_plan_snapshot")
    _copy_regular(
        bundle / "release-manifest.json",
        authority_root / "release-manifest.json",
        expected_sha256=str(plan["qg_manifest_sha256"]),
        max_bytes=archive.MAX_ARCHIVE_BYTES,
        marker="manifest_snapshot",
        boundary=boundary,
    )
    try:
        manifest = release.load_manifest(
            authority_root / "release-manifest.json",
            expected_repository=str(plan["qg_repository"]),
            expected_workflow_ref=str(plan["qg_workflow_ref"]),
            expected_run_id=plan["qg_run_id"],
            expected_run_attempt=plan["qg_run_attempt"],
            expected_target_sha=str(plan["qg_target_sha"]),
        )
    except release.ContractError as exc:
        raise ProvisionError("durable release manifest snapshot is invalid") from exc
    payloads = manifest["payloads"]
    if (
        payloads["control_plane"]["archive_sha256"] != plan["control_plane_archive_sha256"]
        or payloads["wheelhouse"]["archive_sha256"] != plan["wheelhouse_archive_sha256"]
        or payloads["python_runtime"]["sha256"] != plan["artifact_sha256"]
    ):
        raise ProvisionError("durable release manifest differs from the runtime plan")
    files = (
        ("control-plane.tar", str(plan["control_plane_archive_sha256"]), "control_snapshot", archive.MAX_ARCHIVE_BYTES),
        ("wheelhouse.tar", str(plan["wheelhouse_archive_sha256"]), "wheelhouse_snapshot", MAX_WHEELHOUSE_BYTES),
        (
            "dashboard-build.tar",
            str(payloads["dashboard"]["archive_sha256"]),
            "dashboard_snapshot",
            MAX_RELEASE_PAYLOAD_BYTES,
        ),
        (
            "source.bundle",
            str(payloads["source_bundle"]["sha256"]),
            "source_bundle_snapshot",
            MAX_RELEASE_PAYLOAD_BYTES,
        ),
        (str(plan["artifact_name"]), str(plan["artifact_sha256"]), "runtime_snapshot", archive.MAX_ARCHIVE_BYTES),
    )
    for name, digest, marker, limit in files:
        _copy_regular(
            bundle / name,
            authority_root / name,
            expected_sha256=digest,
            max_bytes=limit,
            marker=marker,
            boundary=boundary,
        )
    size_authority = {
        "source.bundle": payloads["source_bundle"]["size"],
        str(plan["artifact_name"]): plan["runtime_archive_size"],
    }
    for name, expected_size in size_authority.items():
        maximum = archive.MAX_ARCHIVE_BYTES if name == plan["artifact_name"] else MAX_RELEASE_PAYLOAD_BYTES
        if archive.file_evidence(authority_root / name, max_bytes=maximum)[1] != expected_size:
            raise ProvisionError("durable release payload size differs from the manifest")
    control_root = paths.tx_root(str(plan["transaction_id"])) / "control"
    try:
        if control_root.exists() or control_root.is_symlink():
            extracted = release.tree_evidence(control_root)
            names = {path.relative_to(control_root).as_posix() for path in control_root.rglob("*")}
            if extracted.tree_sha256 != plan["control_plane_tree_sha256"] or names != release.CONTROL_PLANE_MEMBERS:
                raise ProvisionError("durable control root differs from the QG authority")
        else:
            release.extract_archive(
                authority_root / "control-plane.tar",
                control_root,
                str(plan["control_plane_archive_sha256"]),
                str(plan["control_plane_tree_sha256"]),
                expected_paths=release.CONTROL_PLANE_MEMBERS,
            )
    except release.ContractError as exc:
        raise ProvisionError("durable control-plane extraction failed") from exc
    return authority_root
