#!/usr/bin/env python3
"""OS-Python trust bridge into an authenticated runtime-provision control tree."""

from __future__ import annotations

import hashlib
import json
import os
import re
import socket
import stat
import sys
from pathlib import Path
from typing import Any, Final

TREE_DOMAIN = b"linasbot-release-tree-v1\0"
CONTROL_FILES = frozenset(
    {
        "deploy/systemd/95-linasbot-credential-rekey-guard.conf",
        "deploy/systemd/linasbot-worker@.service",
        "deploy/systemd/linasbot.service",
        "requirements.lock",
        "scripts/ha/bootstrap_meta_ha_contract.py",
        "scripts/ha/bootstrap_nested_runtime_quarantine.py",
        "scripts/ha/bootstrap_nested_runtime_evidence.py",
        "scripts/ha/bootstrap_nested_runtime_safety.py",
        "scripts/ha/bootstrap_nested_runtime_loader.py",
        "scripts/ha/bootstrap_nested_runtime_mount.py",
        "scripts/ha/cluster_runtime_env_contract.py",
        "scripts/ha/deploy_meta_release_ha.sh",
        "scripts/ha/do_lb_ready_contract.py",
        "scripts/ha/manage_do_lb_ready_healthcheck.py",
        "scripts/ha/production_mutation_guard.py",
        "scripts/ha/provision_python_runtime_ha.py",
        "scripts/ha/python_runtime_archive_contract.py",
        "scripts/ha/python_runtime_provision_authority.py",
        "scripts/ha/python_runtime_provision_commit.py",
        "scripts/ha/python_runtime_provision_coordinator.py",
        "scripts/ha/python_runtime_provision_contract.py",
        "scripts/ha/python_runtime_provision_ingest.py",
        "scripts/ha/python_runtime_provision_ingest_contract.py",
        "scripts/ha/python_runtime_provision_peer.py",
        "scripts/ha/python_runtime_provision_rollback.py",
        "scripts/ha/python_runtime_provision_state.py",
        "scripts/ha/python_runtime_provision_trusted_launcher.py",
        "scripts/ha/python_runtime_provision_workflow_bootstrap.py",
        "scripts/ha/release_archive_contract.py",
        "scripts/ha/release_artifact_contract.py",
        "scripts/ha/release_readiness_probe.py",
        "scripts/ha/release_verify_server.py",
        "scripts/ha/verify_meta_release_ha.sh",
    }
)
CONTROL_MEMBERS = frozenset({"deploy", "deploy/systemd", "scripts", "scripts/ha", *CONTROL_FILES})
SHA256_RE: Final = re.compile(r"[0-9a-f]{64}")
TX_RE: Final = re.compile(r"pyr_[0-9a-f]{32}")
STATE_ROOT: Final = Path("/var/lib/linasbot/meta-ha")
BOOTSTRAP_FILES: Final = {
    "scripts/ha/python_runtime_provision_ingest.py",
    "scripts/ha/python_runtime_provision_ingest_contract.py",
}
BOOTSTRAP_MEMBERS: Final = {"scripts", "scripts/ha", *BOOTSTRAP_FILES}


class LaunchError(RuntimeError):
    pass


def _canonical(value: dict[str, Any]) -> bytes:
    return (json.dumps(value, allow_nan=False, separators=(",", ":"), sort_keys=True) + "\n").encode()


def _read(path: Path, limit: int, *, mode: int | None = None) -> bytes:
    before = path.lstat()
    if (
        not stat.S_ISREG(before.st_mode)
        or stat.S_ISLNK(before.st_mode)
        or before.st_uid != 0
        or before.st_gid != 0
        or before.st_nlink != 1
        or before.st_size < 1
        or before.st_size > limit
        or (mode is not None and stat.S_IMODE(before.st_mode) != mode)
    ):
        raise LaunchError("trusted launcher input is unsafe")
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    try:
        opened = os.fstat(descriptor)
        chunks: list[bytes] = []
        consumed = 0
        while consumed < opened.st_size:
            chunk = os.read(descriptor, min(1024 * 1024, opened.st_size - consumed))
            if not chunk:
                raise LaunchError("trusted launcher input is truncated")
            chunks.append(chunk)
            consumed += len(chunk)
        after = os.fstat(descriptor)
    finally:
        os.close(descriptor)
    identity = ("st_dev", "st_ino", "st_size", "st_mtime_ns")
    if any(getattr(opened, key) != getattr(after, key) for key in identity):
        raise LaunchError("trusted launcher input changed while reading")
    return b"".join(chunks)


def _json(path: Path) -> tuple[dict[str, Any], bytes]:
    raw = _read(path, 1024 * 1024, mode=0o600)
    try:
        value = json.loads(raw.decode("utf-8", "strict"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise LaunchError("trusted launcher JSON is invalid") from exc
    if not isinstance(value, dict) or _canonical(value) != raw:
        raise LaunchError("trusted launcher JSON is not canonical")
    return value, raw


def _secure_dir(path: Path, mode: int) -> None:
    observed = path.lstat()
    if (
        not stat.S_ISDIR(observed.st_mode)
        or stat.S_ISLNK(observed.st_mode)
        or observed.st_uid != 0
        or observed.st_gid != 0
        or stat.S_IMODE(observed.st_mode) != mode
    ):
        raise LaunchError("trusted launcher directory is unsafe")


def _digest(value: str) -> str:
    if SHA256_RE.fullmatch(value) is None or value == "0" * 64:
        raise LaunchError("trusted launcher digest is invalid")
    return value


def _record(digest: Any, kind: str, name: str, mode: int, size: int, content: str | None) -> None:
    digest.update(json.dumps([kind, name, mode, size, content], separators=(",", ":")).encode() + b"\n")


def _control_tree(root: Path) -> tuple[str, int, int]:
    info = root.lstat()
    if not stat.S_ISDIR(info.st_mode) or stat.S_ISLNK(info.st_mode) or info.st_uid != 0 or info.st_gid != 0:
        raise LaunchError("trusted control root is unsafe")
    inventory: list[tuple[str, Path, os.stat_result]] = []
    for path in root.rglob("*"):
        name = path.relative_to(root).as_posix()
        if name not in CONTROL_MEMBERS:
            raise LaunchError("trusted control root has an unexpected path")
        observed = path.lstat()
        if observed.st_uid != 0 or observed.st_gid != 0 or stat.S_ISLNK(observed.st_mode):
            raise LaunchError("trusted control object is unsafe")
        inventory.append((name, path, observed))
    if {name for name, _path, _info in inventory} != CONTROL_MEMBERS:
        raise LaunchError("trusted control root is incomplete")
    digest = hashlib.sha256(TREE_DOMAIN)
    count = total = 0
    for name, path, observed in sorted(inventory, key=lambda item: item[0].encode("utf-8")):
        if stat.S_ISDIR(observed.st_mode) and stat.S_IMODE(observed.st_mode) == 0o755:
            _record(digest, "dir", name, 0o755, 0, None)
        elif (
            stat.S_ISREG(observed.st_mode)
            and observed.st_nlink == 1
            and stat.S_IMODE(observed.st_mode) in {0o644, 0o755}
        ):
            raw = _read(path, 8 * 1024**2)
            _record(digest, "file", name, stat.S_IMODE(observed.st_mode), len(raw), hashlib.sha256(raw).hexdigest())
            count += 1
            total += len(raw)
        else:
            raise LaunchError("trusted control mode or type is invalid")
    return digest.hexdigest(), count, total


def _manifest_control(manifest: dict[str, Any]) -> dict[str, Any]:
    payloads = manifest.get("payloads")
    if not isinstance(payloads, dict):
        raise LaunchError("trusted manifest payload is invalid")
    control = payloads.get("control_plane")
    if (
        not isinstance(control, dict)
        or set(control) != {"archive", "archive_sha256", "tree_sha256", "file_count", "total_size"}
        or control.get("archive") != "control-plane.tar"
    ):
        raise LaunchError("trusted manifest control authority is invalid")
    return control


def _verify_control(root: Path, expected: dict[str, Any]) -> None:
    if _control_tree(root) != (
        expected.get("tree_sha256"),
        expected.get("file_count"),
        expected.get("total_size"),
    ):
        raise LaunchError("trusted control tree differs from authority")


def _run(control_root: Path, arguments: list[str]) -> int:
    sys.path.insert(0, str(control_root))
    from scripts.ha.provision_python_runtime_ha import main
    from scripts.ha.python_runtime_archive_contract import ProvisionError

    try:
        return main(arguments)
    except ProvisionError as exc:
        raise LaunchError(f"runtime transaction failed: {exc}") from None


def _run_ingest(values: list[str]) -> int:
    if len(values) != 13:
        raise LaunchError("ingest launch arguments are incomplete")
    module_root = Path(values[0])
    _secure_dir(module_root, 0o700)
    observed_names: set[str] = set()
    for path in module_root.rglob("*"):
        relative = path.relative_to(module_root).as_posix()
        observed_names.add(relative)
        if relative not in BOOTSTRAP_MEMBERS:
            raise LaunchError("ingest bootstrap root has an unexpected path")
        if relative in {"scripts", "scripts/ha"}:
            _secure_dir(path, 0o755)
    if observed_names != BOOTSTRAP_MEMBERS:
        raise LaunchError("ingest bootstrap root is incomplete")
    authority = {
        "scripts/ha/python_runtime_provision_ingest.py": (_digest(values[1]), int(values[2])),
        "scripts/ha/python_runtime_provision_ingest_contract.py": (_digest(values[3]), int(values[4])),
    }
    for relative, (expected_sha, expected_size) in authority.items():
        raw = _read(module_root / relative, 8 * 1024**2, mode=0o600)
        if expected_size != len(raw) or hashlib.sha256(raw).hexdigest() != expected_sha:
            raise LaunchError("ingest bootstrap module differs from owner authority")
    sys.path.insert(0, str(module_root))
    from scripts.ha.python_runtime_provision_ingest import main

    return main(values[5:])


def _run_bundle(values: list[str]) -> int:
    if len(values) < 4:
        raise LaunchError("bundle launch arguments are incomplete")
    bundle, control = Path(values[0]), Path(values[1])
    manifest_sha = values[2]
    manifest, raw = _json(bundle / "release-manifest.json")
    if hashlib.sha256(raw).hexdigest() != manifest_sha:
        raise LaunchError("trusted bundle manifest digest is wrong")
    authority = _manifest_control(manifest)
    if (
        hashlib.sha256(_read(bundle / "control-plane.tar", 1024**3, mode=0o600)).hexdigest()
        != authority["archive_sha256"]
    ):
        raise LaunchError("trusted bundle control archive digest is wrong")
    _verify_control(control, authority)
    arguments = values[3:]
    if len(arguments) < 7 or arguments[0] not in {"plan", "dry-run", "apply"}:
        raise LaunchError("trusted bundle command is invalid")
    artifact_id, artifact_api_sha, command_manifest_sha = arguments[1:4]
    if not artifact_id.isdecimal() or int(artifact_id) < 1 or _digest(artifact_api_sha) != artifact_api_sha:
        raise LaunchError("trusted bundle artifact identity is invalid")
    if command_manifest_sha != manifest_sha:
        raise LaunchError("trusted bundle command manifest differs")
    expected_bundle = STATE_ROOT / "release-bundles" / f"{artifact_id}-{artifact_api_sha}"
    if bundle != expected_bundle or control != STATE_ROOT / "python-runtime-provision-control" / expected_bundle.name:
        raise LaunchError("trusted bundle paths differ from artifact authority")
    return _run(control, arguments)


def _plan_source(values: list[str]) -> int:
    if len(values) != 9:
        raise LaunchError("source plan arguments are incomplete")
    bundle, control = Path(values[0]), Path(values[1])
    manifest_sha = _digest(values[2])
    manifest, raw = _json(bundle / "release-manifest.json")
    if hashlib.sha256(raw).hexdigest() != manifest_sha:
        raise LaunchError("source plan manifest digest is wrong")
    control_authority = _manifest_control(manifest)
    control_raw = _read(bundle / "control-plane.tar", 1024**3, mode=0o600)
    if hashlib.sha256(control_raw).hexdigest() != control_authority["archive_sha256"]:
        raise LaunchError("source plan control archive digest is wrong")
    _verify_control(control, control_authority)
    sys.path.insert(0, str(control))
    from scripts.ha import python_runtime_provision_contract as contract

    authority = contract.Authority.build(*values[3:])
    plan, plan_sha = contract.build_plan(authority, bundle, enforce_path=False)
    print(
        json.dumps(
            {
                "schema": 1,
                "status": "read-only-plan",
                "plan": plan,
                "plan_sha256": plan_sha,
                "apply_confirmation": f"APPLY_PYTHON_RUNTIME_{plan_sha.upper()}",
            },
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        )
    )
    return 0


def _transaction_authority(values: list[str]) -> tuple[Path, Path, dict[str, Any], dict[str, Any], str]:
    if len(values) < 3:
        raise LaunchError("transaction launch arguments are incomplete")
    tx_root, control = Path(values[0]), Path(values[1])
    expected_plan_sha = _digest(values[2])
    plan, plan_raw = _json(tx_root / "authority/plan.json")
    manifest, manifest_raw = _json(tx_root / "authority/release-manifest.json")
    transaction_id = str(plan.get("transaction_id", ""))
    if (
        TX_RE.fullmatch(transaction_id) is None
        or tx_root != STATE_ROOT / "python-runtime-transactions" / transaction_id
        or control != tx_root / "control"
        or hashlib.sha256(plan_raw).hexdigest() != expected_plan_sha
    ):
        raise LaunchError("transaction plan or path authority is invalid")
    if hashlib.sha256(manifest_raw).hexdigest() != plan.get("qg_manifest_sha256"):
        raise LaunchError("transaction manifest digest differs from its plan")
    authority = _manifest_control(manifest)
    if authority.get("archive_sha256") != plan.get("control_plane_archive_sha256") or authority.get(
        "tree_sha256"
    ) != plan.get("control_plane_tree_sha256"):
        raise LaunchError("transaction control authority differs between plan and manifest")
    if (
        hashlib.sha256(_read(tx_root / "authority/control-plane.tar", 1024**3, mode=0o600)).hexdigest()
        != authority["archive_sha256"]
    ):
        raise LaunchError("transaction control archive digest is wrong")
    _verify_control(control, authority)
    return tx_root, control, plan, manifest, expected_plan_sha


def _run_transaction(values: list[str]) -> int:
    if len(values) < 4:
        raise LaunchError("transaction launch arguments are incomplete")
    _tx_root, control, _plan, _manifest, _plan_sha = _transaction_authority(values[:3])
    return _run(control, values[3:])


def _run_bootstrap(values: list[str]) -> int:
    if len(values) < 4:
        raise LaunchError("bootstrap launch arguments are incomplete")
    tx_root, control, plan, manifest, plan_sha = _transaction_authority(values[:3])
    sys.path.insert(0, str(control))
    from scripts.ha import python_runtime_archive_contract as runtime
    from scripts.ha import python_runtime_provision_contract as contract
    from scripts.ha import release_artifact_contract as release

    contract.validate_plan(plan, plan_sha)
    try:
        release.validate_manifest(
            manifest,
            expected_repository=plan["qg_repository"],
            expected_workflow_ref=plan["qg_workflow_ref"],
            expected_run_id=plan["qg_run_id"],
            expected_run_attempt=plan["qg_run_attempt"],
            expected_target_sha=plan["qg_target_sha"],
        )
    except release.ContractError as exc:
        raise LaunchError("bootstrap release manifest is invalid") from exc
    wheelhouse = manifest["payloads"]["wheelhouse"]
    runtime_payload = manifest["payloads"]["python_runtime"]
    if (
        wheelhouse["archive_sha256"] != plan["wheelhouse_archive_sha256"]
        or wheelhouse["tree_sha256"] != plan["wheelhouse_tree_sha256"]
        or wheelhouse["file_count"] != plan["wheelhouse_file_count"]
        or wheelhouse["total_size"] != plan["wheelhouse_total_size"]
        or runtime_payload["sha256"] != plan["artifact_sha256"]
        or runtime_payload["size"] != plan["runtime_archive_size"]
    ):
        raise LaunchError("bootstrap retained payload authority differs from the plan")
    wheelhouse_evidence = runtime.file_evidence(tx_root / "authority/wheelhouse.tar", max_bytes=1024**3)
    runtime_evidence = runtime.file_evidence(
        tx_root / "authority" / str(plan["artifact_name"]), max_bytes=256 * 1024**2
    )
    if wheelhouse_evidence[0] != plan["wheelhouse_archive_sha256"] or runtime_evidence != (
        plan["artifact_sha256"],
        plan["runtime_archive_size"],
    ):
        raise LaunchError("bootstrap retained payload bytes differ from the plan")
    node_receipt, node_raw = _json(STATE_ROOT / "python-runtime-provisioned.json")
    cluster_receipt, _cluster_raw = _json(STATE_ROOT / "python-runtime-cluster.json")
    try:
        node = contract.validate_node_receipt(node_receipt, plan, plan_sha)
        cluster = contract.validate_cluster_receipt(cluster_receipt, plan, plan_sha)
    except runtime.ProvisionError as exc:
        raise LaunchError("bootstrap runtime receipt authority is invalid") from exc
    expected_host = {
        "node01": "ubuntu-s-2vcpu-2gb-90gb-intel-lon1-01",
        "node02": "linas-app-lon1-02",
    }[node["node_id"]]
    if (
        socket.gethostname() != expected_host
        or cluster["node_receipt_sha256"][node["node_id"]] != hashlib.sha256(node_raw).hexdigest()
    ):
        raise LaunchError("bootstrap runtime receipt node binding is invalid")
    if any(
        path.exists() or path.is_symlink()
        for path in (
            STATE_ROOT / "python-runtime-provision.active",
            STATE_ROOT / "python-runtime-provision.coordinator.json",
        )
    ):
        raise LaunchError("bootstrap cannot overlap runtime provisioning")
    if (
        runtime.verify_runtime_before_use(contract.RUNTIME_PATH, execute_self_check=False)[0]
        != plan["runtime_tree_sha256"]
    ):
        raise LaunchError("bootstrap runtime tree differs from the committed plan")
    code = (
        "import sys;sys.path.insert(0,sys.argv[1]);"
        "from scripts.ha.bootstrap_meta_ha_contract import main;"
        "raise SystemExit(main(sys.argv[2:]))"
    )
    executable = str(contract.RUNTIME_PATH / "bin/python3.13")
    os.execve(
        executable,
        [executable, "-B", "-I", "-S", "-c", code, str(control), *values[3:]],
        {"HOME": "/root", "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8", "PATH": "/usr/sbin:/usr/bin:/sbin:/bin"},
    )


def main(argv: list[str] | None = None) -> int:
    values = sys.argv[1:] if argv is None else argv
    if os.geteuid() != 0 or not (sys.flags.isolated and sys.flags.no_site and sys.flags.dont_write_bytecode):
        raise LaunchError("trusted launcher requires root OS Python with -B -I -S")
    if any(name.startswith("PYTHON") for name in os.environ):
        raise LaunchError("trusted launcher forbids ambient Python controls")
    if not values:
        raise LaunchError("trusted launcher operation is missing")
    operation, arguments = values[0], values[1:]
    if operation == "ingest":
        return _run_ingest(arguments)
    if operation == "plan-source":
        return _plan_source(arguments)
    if operation == "run-bundle":
        return _run_bundle(arguments)
    if operation == "run-transaction":
        return _run_transaction(arguments)
    if operation == "run-bootstrap":
        return _run_bootstrap(arguments)
    raise LaunchError("trusted launcher operation is invalid")


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (LaunchError, OSError, ValueError) as exc:
        print(f"[python-runtime-launcher] ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
