"""Focused safety and recovery tests for the exact HA Python provisioner."""

from __future__ import annotations

import hashlib
import io
import json
import os
import shlex
import shutil
import subprocess
import tarfile
import threading
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from scripts.ha import provision_python_runtime_ha as provisioner
from scripts.ha import python_runtime_archive_contract as archive
from scripts.ha import python_runtime_provision_authority as authority_io
from scripts.ha import python_runtime_provision_commit as commit
from scripts.ha import python_runtime_provision_contract as contract
from scripts.ha import python_runtime_provision_coordinator as coordinator
from scripts.ha import python_runtime_provision_peer as peer
from scripts.ha import python_runtime_provision_rollback as rollback
from scripts.ha import python_runtime_provision_state as state
from scripts.ha import python_runtime_provision_trusted_launcher as launcher
from scripts.ha import python_runtime_provision_workflow_bootstrap as workflow_bridge
from scripts.ha import release_artifact_contract as release

ROOT = Path(__file__).resolve().parents[1]


def _plan() -> tuple[dict[str, Any], str]:
    payload: dict[str, Any] = {
        "schema": 1,
        "format": contract.PLAN_FORMAT,
        "transaction_id": "",
        "required_nodes": list(contract.NODES),
        "runtime_path": str(contract.RUNTIME_PATH),
        "artifact_name": release.PYTHON_RUNTIME_NAME,
        "artifact_sha256": release.PYTHON_RUNTIME_SHA256,
        "runtime_tree_sha256": release.PYTHON_RUNTIME_TREE_SHA256,
        "python_executable_sha256": release.PYTHON_EXECUTABLE_SHA256,
        "libpython_sha256": release.PYTHON_LIBPYTHON_SHA256,
        "control_plane_archive_sha256": "1" * 64,
        "control_plane_tree_sha256": "2" * 64,
        "wheelhouse_archive_sha256": "3" * 64,
        "wheelhouse_tree_sha256": "4" * 64,
        "wheelhouse_file_count": 7,
        "wheelhouse_total_size": 8192,
        "runtime_archive_size": 1234,
        "qg_repository": contract.EXPECTED_REPOSITORY,
        "qg_workflow_ref": contract.EXPECTED_WORKFLOW_REF,
        "qg_run_id": 123,
        "qg_run_attempt": 2,
        "qg_target_sha": "5" * 40,
        "qg_artifact_id": 456,
        "qg_artifact_api_sha256": "6" * 64,
        "qg_manifest_sha256": "7" * 64,
    }
    payload["transaction_id"] = f"pyr_{contract.digest_json(payload)[:32]}"
    digest = contract.digest_json(payload)
    contract.validate_plan(payload, digest)
    return payload, digest


def test_control_plane_allowlists_and_workflow_bridge_are_closed() -> None:
    from scripts.ha import bootstrap_meta_ha_contract as bootstrap
    from scripts.ha import python_runtime_provision_ingest_contract as ingest_contract

    assert set(release.CONTROL_PLANE_FILES) == launcher.CONTROL_FILES == ingest_contract.CONTROL_FILES
    required = {
        "scripts/ha/bootstrap_nested_runtime_quarantine.py",
        "scripts/ha/bootstrap_nested_runtime_evidence.py",
        "scripts/ha/do_lb_ready_contract.py",
    }
    nested_runtime_authority = {
        "scripts/ha/bootstrap_nested_runtime_evidence.py",
        "scripts/ha/bootstrap_nested_runtime_quarantine.py",
    }
    assert required <= set(release.CONTROL_PLANE_FILES)
    assert required <= bootstrap.RUNTIME_CONTROL_FILES
    assert nested_runtime_authority <= bootstrap.RUNTIME_CONTROL_FILES
    assert nested_runtime_authority <= set(release.CONTROL_PLANE_FILES)
    assert "scripts/ha/python_runtime_provision_workflow_bootstrap.py" in launcher.CONTROL_FILES
    workflow = (ROOT / ".github/workflows/provision-python-runtime-ha.yml").read_text(encoding="utf-8")
    bridge = ROOT / "scripts/ha/python_runtime_provision_workflow_bootstrap.py"
    bridge_sha = hashlib.sha256(bridge.read_bytes()).hexdigest()
    assert workflow.count(bridge_sha) == 2
    assert "environment: meta-social-cutover" in workflow
    assert "group: meta-social-cutover" in workflow
    assert "/usr/bin/python3 -B -I -S" in workflow
    assert "actions/download-artifact@d3f86a106a0bac45b974a628896c90dbdf5c8093" in workflow
    assert "if: inputs.OPERATION == 'apply'" in workflow


def test_actual_control_archive_contains_every_trusted_import(tmp_path: Path) -> None:
    source = tmp_path / "source"
    for relative in release.CONTROL_PLANE_FILES:
        destination = source / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes((ROOT / relative).read_bytes())
        destination.chmod(0o755 if relative.endswith(".sh") else 0o644)
    evidence = release.create_archive(source, tmp_path / "control-plane.tar")
    verified = release.verify_archive(
        tmp_path / "control-plane.tar",
        evidence.archive_sha256,
        evidence.tree_sha256,
        expected_paths=release.CONTROL_PLANE_MEMBERS,
    )
    assert verified.file_count == len(release.CONTROL_PLANE_FILES)
    with tarfile.open(tmp_path / "control-plane.tar", "r:") as bundle:
        members = {member.name for member in bundle}
    assert members == release.CONTROL_PLANE_MEMBERS
    for relative in release.CONTROL_PLANE_FILES:
        if relative.endswith(".py"):
            compile((source / relative).read_bytes(), relative, "exec")


def test_control_plane_archive_imports_bootstrap_dependencies(tmp_path: Path) -> None:
    import importlib.util
    import sys

    control_root = tmp_path / "control"
    for relative in release.CONTROL_PLANE_FILES:
        destination = control_root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes((ROOT / relative).read_bytes())
    inserted = str(control_root)
    if inserted not in sys.path:
        sys.path.insert(0, inserted)
    spec = importlib.util.spec_from_file_location(
        "bootstrap_meta_ha_contract_import_test",
        control_root / "scripts/ha/bootstrap_meta_ha_contract.py",
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module._nested.NESTED_RUNTIME_NAME == "linaslaserbot-2.7.22"
    assert module._nested_evidence.NESTED_RUNTIME_NAME == "linaslaserbot-2.7.22"
    assert Path(module._nested_evidence.__file__) == Path(module._nested._evidence.__file__)
    assert module._lb_contract.LB_NETWORK_STACK == "DUALSTACK"
    absent = module._nested_evidence.portable_content_identity({"schema": 1, "present": False})
    assert absent["present"] is False and absent["file_count"] == 0


def test_nested_runtime_authenticated_dependencies_are_closed_and_non_circular() -> None:
    from scripts.ha import bootstrap_meta_ha_contract as bootstrap

    evidence_source = (ROOT / "scripts/ha/bootstrap_nested_runtime_evidence.py").read_text(encoding="utf-8")
    quarantine_source = (ROOT / "scripts/ha/bootstrap_nested_runtime_quarantine.py").read_text(encoding="utf-8")
    bootstrap_source = (ROOT / "scripts/ha/bootstrap_meta_ha_contract.py").read_text(encoding="utf-8")
    nested_runtime_authority = {
        "scripts/ha/bootstrap_nested_runtime_evidence.py",
        "scripts/ha/bootstrap_nested_runtime_quarantine.py",
    }
    assert nested_runtime_authority <= bootstrap.RUNTIME_CONTROL_FILES
    assert len(evidence_source.splitlines()) <= 500
    assert len(quarantine_source.splitlines()) <= 500
    assert "bootstrap_nested_runtime_quarantine" not in evidence_source
    assert "from scripts.ha" not in quarantine_source
    assert 'Path(__file__).with_name("bootstrap_nested_runtime_evidence.py")' in quarantine_source
    assert "_nested_evidence_spec" in bootstrap_source
    assert "bootstrap_nested_runtime_evidence.py" in bootstrap_source


def test_bootstrap_nested_runtime_modules_load_from_closed_control_tree_only(tmp_path: Path) -> None:
    import importlib.util

    control_root = tmp_path / "control"
    checkout = tmp_path / "checkout"
    checkout.mkdir()
    sentinel = tmp_path / "checkout-evidence-executed"
    for relative in release.CONTROL_PLANE_FILES:
        destination = control_root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes((ROOT / relative).read_bytes())
    evil = f"from pathlib import Path\nPath({str(sentinel)!r}).write_text('executed')\n" + (
        ROOT / "scripts/ha/bootstrap_nested_runtime_evidence.py"
    ).read_text(encoding="utf-8")
    (checkout / "scripts/ha").mkdir(parents=True)
    (checkout / "scripts/ha/bootstrap_nested_runtime_evidence.py").write_text(evil, encoding="utf-8")
    spec = importlib.util.spec_from_file_location(
        "bootstrap_meta_ha_contract_closed_tree_test",
        control_root / "scripts/ha/bootstrap_meta_ha_contract.py",
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert not sentinel.exists()
    assert module._nested_evidence.READ_CHUNK == 1024 * 1024


def test_remote_stage_materializes_full_bundle_control_and_launcher_receipt(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from scripts.ha import python_runtime_provision_ingest as ingest
    from scripts.ha import python_runtime_provision_ingest_contract as ingest_contract

    source = tmp_path / "source"
    for relative in release.CONTROL_PLANE_FILES:
        destination = source / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes((ROOT / relative).read_bytes())
        destination.chmod(0o755 if relative.endswith(".sh") else 0o644)
    control_path = tmp_path / "control-plane.tar"
    control = release.create_archive(source, control_path)
    wheelhouse = b"exact-wheelhouse"
    dashboard = b"exact-dashboard"
    source_bundle = b"exact-source-bundle"
    runtime = b"exact-runtime"
    manifest = {
        "schema": release.MANIFEST_SCHEMA,
        "repository": contract.EXPECTED_REPOSITORY,
        "workflow_path": release.WORKFLOW_PATH,
        "workflow_ref": contract.EXPECTED_WORKFLOW_REF,
        "run_id": 123,
        "run_attempt": 2,
        "target_sha": "5" * 40,
        "source_locks": {
            "requirements_lock_sha256": "1" * 64,
            "requirements_dev_lock_sha256": "2" * 64,
            "dashboard_package_lock_sha256": "3" * 64,
        },
        "toolchains": {
            "python": {
                "implementation": "CPython",
                "version": release.PYTHON_VERSION,
                "pip_version": release.PIP_VERSION,
                "cache_tag": release.PYTHON_CACHE_TAG,
                "platform": release.PYTHON_PLATFORM,
                "machine": release.PYTHON_MACHINE,
                "runtime_artifact_name": release.PYTHON_RUNTIME_NAME,
                "runtime_artifact_url": release.PYTHON_RUNTIME_URL,
                "runtime_artifact_sha256": hashlib.sha256(runtime).hexdigest(),
                "runtime_executable_name": "python3.13",
                "runtime_executable_sha256": release.PYTHON_EXECUTABLE_SHA256,
                "runtime_tree_sha256": release.PYTHON_RUNTIME_TREE_SHA256,
                "runtime_libpython_name": release.PYTHON_LIBPYTHON_NAME,
                "runtime_libpython_sha256": release.PYTHON_LIBPYTHON_SHA256,
            },
            "node": {"version": release.NODE_VERSION},
            "npm": {"version": release.NPM_VERSION},
        },
        "payloads": {
            "control_plane": {
                "archive": "control-plane.tar",
                "archive_sha256": control.archive_sha256,
                "tree_sha256": control.tree_sha256,
                "file_count": control.file_count,
                "total_size": control.total_size,
            },
            "wheelhouse": {
                "archive": "wheelhouse.tar",
                "archive_sha256": hashlib.sha256(wheelhouse).hexdigest(),
                "tree_sha256": "4" * 64,
                "file_count": 1,
                "total_size": len(wheelhouse),
            },
            "dashboard": {
                "archive": "dashboard-build.tar",
                "archive_sha256": hashlib.sha256(dashboard).hexdigest(),
                "tree_sha256": "8" * 64,
                "file_count": 1,
                "total_size": len(dashboard),
            },
            "source_bundle": {
                "file": "source.bundle",
                "sha256": hashlib.sha256(source_bundle).hexdigest(),
                "size": len(source_bundle),
                "target_sha": "5" * 40,
                "target_tree_sha": "9" * 40,
                "advertised_ref": "HEAD",
            },
            "python_runtime": {
                "file": release.PYTHON_RUNTIME_NAME,
                "sha256": hashlib.sha256(runtime).hexdigest(),
                "size": len(runtime),
            },
        },
    }
    manifest_raw = contract.canonical(manifest)
    plan, _old_plan_sha = _plan()
    plan.update(
        transaction_id="",
        qg_manifest_sha256=hashlib.sha256(manifest_raw).hexdigest(),
        control_plane_archive_sha256=control.archive_sha256,
        control_plane_tree_sha256=control.tree_sha256,
        wheelhouse_archive_sha256=hashlib.sha256(wheelhouse).hexdigest(),
        wheelhouse_tree_sha256="4" * 64,
        wheelhouse_file_count=1,
        wheelhouse_total_size=len(wheelhouse),
        runtime_archive_size=len(runtime),
    )
    plan["transaction_id"] = f"pyr_{contract.digest_json(plan)[:32]}"
    plan_raw = contract.canonical(plan)
    plan_sha = hashlib.sha256(plan_raw).hexdigest()
    state_root, lock = tmp_path / "state", tmp_path / "lock"
    uid, gid = os.getuid(), os.getgid()
    script = peer.REMOTE_STAGE.replace(
        'root=Path("/var/lib/linasbot/meta-ha"); lock=Path("/run/lock/linasbot-meta-live.lock")',
        f"UID={uid}; GID={gid}; root=Path({str(state_root)!r}); lock=Path({str(lock)!r})",
    )
    replacements = {
        "os.chown(path,0,0)": "os.chown(path,UID,GID)",
        "os.chown(target,0,0)": "os.chown(target,UID,GID)",
        "os.fchown(fd,0,0)": "os.fchown(fd,UID,GID)",
        "os.fchown(lfd,0,0)": "os.fchown(lfd,UID,GID)",
        "!=(0,0,mode)": "!=(UID,GID,mode)",
        "!=(0,0,mode,1)": "!=(UID,GID,mode,1)",
        "!=(0,0,0o600,1)": "!=(UID,GID,0o600,1)",
        "==(0,0,0o600,2,size)": "==(UID,GID,0o600,2,size)",
        "info.st_uid!=0 or info.st_gid!=0": "info.st_uid!=UID or info.st_gid!=GID",
    }
    for before, after in replacements.items():
        script = script.replace(before, after)
    script = script.replace(
        "from scripts.ha.python_runtime_provision_ingest import _install\n",
        "def _install(*args,**kwargs): return 0\n",
    )
    compile(script, "REMOTE_STAGE", "exec")
    tx_id = str(plan["transaction_id"])
    arguments = [
        tx_id,
        plan_sha,
        str(len(plan_raw)),
        hashlib.sha256(manifest_raw).hexdigest(),
        str(len(manifest_raw)),
        control.archive_sha256,
        str(control_path.stat().st_size),
        hashlib.sha256(wheelhouse).hexdigest(),
        str(len(wheelhouse)),
        hashlib.sha256(dashboard).hexdigest(),
        str(len(dashboard)),
        hashlib.sha256(source_bundle).hexdigest(),
        str(len(source_bundle)),
        release.PYTHON_RUNTIME_NAME,
        hashlib.sha256(runtime).hexdigest(),
        str(len(runtime)),
    ]
    payload = plan_raw + manifest_raw + control_path.read_bytes() + wheelhouse + dashboard + source_bundle + runtime

    def stage() -> subprocess.CompletedProcess[bytes]:
        return subprocess.run(
            [os.sys.executable, "-B", "-I", "-S", "-c", script, *arguments],
            input=payload,
            capture_output=True,
            check=False,
            timeout=20,
        )

    result = stage()
    assert result.returncode == 0, result.stderr.decode("utf-8", "replace")
    control_root = state_root / "python-runtime-transactions" / tx_id / "control"
    actual = release.tree_evidence(control_root)
    assert (
        actual.tree_sha256,
        actual.file_count,
        actual.total_size,
    ) == (
        control.tree_sha256,
        control.file_count,
        control.total_size,
    )
    assert {
        path.relative_to(control_root).as_posix() for path in control_root.rglob("*")
    } == release.CONTROL_PLANE_MEMBERS
    assert stage().returncode == 0

    shutil.rmtree(control_root)
    partial = control_root.parent / ".control.extracting"
    partial.mkdir(mode=0o700)
    (partial / "truncated").write_bytes(b"partial")
    assert stage().returncode == 0
    assert any(path.name.startswith(".quarantine-control-incomplete-") for path in control_root.parent.iterdir())

    uid, gid = os.getuid(), os.getgid()
    monkeypatch.setattr(ingest, "STATE_ROOT", state_root)
    monkeypatch.setattr(ingest, "LAUNCHER_RECEIPTS", state_root / "python-runtime-provision-launchers")
    monkeypatch.setattr(ingest_contract, "RUNTIME_SHA256", hashlib.sha256(runtime).hexdigest())
    monkeypatch.setattr(ingest_contract, "validate_launcher_receipt", lambda payload: payload)
    monkeypatch.setattr(archive, "EXPECTED_UID", uid)
    monkeypatch.setattr(archive, "EXPECTED_GID", gid)
    monkeypatch.setattr(ingest.os, "fchown", lambda *_args: None)
    monkeypatch.setattr(ingest.os, "chown", lambda *_args, **_kwargs: None)

    def secure_dir(path: Path, mode: int, *, create: bool = False) -> None:
        if create:
            path.mkdir(parents=True, exist_ok=True, mode=mode)
            path.chmod(mode)
        observed = path.lstat()
        assert (observed.st_uid, observed.st_gid, observed.st_mode & 0o777) == (uid, gid, mode)

    original_snapshot = ingest._snapshot_source
    monkeypatch.setattr(ingest, "_secure_dir", secure_dir)
    monkeypatch.setattr(
        ingest,
        "_snapshot_source",
        lambda source, destination, _source_uid, **kwargs: original_snapshot(source, destination, uid, **kwargs),
    )
    monkeypatch.setattr(
        ingest,
        "_root_evidence",
        lambda path, limit: archive.file_evidence(path, max_bytes=limit),
    )
    monkeypatch.setattr(
        ingest,
        "_source_evidence",
        lambda path, _source_uid, limit: archive.file_evidence(path, max_bytes=limit),
    )
    monkeypatch.setattr(
        ingest,
        "_load_manifest",
        lambda path, expected: (
            (
                json.loads(path.read_text(encoding="utf-8")),
                path.read_bytes(),
            )
            if hashlib.sha256(path.read_bytes()).hexdigest() == expected
            else pytest.fail("manifest digest changed")
        ),
    )
    monkeypatch.setattr(
        ingest,
        "_control_tree",
        lambda path: (
            release.tree_evidence(path).tree_sha256,
            release.tree_evidence(path).file_count,
            release.tree_evidence(path).total_size,
        ),
    )
    authority_root = control_root.parent / "authority"
    assert (
        ingest._install(
            authority_root,
            0,
            plan["qg_artifact_id"],
            plan["qg_artifact_api_sha256"],
            plan["qg_manifest_sha256"],
            plan["qg_run_id"],
            plan["qg_run_attempt"],
            plan["qg_target_sha"],
            retained_transaction_id=tx_id,
            emit_ack=False,
        )
        == 0
    )
    key = f"{plan['qg_artifact_id']}-{plan['qg_artifact_api_sha256']}"
    global_bundle = state_root / "release-bundles" / key
    global_control = state_root / "python-runtime-provision-control" / key
    launcher_receipt = state_root / "python-runtime-provision-launchers" / f"{key}.json"
    assert {path.name for path in global_bundle.iterdir()} == ingest_contract.FILES
    assert release.tree_evidence(global_control).tree_sha256 == control.tree_sha256
    receipt = json.loads(launcher_receipt.read_text(encoding="utf-8"))
    assert (
        receipt["launcher_sha256"]
        == hashlib.sha256(
            (global_control / "scripts/ha/python_runtime_provision_trusted_launcher.py").read_bytes()
        ).hexdigest()
    )


def test_plan_and_v2_receipts_bind_wheelhouse_and_reject_forgery() -> None:
    plan, plan_sha = _plan()
    nodes = {node: contract.node_receipt(plan, plan_sha, node) for node in contract.NODES}
    hashes = {node: contract.digest_json(receipt) for node, receipt in nodes.items()}
    cluster = contract.cluster_receipt(plan, plan_sha, hashes)
    for node, receipt in nodes.items():
        assert contract.validate_node_receipt(receipt, plan, plan_sha)["node_id"] == node
        assert receipt["wheelhouse_archive_sha256"] == plan["wheelhouse_archive_sha256"]
    assert contract.validate_cluster_receipt(cluster, plan, plan_sha) == cluster

    forged = dict(plan)
    forged["transaction_id"] = "pyr_" + "f" * 32
    with pytest.raises(archive.ProvisionError, match="transaction ID"):
        contract.validate_plan(forged)
    zero = dict(plan)
    zero["control_plane_tree_sha256"] = "0" * 64
    zero["transaction_id"] = ""
    zero["transaction_id"] = f"pyr_{contract.digest_json(zero)[:32]}"
    with pytest.raises(archive.ProvisionError, match="digest"):
        contract.validate_plan(zero)


def test_write_all_retries_forced_partial_writes(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    target = tmp_path / "payload"
    descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    original = os.write

    def partial(fd: int, payload: bytes | memoryview) -> int:
        return original(fd, bytes(payload[: max(1, len(payload) // 3)]))

    monkeypatch.setattr(archive.os, "write", partial)
    try:
        archive.write_all(descriptor, b"partial-write-regression" * 100)
    finally:
        os.close(descriptor)
    assert target.read_bytes() == b"partial-write-regression" * 100


def test_runtime_extraction_retries_partial_writes_and_rejects_hardlinks(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    tmp_path.chmod(0o755)
    runtime_tar = tmp_path / "runtime.tar.gz"
    with tarfile.open(runtime_tar, "w:gz") as bundle:
        root = tarfile.TarInfo("python")
        root.type, root.mode = tarfile.DIRTYPE, 0o777
        bundle.addfile(root)
        data = b"runtime-member" * 1000
        item = tarfile.TarInfo("python/data")
        item.mode, item.size = 0o666, len(data)
        bundle.addfile(item, io.BytesIO(data))
        link = tarfile.TarInfo("python/link")
        link.type, link.mode, link.linkname = tarfile.SYMTYPE, 0o777, "data"
        bundle.addfile(link)
    monkeypatch.setattr(archive, "EXPECTED_UID", os.getuid())
    monkeypatch.setattr(archive, "EXPECTED_GID", os.getgid())
    monkeypatch.setattr(archive, "RUNTIME_SHA256", hashlib.sha256(runtime_tar.read_bytes()).hexdigest())
    original = os.write

    def partial(fd: int, payload: bytes | memoryview) -> int:
        return original(fd, bytes(payload[: max(1, len(payload) // 5)]))

    monkeypatch.setattr(archive.os, "write", partial)
    destination = tmp_path / "runtime"
    archive.extract_runtime_archive(runtime_tar, destination)
    assert (destination / "data").read_bytes() == data
    assert os.readlink(destination / "link") == "data"
    assert (destination / "data").stat().st_mode & 0o777 == 0o644

    hardlink_tar = tmp_path / "hardlink.tar.gz"
    with tarfile.open(hardlink_tar, "w:gz") as bundle:
        root = tarfile.TarInfo("python")
        root.type, root.mode = tarfile.DIRTYPE, 0o755
        bundle.addfile(root)
        link = tarfile.TarInfo("python/hard")
        link.type, link.linkname = tarfile.LNKTYPE, "python/data"
        bundle.addfile(link)
    monkeypatch.setattr(archive, "RUNTIME_SHA256", hashlib.sha256(hardlink_tar.read_bytes()).hexdigest())
    with pytest.raises(archive.ProvisionError, match="hardlink or device"):
        archive.extract_runtime_archive(hardlink_tar, tmp_path / "rejected")


def test_nlink_two_publication_is_adopted_without_deleting_live_writer(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(archive, "EXPECTED_UID", os.getuid())
    monkeypatch.setattr(archive, "EXPECTED_GID", os.getgid())
    tmp_path.chmod(0o700)
    published = tmp_path / "state.json"
    temporary = tmp_path / ".state.json.writing"
    temporary.write_bytes(b"payload")
    temporary.chmod(0o600)
    os.link(temporary, published)
    assert published.stat().st_nlink == 2
    assert authority_io.secure_state_file(published) == b"payload"
    assert published.stat().st_nlink == 1 and not temporary.exists()

    separate = tmp_path / ".state.json.writing"
    separate.write_bytes(b"new")
    separate.chmod(0o600)
    ready = threading.Event()
    finished = threading.Event()

    def writer() -> None:
        ready.set()
        finished.wait(2)
        os.replace(separate, published)

    thread = threading.Thread(target=writer)
    thread.start()
    ready.wait(2)
    assert authority_io.secure_state_file(published) == b"payload"
    assert separate.exists()
    finished.set()
    thread.join(2)
    assert published.read_bytes() == b"new"


def test_local_active_nlink_two_crash_is_adopted_by_exact_retry(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    plan, plan_sha = _plan()
    monkeypatch.setattr(archive, "EXPECTED_UID", os.getuid())
    monkeypatch.setattr(archive, "EXPECTED_GID", os.getgid())
    tmp_path.chmod(0o700)
    paths = state.ProvisionPaths(state_root=tmp_path, runtime=tmp_path / "runtime", lock_path=tmp_path / "lock")
    payload = contract.canonical(state._active_payload(plan, plan_sha, "node01"))
    temporary = tmp_path / f".{state.ACTIVE_NAME}.writing"
    temporary.write_bytes(payload)
    temporary.chmod(0o600)
    os.link(temporary, paths.active)
    state.claim_active(paths, plan, plan_sha, "node01")
    assert not temporary.exists()
    assert paths.active.stat().st_nlink == 1


def test_peer_uses_one_shell_quoted_command_and_bounded_stream() -> None:
    command = peer._ssh_command("-c", "print('semi; line')\n", "argument with spaces")
    assert command[0] == "/usr/bin/ssh"
    assert len(command) == len(peer.SSH_OPTIONS) + 3
    remote = shlex.split(command[-1])
    assert remote[:6] == [
        "/usr/bin/env",
        "-i",
        "HOME=/root",
        "LANG=C.UTF-8",
        "LC_ALL=C.UTF-8",
        "PATH=/usr/sbin:/usr/bin:/sbin:/bin",
    ]
    assert remote[-3:] == ["-c", "print('semi; line')\n", "argument with spaces"]
    code, stdout, stderr = peer._bounded_pump(["/bin/cat"], [b"a" * 100_000, b"tail"], timeout=5)
    assert (code, stdout, stderr) == (0, b"a" * 100_000 + b"tail", b"")


def test_run_bootstrap_verifies_os_authority_before_canonical_exec(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    plan, plan_sha = _plan()
    manifest = {
        "payloads": {
            "wheelhouse": {
                "archive": "wheelhouse.tar",
                "archive_sha256": plan["wheelhouse_archive_sha256"],
                "tree_sha256": plan["wheelhouse_tree_sha256"],
                "file_count": plan["wheelhouse_file_count"],
                "total_size": plan["wheelhouse_total_size"],
            },
            "python_runtime": {
                "file": plan["artifact_name"],
                "sha256": plan["artifact_sha256"],
                "size": plan["runtime_archive_size"],
            },
        }
    }
    tx_root, control = tmp_path / "tx", tmp_path / "tx/control"
    monkeypatch.setattr(
        launcher,
        "_transaction_authority",
        lambda _values: (tx_root, control, plan, manifest, plan_sha),
    )
    monkeypatch.setattr(release, "validate_manifest", lambda *_args, **_kwargs: manifest)
    monkeypatch.setattr(
        archive,
        "file_evidence",
        lambda path, **_kwargs: (
            (plan["wheelhouse_archive_sha256"], 99)
            if path.name == "wheelhouse.tar"
            else (plan["artifact_sha256"], plan["runtime_archive_size"])
        ),
    )
    monkeypatch.setattr(
        archive, "verify_runtime_before_use", lambda *_args, **_kwargs: (plan["runtime_tree_sha256"], 1)
    )
    node = contract.node_receipt(plan, plan_sha, "node01")
    node_raw = contract.canonical(node)
    cluster = contract.cluster_receipt(
        plan, plan_sha, {"node01": hashlib.sha256(node_raw).hexdigest(), "node02": "8" * 64}
    )
    receipts = {"cluster": cluster}
    monkeypatch.setattr(
        launcher,
        "_json",
        lambda path: (
            (node, node_raw)
            if path.name == "python-runtime-provisioned.json"
            else (receipts["cluster"], contract.canonical(receipts["cluster"]))
        ),
    )
    monkeypatch.setattr(launcher.socket, "gethostname", lambda: "ubuntu-s-2vcpu-2gb-90gb-intel-lon1-01")
    monkeypatch.setattr(launcher, "STATE_ROOT", tmp_path / "state")
    observed: dict[str, Any] = {}

    def execute(path: str, argv: list[str], env: dict[str, str]) -> None:
        observed.update(path=path, argv=argv, env=env)
        raise RuntimeError("exec-sentinel")

    monkeypatch.setattr(launcher.os, "execve", execute)
    with pytest.raises(RuntimeError, match="exec-sentinel"):
        launcher._run_bootstrap([str(tx_root), str(control), plan_sha, "node-phase", "status"])
    assert observed["path"] == str(contract.RUNTIME_PATH / "bin/python3.13")
    assert observed["argv"][:5] == [observed["path"], "-B", "-I", "-S", "-c"]
    assert observed["argv"][-2:] == ["node-phase", "status"]
    assert all(not key.startswith("PYTHON") for key in observed["env"])

    receipts["cluster"] = contract.cluster_receipt(plan, plan_sha, {"node01": "f" * 64, "node02": "8" * 64})
    with pytest.raises(launcher.LaunchError, match="node binding"):
        launcher._run_bootstrap([str(tx_root), str(control), plan_sha, "node-phase", "status"])


def test_clean_host_initial_ingests_before_transaction_apply(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    module_bytes = {name: f"trusted-{name}\n".encode() for name in workflow_bridge.NODE_MODULES}
    upload = Path("/tmp/linasbot-python-runtime-upload-100-2")
    state_root = tmp_path / "state"
    commands: list[list[str]] = []
    monkeypatch.setattr(workflow_bridge, "STATE_ROOT", state_root)
    monkeypatch.setattr(workflow_bridge, "_directory", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(workflow_bridge, "_publish", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(workflow_bridge, "_read", lambda path, *_args, **_kwargs: module_bytes[path.name])

    def invoke(command: list[str]) -> str:
        commands.append(command)
        if len(commands) == 1:
            key = f"9-{'a' * 64}"
            return workflow_bridge._canonical(
                {
                    "schema": 1,
                    "bundle_root": str(state_root / "release-bundles" / key),
                    "control_root": str(state_root / "python-runtime-provision-control" / key),
                }
            ).decode()
        return '{"schema":1,"status":"committed"}\n'

    monkeypatch.setattr(workflow_bridge, "_invoke", invoke)
    hashes: list[str] = []
    for alias in workflow_bridge.NODE_MODULES:
        raw = module_bytes[alias]
        hashes.extend((hashlib.sha256(raw).hexdigest(), str(len(raw))))
    values = [
        str(upload),
        "100",
        "2",
        "0",
        "9",
        "a" * 64,
        "b" * 64,
        "10",
        "1",
        "c" * 40,
        "d" * 64,
        "APPLY_PYTHON_RUNTIME_CONFIRM",
        *hashes,
    ]
    assert workflow_bridge._initial(values) == 0
    assert commands[0][:5] == [
        workflow_bridge.OS_PYTHON,
        "-B",
        "-I",
        "-S",
        str(Path("/run/linas-python-runtime-bootstrap-100-2/launcher.py")),
    ]
    assert commands[0][5] == "ingest"
    assert commands[1][0:4] == [workflow_bridge.OS_PYTHON, "-B", "-I", "-S"]
    assert "run-bundle" in commands[1] and "apply" in commands[1]
    assert "committed" in capsys.readouterr().out


def test_malicious_live_checkout_cannot_preempt_authenticated_ingest_import(tmp_path: Path) -> None:
    trusted = tmp_path / "trusted"
    live = tmp_path / "live"
    for root in (trusted, live):
        (root / "scripts/ha").mkdir(parents=True)
    trusted_sentinel = tmp_path / "trusted-ran"
    live_sentinel = tmp_path / "live-ran"
    trusted_ingest = (
        f"from pathlib import Path\ndef main(values): Path({str(trusted_sentinel)!r}).write_text('trusted'); return 0\n"
    ).encode()
    trusted_contract = b"TRUSTED_CONTRACT = True\n"
    (trusted / "scripts/ha/python_runtime_provision_ingest.py").write_bytes(trusted_ingest)
    (trusted / "scripts/ha/python_runtime_provision_ingest_contract.py").write_bytes(trusted_contract)
    (live / "scripts/ha/python_runtime_provision_ingest.py").write_text(
        f"from pathlib import Path\nPath({str(live_sentinel)!r}).write_text('live')\n",
        encoding="utf-8",
    )
    driver = tmp_path / "driver.py"
    driver.write_text(
        "import hashlib,importlib.util\n"
        f"spec=importlib.util.spec_from_file_location('trusted_launcher',{str(ROOT / 'scripts/ha/python_runtime_provision_trusted_launcher.py')!r})\n"
        "module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)\n"
        "module._secure_dir=lambda *a,**k:None\n"
        "module._read=lambda path,*a,**k:path.read_bytes()\n"
        f"root={str(trusted)!r}\n"
        f"a={hashlib.sha256(trusted_ingest).hexdigest()!r};b={hashlib.sha256(trusted_contract).hexdigest()!r}\n"
        "raise SystemExit(module._run_ingest([root,a,str(len(open(root+'/scripts/ha/python_runtime_provision_ingest.py','rb').read())),b,str(len(open(root+'/scripts/ha/python_runtime_provision_ingest_contract.py','rb').read())),"
        + ",".join(repr(str(tmp_path / f"arg-{index}")) for index in range(8))
        + "]))\n",
        encoding="utf-8",
    )
    result = subprocess.run(
        [os.sys.executable, "-B", "-I", "-S", str(driver)],
        cwd=live,
        capture_output=True,
        text=True,
        check=False,
        timeout=10,
    )
    assert result.returncode == 0, result.stderr
    assert trusted_sentinel.read_text(encoding="utf-8") == "trusted"
    assert not live_sentinel.exists()


def test_workflow_never_contacts_production_for_plan_or_dry_run() -> None:
    workflow = (ROOT / ".github/workflows/provision-python-runtime-ha.yml").read_text(encoding="utf-8")
    assert "if: inputs.OPERATION == 'apply' || inputs.OPERATION == 'status'" in workflow
    assert "if: inputs.OPERATION == 'plan' || inputs.OPERATION == 'dry-run' || inputs.OPERATION == 'apply'" in workflow
    assert "persist-credentials: false" in workflow
    for action in ("actions/checkout@", "actions/download-artifact@", "appleboy/scp-action@", "appleboy/ssh-action@"):
        line = next(line for line in workflow.splitlines() if action in line)
        assert len(line.rsplit("@", 1)[1].strip()) == 40


@pytest.mark.parametrize(
    "name",
    ["python-runtime-provision.active", "python-runtime-provision.coordinator.json"],
)
def test_other_ha_mutators_reject_durable_python_provision_collisions(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, name: str
) -> None:
    from scripts.ha import controlled_meta_failover as failover
    from scripts.ha import rekey_meta_whatsapp_credentials as rekey
    from scripts.ha import retire_meta_registry_nfs_ha as retire
    from scripts.ha import sync_meta_env_to_peer as sync

    collision = tmp_path / name
    collision.parent.mkdir(parents=True, exist_ok=True)
    collision.write_text("active\n", encoding="utf-8")
    collision.chmod(0o600)
    tmp_path.chmod(0o700)
    assert name in {path.name for path in rekey.REKEY_COLLISION_PATHS}
    assert name in {path.name for path in retire.OTHER_TRANSACTION_PATHS}
    assert name in {path.name for path in failover.COLLISION_PATHS}

    with pytest.raises(RuntimeError, match="transaction"):
        rekey._require_no_conflicting_ha_transaction((collision,))

    monkeypatch.setattr(retire, "OTHER_TRANSACTION_PATHS", (collision,))
    monkeypatch.setattr(retire, "VOLATILE_MAINTENANCE", tmp_path / "volatile-missing")
    with pytest.raises(retire.NfsRetirementError, match="transaction"):
        retire._assert_no_other_transaction()

    monkeypatch.setattr(failover, "STATE_ROOT", tmp_path)
    monkeypatch.setattr(failover, "COLLISION_PATHS", (collision,))
    monkeypatch.setattr(failover, "_secure_directory", lambda _path: None)
    with pytest.raises(RuntimeError, match="transaction"):
        failover._assert_no_collision()

    with pytest.raises(RuntimeError, match="Python runtime provision"):
        sync._refuse_conflicting_ha_transaction(tmp_path)


def test_apply_snapshots_authority_before_coordinator_publication(monkeypatch: pytest.MonkeyPatch) -> None:
    plan, plan_sha = _plan()
    events: list[str] = []
    fake_authority = SimpleNamespace(bundle_path=lambda _root: Path("/protected/release"))
    paths = state.ProvisionPaths()
    arguments = SimpleNamespace(
        plan_sha256=plan_sha,
        confirm=f"APPLY_PYTHON_RUNTIME_{plan_sha.upper()}",
    )
    monkeypatch.setattr(provisioner, "_authority", lambda _arguments: fake_authority)
    monkeypatch.setattr(contract, "build_plan", lambda *_args, **_kwargs: (plan, plan_sha))
    monkeypatch.setattr(state, "common_lock", lambda _paths: nullcontext())
    monkeypatch.setattr(state, "_ensure_roots", lambda *_args: events.append("roots"))
    monkeypatch.setattr(coordinator, "terminal", lambda *_args: None)
    monkeypatch.setattr(state, "assert_no_collisions", lambda *_args: events.append("collisions"))
    monkeypatch.setattr(state, "snapshot_authority", lambda *_args: events.append("snapshot"))
    monkeypatch.setattr(coordinator, "template", lambda *_args: {"phase": "started"})
    monkeypatch.setattr(coordinator, "write", lambda *_args, **_kwargs: events.append("coordinator"))
    monkeypatch.setattr(
        provisioner,
        "_continue_commit",
        lambda *_args: events.append("commit") or {"status": "committed"},
    )
    assert provisioner._new_apply(arguments, paths) == {"status": "committed"}
    assert events.index("snapshot") < events.index("coordinator") < events.index("commit")


def test_crash_boundary_namespace_is_closed_and_every_boundary_is_injectable() -> None:
    seen: list[str] = []
    state.set_failpoint_hook(seen.append)
    try:
        for name in state.CRASH_BOUNDARIES:
            state.boundary(name)
        with pytest.raises(AssertionError, match="unreviewed crash boundary"):
            state.boundary("after-unreviewed-publication")
    finally:
        state.set_failpoint_hook(None)
    assert tuple(seen) == state.CRASH_BOUNDARIES
    for required in (
        "after_active_publish",
        "after_plan_snapshot",
        "after_manifest_snapshot_publish",
        "after_control_snapshot_publish",
        "after_wheelhouse_snapshot_publish",
        "after_dashboard_snapshot_publish",
        "after_source_bundle_snapshot_publish",
        "after_runtime_snapshot_publish",
        "after_candidate_rename",
        "after_decision_publish",
        "after_runtime_rename",
        "after_node_receipt",
        "after_cluster_receipt",
        "after_committed_journal",
        "after_rollback_runtime_rename",
        "after_rollback_baseline_rename",
        "after_rollback_terminal_journal",
        "after_active_clear",
        "after_coordinator_clear",
    ):
        assert required in state.CRASH_BOUNDARIES


@pytest.mark.parametrize(
    ("field", "value", "error"),
    [
        ("node_id", "node03", "schema"),
        ("phase", "forged", "schema"),
        ("decision", "commit", "pre-decision"),
        ("node_receipt_sha256", "a" * 64, "pre-decision"),
        ("had_previous", 1, "schema"),
    ],
)
def test_node_journal_rejects_forged_or_mixed_state(
    monkeypatch: pytest.MonkeyPatch, field: str, value: Any, error: str
) -> None:
    plan, plan_sha = _plan()
    journal = state._journal_template(plan, plan_sha, "node01", False)
    journal[field] = value
    monkeypatch.setattr(state, "_load_json", lambda _path: journal)
    with pytest.raises(archive.ProvisionError, match=error):
        state.load_journal(state.ProvisionPaths(), plan["transaction_id"])


def test_rollback_preflights_both_nodes_before_first_mutation(monkeypatch: pytest.MonkeyPatch) -> None:
    plan, plan_sha = _plan()
    paths = state.ProvisionPaths()
    authority_state = {
        "phase": "both-prepared",
        "decision": "undecided",
        "rollback_decision": "undecided",
    }
    events: list[str] = []
    monkeypatch.setattr(coordinator, "load", lambda _paths: (dict(authority_state), "9" * 64))
    monkeypatch.setattr(
        rollback,
        "staged_preflight",
        lambda *_args: events.append("local-preflight") or ({}, "a" * 64),
    )
    monkeypatch.setattr(peer, "stage_peer", lambda *_args: events.append("peer-stage") or Path("/peer/control"))

    def call_peer(_root: Path, arguments: list[str], **_kwargs: Any) -> dict[str, Any]:
        if arguments[0] == "_peer-rollback-preflight":
            events.append("peer-preflight")
            return {"preflight_sha256": "b" * 64}
        events.append("peer-mutate")
        return {"status": "rolled-back"}

    def update(_paths: state.ProvisionPaths, **changes: Any) -> dict[str, Any]:
        authority_state.update(changes)
        events.append(f"coordinator-{changes['phase']}")
        return dict(authority_state)

    monkeypatch.setattr(peer, "call_peer", call_peer)
    monkeypatch.setattr(coordinator, "update", update)
    monkeypatch.setattr(
        provisioner,
        "_local_rollback",
        lambda *_args: events.append("local-mutate") or {"status": "staged-aborted"},
    )
    monkeypatch.setattr(coordinator, "archive_and_clear", lambda _paths: events.append("archive"))
    result = provisioner._continue_rollback(paths, plan, plan_sha)
    assert result["status"] == "rolled-back"
    assert events.index("local-preflight") < events.index("peer-mutate")
    assert events.index("peer-preflight") < events.index("peer-mutate")
    assert events.index("peer-preflight") < events.index("local-mutate")


@pytest.mark.parametrize("terminal_phase", ["rolled-back", "compensated-rollback"])
def test_terminal_rollback_ack_loss_archives_without_replaying_peer(
    monkeypatch: pytest.MonkeyPatch, terminal_phase: str
) -> None:
    plan, plan_sha = _plan()
    paths = state.ProvisionPaths()
    authority_state = {"phase": terminal_phase}
    events: list[str] = []
    monkeypatch.setattr(coordinator, "load", lambda _paths: (authority_state, "a" * 64))
    monkeypatch.setattr(coordinator, "archive_and_clear", lambda _paths: events.append("archive"))
    monkeypatch.setattr(peer, "stage_peer", lambda *_args: pytest.fail("terminal replay contacted peer"))
    assert provisioner._continue_rollback(paths, plan, plan_sha) == {
        "schema": 1,
        "status": terminal_phase,
        "transaction_id": plan["transaction_id"],
    }
    assert events == ["archive"]


def test_durable_rollback_decision_controls_recovery_action(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    plan, plan_sha = _plan()
    tx_id = plan["transaction_id"]
    journal_sha = "b" * 64
    authority_state = {
        "transaction_id": tx_id,
        "plan_sha256": plan_sha,
        "phase": "rollback-preflight-durable",
        "decision": "commit",
        "rollback_decision": "rollback",
    }
    paths = state.ProvisionPaths(state_root=tmp_path, runtime=tmp_path / "runtime", lock_path=tmp_path / "lock")
    paths.coordinator.write_bytes(b"durable")
    arguments = SimpleNamespace(
        transaction_id=tx_id,
        journal_sha256=journal_sha,
        confirm=f"RECOVER_PYTHON_RUNTIME_{tx_id.upper()}_{journal_sha.upper()}_ROLLBACK",
    )
    monkeypatch.setattr(state, "common_lock", lambda _paths: nullcontext())
    monkeypatch.setattr(coordinator, "load", lambda _paths: (authority_state, journal_sha))
    monkeypatch.setattr(provisioner, "_load_durable_plan", lambda *_args: plan)
    monkeypatch.setattr(
        provisioner,
        "_continue_rollback",
        lambda *_args: {"status": "compensated-rollback"},
    )
    monkeypatch.setattr(provisioner, "_continue_commit", lambda *_args: pytest.fail("commit was selected"))
    assert provisioner._recovery(arguments, paths, rollback_requested=False) == {"status": "compensated-rollback"}


def test_missing_participant_journals_abort_staged_prefixes(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    plan, plan_sha = _plan()
    paths = state.ProvisionPaths(state_root=tmp_path, runtime=tmp_path / "runtime", lock_path=tmp_path / "lock")
    monkeypatch.setattr(
        rollback,
        "abort_staged",
        lambda _paths, _plan, _sha, node: {"schema": 1, "status": f"{node}-aborted"},
    )
    assert provisioner._local_rollback(paths, plan, plan_sha, "rollback", "a" * 64)["status"] == "node01-aborted"

    arguments = SimpleNamespace(
        command="_peer-rollback",
        transaction_id=plan["transaction_id"],
        plan_sha256=plan_sha,
        authority_decision="rollback",
        preflight_sha256="b" * 64,
    )
    monkeypatch.setattr(provisioner, "_assert_node_identity", lambda _node: None)
    monkeypatch.setattr(provisioner, "_load_durable_plan", lambda *_args: plan)
    monkeypatch.setattr(state, "common_lock", lambda _paths: nullcontext())
    assert provisioner._participant(arguments, paths)["status"] == "node02-aborted"


def test_terminal_coordinator_ack_loss_is_adopted_by_apply_and_recover(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    plan, plan_sha = _plan()
    monkeypatch.setattr(archive, "EXPECTED_UID", os.getuid())
    monkeypatch.setattr(archive, "EXPECTED_GID", os.getgid())
    tmp_path.chmod(0o700)
    paths = state.ProvisionPaths(state_root=tmp_path, runtime=tmp_path / "runtime", lock_path=tmp_path / "lock")
    tx_root = paths.tx_root(plan["transaction_id"])
    tx_root.mkdir(parents=True, mode=0o700)
    payload = coordinator.template(plan, plan_sha)
    node_hashes = {"node01": "8" * 64, "node02": "9" * 64}
    cluster = contract.cluster_receipt(plan, plan_sha, node_hashes)
    payload.update(
        phase="committed",
        decision="commit",
        node_receipt_sha256=node_hashes,
        cluster_receipt=cluster,
        cluster_receipt_sha256=contract.digest_json(cluster),
    )
    coordinator.write(paths, payload, no_replace=True)
    state.set_failpoint_hook(
        lambda name: (
            (_ for _ in ()).throw(RuntimeError("kill-before-clear")) if name == "before_coordinator_clear" else None
        )
    )
    try:
        with pytest.raises(RuntimeError, match="kill-before-clear"):
            coordinator.archive_and_clear(paths)
    finally:
        state.set_failpoint_hook(None)
    assert paths.coordinator.exists()
    terminal = coordinator.terminal(paths, plan["transaction_id"])
    assert terminal is not None
    archived, journal_sha = terminal
    assert coordinator.terminal(paths, plan["transaction_id"]) == (archived, journal_sha)

    fake_authority = SimpleNamespace(bundle_path=lambda _root: Path("/unneeded"))
    apply_arguments = SimpleNamespace(
        plan_sha256=plan_sha,
        confirm=f"APPLY_PYTHON_RUNTIME_{plan_sha.upper()}",
    )
    monkeypatch.setattr(provisioner, "_authority", lambda _args: fake_authority)
    monkeypatch.setattr(contract, "build_plan", lambda *_args, **_kwargs: (plan, plan_sha))
    monkeypatch.setattr(state, "common_lock", lambda _paths: nullcontext())
    monkeypatch.setattr(state, "_ensure_roots", lambda *_args: None)
    assert provisioner._new_apply(apply_arguments, paths)["status"] == "committed"
    assert not paths.coordinator.exists()

    recover_arguments = SimpleNamespace(
        transaction_id=plan["transaction_id"],
        journal_sha256=journal_sha,
        confirm=(f"RECOVER_PYTHON_RUNTIME_{plan['transaction_id'].upper()}_{journal_sha.upper()}_COMMIT"),
    )
    assert provisioner._recovery(recover_arguments, paths, rollback_requested=False)["status"] == "committed"

    coordinator.restore_terminal(paths, plan["transaction_id"], journal_sha)
    coordinator.update(
        paths,
        phase="rollback-preflight-durable",
        rollback_decision="rollback",
        rollback_preflight_sha256={"node01": "a" * 64, "node02": "b" * 64},
    )
    with pytest.raises(archive.ProvisionError, match="diverges"):
        provisioner._new_apply(apply_arguments, paths)


@pytest.mark.parametrize(
    "name",
    ["python-runtime-provision.active", "python-runtime-provision.coordinator.json"],
)
def test_clean_host_ingest_refuses_active_runtime_transaction_without_receipt_change(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, name: str
) -> None:
    from scripts.ha import python_runtime_provision_ingest_contract as ingest_contract

    state_root = tmp_path / "state"
    state_root.mkdir(mode=0o700)
    collision = state_root / name
    collision.write_bytes(b"active")
    receipt = state_root / "launcher.json"
    receipt.write_bytes(b"old-receipt")
    lock = tmp_path / "common.lock"
    monkeypatch.setattr(ingest_contract, "LOCK_PATH", lock)
    monkeypatch.setattr(ingest_contract.os, "fchown", lambda *_args: None)
    with pytest.raises(ingest_contract.IngestError, match="collides"):
        with ingest_contract.common_lock(state_root):
            pytest.fail("collision gate yielded")
    assert receipt.read_bytes() == b"old-receipt"


@pytest.mark.parametrize("phase", ["committed", "rolled-back", "compensated-rollback"])
def test_terminal_node_replay_clears_restaged_active(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, phase: str
) -> None:
    plan, plan_sha = _plan()
    paths = state.ProvisionPaths(state_root=tmp_path, runtime=tmp_path / "runtime", lock_path=tmp_path / "lock")
    tmp_path.mkdir(exist_ok=True)
    paths.active.write_bytes(contract.canonical(state._active_payload(plan, plan_sha, "node01")))
    journal = {
        "phase": phase,
        "plan": plan,
        "plan_sha256": plan_sha,
        "node_id": "node01",
        "decision": "commit" if phase != "rolled-back" else "rollback",
        "node_receipt_sha256": "8" * 64,
    }
    monkeypatch.setattr(state, "load_journal", lambda *_args: journal)
    monkeypatch.setattr(state, "_load_json", lambda _path: state._active_payload(plan, plan_sha, "node01"))
    monkeypatch.setattr(archive, "fsync_directory", lambda _path: None)
    if phase == "committed":
        raw = contract.canonical(contract.cluster_receipt(plan, plan_sha, {"node01": "8" * 64, "node02": "9" * 64}))
        monkeypatch.setattr(state, "_secure_state_file", lambda _path: raw)
        monkeypatch.setattr(archive, "verify_runtime_before_use", lambda _path: (plan["runtime_tree_sha256"], 1))
        commit.install_cluster_receipt(
            paths,
            plan["transaction_id"],
            contract.cluster_receipt(plan, plan_sha, {"node01": "8" * 64, "node02": "9" * 64}),
        )
    else:
        rollback.rollback_node(paths, plan["transaction_id"])
    assert not paths.active.exists()
