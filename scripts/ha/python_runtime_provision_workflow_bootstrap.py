#!/usr/bin/env python3
"""Fixed OS-Python bridge from a protected workflow to QG runtime controls."""

from __future__ import annotations

import hashlib
import io
import json
import os
import re
import stat
import subprocess
import sys
import tarfile
from pathlib import Path, PurePosixPath
from typing import Any, Final

STATE_ROOT: Final = Path("/var/lib/linasbot/meta-ha")
RUNTIME_NAME: Final = "cpython-3.13.15+20260814-x86_64-unknown-linux-gnu-install_only_stripped.tar.gz"
# fmt: off
FILES: Final = {"release-manifest.json", "wheelhouse.tar", "dashboard-build.tar", "control-plane.tar", "source.bundle", RUNTIME_NAME}
BOOTSTRAP_MODULES: Final = {"scripts/ha/release_archive_contract.py", "scripts/ha/release_artifact_contract.py"}
NODE_MODULES: Final = {
    "launcher.py": "scripts/ha/python_runtime_provision_trusted_launcher.py",
    "ingest.py": "scripts/ha/python_runtime_provision_ingest.py",
    "ingest_contract.py": "scripts/ha/python_runtime_provision_ingest_contract.py",
}
# fmt: on
SHA256_RE: Final = re.compile(r"[0-9a-f]{64}")
SHA_RE: Final = re.compile(r"[0-9a-f]{40}")
TX_RE: Final = re.compile(r"pyr_[0-9a-f]{32}")
OS_PYTHON: Final = "/usr/bin/python3"
CHILD_ENV: Final = {"HOME": "/root", "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8", "PATH": "/usr/sbin:/usr/bin:/sbin:/bin"}


class BootstrapError(RuntimeError):
    pass


def _canonical(payload: dict[str, Any]) -> bytes:
    return (json.dumps(payload, allow_nan=False, separators=(",", ":"), sort_keys=True) + "\n").encode()


def _pairs(values: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in values:
        if key in result:
            raise BootstrapError("bootstrap JSON contains duplicate keys")
        result[key] = value
    return result


def _sync_dir(path: Path) -> None:
    descriptor = os.open(
        path,
        os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0),
    )
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _directory(path: Path, mode: int, uid: int, gid: int, *, create: bool = False) -> None:
    if create:
        path.mkdir(parents=True, exist_ok=True, mode=mode)
        os.chmod(path, mode, follow_symlinks=False)
        os.chown(path, uid, gid, follow_symlinks=False)
    observed = path.lstat()
    if (
        not stat.S_ISDIR(observed.st_mode)
        or stat.S_ISLNK(observed.st_mode)
        or (observed.st_uid, observed.st_gid, stat.S_IMODE(observed.st_mode)) != (uid, gid, mode)
    ):
        raise BootstrapError("bootstrap directory is unsafe")


def _read(path: Path, uid: int, maximum: int, *, mode: int | None = None) -> bytes:
    before = path.lstat()
    if (
        not stat.S_ISREG(before.st_mode)
        or stat.S_ISLNK(before.st_mode)
        or before.st_uid != uid
        or before.st_nlink != 1
        or not 1 <= before.st_size <= maximum
        or (mode is None and stat.S_IMODE(before.st_mode) & 0o022)
        or (mode is not None and stat.S_IMODE(before.st_mode) != mode)
    ):
        raise BootstrapError("bootstrap file is unsafe")
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    try:
        opened = os.fstat(descriptor)
        chunks: list[bytes] = []
        consumed = 0
        while consumed < opened.st_size:
            chunk = os.read(descriptor, min(1024 * 1024, opened.st_size - consumed))
            if not chunk:
                raise BootstrapError("bootstrap file is truncated")
            chunks.append(chunk)
            consumed += len(chunk)
        after = os.fstat(descriptor)
    finally:
        os.close(descriptor)
    identity = ("st_dev", "st_ino", "st_size", "st_mtime_ns")
    if any(getattr(before, key) != getattr(opened, key) for key in identity) or any(
        getattr(opened, key) != getattr(after, key) for key in identity
    ):
        raise BootstrapError("bootstrap file changed while reading")
    return b"".join(chunks)


def _json(path: Path, uid: int, maximum: int, *, mode: int | None = None) -> tuple[dict[str, Any], bytes]:
    raw = _read(path, uid, maximum, mode=mode)
    try:
        payload = json.loads(raw.decode("utf-8", "strict"), object_pairs_hook=_pairs)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise BootstrapError("bootstrap JSON is invalid") from exc
    if not isinstance(payload, dict) or _canonical(payload) != raw:
        raise BootstrapError("bootstrap JSON is not canonical")
    return payload, raw


def _publish(path: Path, payload: bytes, uid: int, gid: int, mode: int) -> None:
    if path.exists() or path.is_symlink():
        if _read(path, uid, max(len(payload), 1), mode=mode) != payload:
            raise BootstrapError("bootstrap publication conflicts")
        return
    temporary = path.parent / f".{path.name}.writing"
    if temporary.exists() or temporary.is_symlink():
        temporary.unlink()
        _sync_dir(path.parent)
    descriptor = os.open(
        temporary,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
        mode,
    )
    try:
        os.fchmod(descriptor, mode)
        os.fchown(descriptor, uid, gid)
        view = memoryview(payload)
        while view:
            written = os.write(descriptor, view)
            if written < 1:
                raise BootstrapError("bootstrap write made no progress")
            view = view[written:]
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    _sync_dir(path.parent)
    os.replace(temporary, path)
    _sync_dir(path.parent)


def _digest(value: Any) -> str:
    text = str(value)
    if SHA256_RE.fullmatch(text) is None or text == "0" * 64:
        raise BootstrapError("bootstrap digest is invalid")
    return text


def _extract_bootstrap(control_raw: bytes, control: dict[str, Any], root: Path) -> None:
    if hashlib.sha256(control_raw).hexdigest() != _digest(control.get("archive_sha256")):
        raise BootstrapError("control archive digest differs from the manifest")
    captured: dict[str, bytes] = {}
    seen: set[str] = set()
    count = total = 0
    try:
        with tarfile.open(fileobj=io.BytesIO(control_raw), mode="r:") as bundle:
            for member in bundle:
                name = member.name
                parts = name.split("/")
                if (
                    not name
                    or name.startswith("/")
                    or "\\" in name
                    or any(part in {"", ".", ".."} for part in parts)
                    or str(PurePosixPath(name)) != name
                    or name in seen
                ):
                    raise BootstrapError("control archive path is unsafe")
                seen.add(name)
                if (
                    set(member.pax_headers) - {"path"}
                    or ("path" in member.pax_headers and member.pax_headers["path"] != name)
                    or (member.uid, member.gid, member.uname, member.gname, member.mtime) != (0, 0, "", "", 0)
                ):
                    raise BootstrapError("control archive metadata is invalid")
                if member.isdir():
                    if member.mode != 0o755 or member.size:
                        raise BootstrapError("control directory metadata is invalid")
                    continue
                if not member.isreg() or member.mode not in {0o644, 0o755} or member.size > 8 * 1024**2:
                    raise BootstrapError("control archive object is unsafe")
                source = bundle.extractfile(member)
                raw = source.read(member.size + 1) if source is not None else b""
                if len(raw) != member.size:
                    raise BootstrapError("control archive member is truncated")
                count += 1
                total += len(raw)
                if name in BOOTSTRAP_MODULES:
                    captured[name] = raw
    except tarfile.TarError as exc:
        raise BootstrapError("control archive is invalid") from exc
    if set(captured) != BOOTSTRAP_MODULES or count != control.get("file_count") or total != control.get("total_size"):
        raise BootstrapError("control archive evidence differs from the manifest")
    _directory(root, 0o700, 0, 0, create=True)
    _directory(root / "scripts", 0o755, 0, 0, create=True)
    _directory(root / "scripts/ha", 0o755, 0, 0, create=True)
    for relative, raw in captured.items():
        destination = root / relative
        _directory(destination.parent, 0o755, 0, 0, create=True)
        _publish(destination, raw, 0, 0, 0o600)


def _snapshot_source(source: Path, bundle: Path, source_uid: int) -> None:
    observed = source.lstat()
    if not stat.S_ISDIR(observed.st_mode) or stat.S_ISLNK(observed.st_mode) or observed.st_uid != source_uid:
        raise BootstrapError("downloaded release directory is unsafe")
    if {entry.name for entry in os.scandir(source)} != FILES:
        raise BootstrapError("downloaded release file set is not closed")
    _directory(bundle, 0o700, 0, 0, create=True)
    for name in sorted(FILES):
        maximum = (
            1024 * 1024 if name == "release-manifest.json" else (256 * 1024**2 if name == RUNTIME_NAME else 1024**3)
        )
        _publish(bundle / name, _read(source / name, source_uid, maximum), 0, 0, 0o600)


def _prepare(values: list[str]) -> int:
    if len(values) != 9:
        raise BootstrapError("prepare arguments are incomplete")
    source, trust, transfer = map(Path, values[:3])
    repository, run_id, attempt, target, manifest_sha = values[3:8]
    source_uid = int(values[8])
    if (
        not run_id.isdecimal()
        or not attempt.isdecimal()
        or min(int(run_id), int(attempt), source_uid) < 1
        or SHA_RE.fullmatch(target) is None
    ):
        raise BootstrapError("prepare identity is invalid")
    if trust != Path(f"/run/linas-python-runtime-qg-{run_id}-{attempt}"):
        raise BootstrapError("prepare trust root is not fixed")
    _directory(trust, 0o700, 0, 0, create=True)
    bundle, modules, control_root = trust / "release", trust / "bootstrap", trust / "control"
    _snapshot_source(source, bundle, source_uid)
    manifest, manifest_raw = _json(bundle / "release-manifest.json", 0, 1024 * 1024, mode=0o600)
    if hashlib.sha256(manifest_raw).hexdigest() != _digest(manifest_sha):
        raise BootstrapError("release manifest differs from dispatch authority")
    expected_workflow = f"{repository}/.github/workflows/quality-gates.yml@refs/heads/main"
    if (
        manifest.get("repository") != repository
        or manifest.get("workflow_ref") != expected_workflow
        or manifest.get("run_id") != int(run_id)
        or manifest.get("run_attempt") != int(attempt)
        or manifest.get("target_sha") != target
    ):
        raise BootstrapError("release manifest identity is wrong")
    payloads = manifest.get("payloads")
    control = payloads.get("control_plane") if isinstance(payloads, dict) else None
    if not isinstance(control, dict) or control.get("archive") != "control-plane.tar":
        raise BootstrapError("release control authority is invalid")
    control_raw = _read(bundle / "control-plane.tar", 0, 256 * 1024**2, mode=0o600)
    _extract_bootstrap(control_raw, control, modules)
    sys.path.insert(0, str(modules))
    from scripts.ha import release_artifact_contract as release

    release.verify_release_bundle(
        bundle,
        expected_repository=repository,
        expected_workflow_ref=expected_workflow,
        expected_run_id=int(run_id),
        expected_run_attempt=int(attempt),
        expected_target_sha=target,
    )
    release.extract_archive(
        bundle / "control-plane.tar",
        control_root,
        str(control["archive_sha256"]),
        str(control["tree_sha256"]),
        expected_paths=release.CONTROL_PLANE_MEMBERS,
    )
    _directory(transfer, 0o700, source_uid, os.getgid(), create=True)
    release_transfer, bootstrap_transfer = transfer / "release", transfer / "bootstrap"
    _directory(release_transfer, 0o700, source_uid, os.getgid(), create=True)
    _directory(bootstrap_transfer, 0o700, source_uid, os.getgid(), create=True)
    for name in sorted(FILES):
        raw = _read(bundle / name, 0, 1024**3, mode=0o600)
        _publish(release_transfer / name, raw, source_uid, os.getgid(), 0o600)
    result: dict[str, Any] = {
        "schema": 1,
        "bundle_root": str(bundle),
        "control_root": str(control_root),
    }
    for alias, relative in NODE_MODULES.items():
        raw = _read(control_root / relative, 0, 8 * 1024**2)
        _publish(bootstrap_transfer / alias, raw, source_uid, os.getgid(), 0o600)
        result[f"{alias.removesuffix('.py')}_sha256"] = hashlib.sha256(raw).hexdigest()
        result[f"{alias.removesuffix('.py')}_size"] = len(raw)
    print(json.dumps(result, separators=(",", ":"), sort_keys=True))
    return 0


def _invoke(command: list[str], *, input_bytes: bytes | None = None) -> str:
    result = subprocess.run(
        command,
        input=input_bytes,
        stdin=subprocess.DEVNULL if input_bytes is None else None,
        capture_output=True,
        check=False,
        timeout=3600,
        env=CHILD_ENV,
    )
    if result.returncode:
        raise BootstrapError(f"trusted child failed: {result.stderr.decode('utf-8', 'replace')[:400]}")
    return result.stdout.decode("utf-8", "strict")


def _launcher_authority(
    tx_id: str,
    *,
    expected_plan_sha256: str | None = None,
    expected_artifact_id: int | None = None,
    expected_artifact_api_sha256: str | None = None,
    expected_target_sha: str | None = None,
) -> tuple[Path, Path, str]:
    if TX_RE.fullmatch(tx_id) is None:
        raise BootstrapError("launcher transaction authority is invalid")
    tx_root = STATE_ROOT / "python-runtime-transactions" / tx_id
    for directory in (
        STATE_ROOT,
        STATE_ROOT / "python-runtime-transactions",
        tx_root,
        tx_root / "authority",
        STATE_ROOT / "python-runtime-provision-launchers",
        STATE_ROOT / "python-runtime-provision-control",
    ):
        _directory(directory, 0o700, 0, 0)
    plan, plan_raw = _json(tx_root / "authority/plan.json", 0, 1024 * 1024, mode=0o600)
    plan_sha256 = hashlib.sha256(plan_raw).hexdigest()
    if plan.get("transaction_id") != tx_id:
        raise BootstrapError("launcher plan transaction binding is invalid")
    if expected_plan_sha256 is not None and _digest(expected_plan_sha256) != plan_sha256:
        raise BootstrapError("launcher plan differs from workflow authority")
    artifact_id, api_sha = plan.get("qg_artifact_id"), str(plan.get("qg_artifact_api_sha256"))
    if type(artifact_id) is not int or artifact_id < 1 or _digest(api_sha) != api_sha:
        raise BootstrapError("launcher plan QG authority is invalid")
    if expected_artifact_id is not None and artifact_id != expected_artifact_id:
        raise BootstrapError("launcher artifact ID differs from workflow authority")
    if expected_artifact_api_sha256 is not None and _digest(expected_artifact_api_sha256) != api_sha:
        raise BootstrapError("launcher artifact digest differs from workflow authority")
    if expected_target_sha is not None and (
        SHA_RE.fullmatch(expected_target_sha) is None or plan.get("qg_target_sha") != expected_target_sha
    ):
        raise BootstrapError("launcher target differs from workflow authority")
    receipt_path = STATE_ROOT / "python-runtime-provision-launchers" / f"{artifact_id}-{api_sha}.json"
    receipt, _raw = _json(receipt_path, 0, 1024 * 1024, mode=0o600)
    # fmt: off
    expected_keys = {
        "schema", "format", "artifact_id", "artifact_api_sha256", "manifest_sha256", "run_id", "run_attempt",
        "target_sha", "bundle_root", "control_root", "control_plane_archive_sha256", "control_plane_tree_sha256",
        "launcher_path", "launcher_sha256", "launcher_size",
    }
    # fmt: on
    if (
        set(receipt) != expected_keys
        or receipt.get("schema") != 1
        or receipt.get("format") != "linas-python-runtime-launcher-v1"
        or receipt.get("artifact_id") != artifact_id
        or receipt.get("artifact_api_sha256") != api_sha
        or receipt.get("manifest_sha256") != plan.get("qg_manifest_sha256")
        or receipt.get("run_id") != plan.get("qg_run_id")
        or receipt.get("run_attempt") != plan.get("qg_run_attempt")
        or receipt.get("target_sha") != plan.get("qg_target_sha")
        or receipt.get("control_plane_archive_sha256") != plan.get("control_plane_archive_sha256")
        or receipt.get("control_plane_tree_sha256") != plan.get("control_plane_tree_sha256")
    ):
        raise BootstrapError("launcher receipt differs from the transaction")
    key = f"{artifact_id}-{api_sha}"
    expected_bundle = STATE_ROOT / "release-bundles" / key
    expected_control = STATE_ROOT / "python-runtime-provision-control" / key
    _directory(expected_control, 0o700, 0, 0)
    launcher = Path(str(receipt["launcher_path"]))
    if (
        receipt.get("bundle_root") != str(expected_bundle)
        or receipt.get("control_root") != str(expected_control)
        or launcher != expected_control / NODE_MODULES["launcher.py"]
    ):
        raise BootstrapError("launcher receipt paths are invalid")
    launcher_raw = _read(launcher, 0, 8 * 1024**2)
    if len(launcher_raw) != receipt.get("launcher_size") or hashlib.sha256(launcher_raw).hexdigest() != _digest(
        receipt.get("launcher_sha256")
    ):
        raise BootstrapError("launcher differs from its receipt")
    return tx_root, launcher, plan_sha256


def _initial(values: list[str]) -> int:
    if len(values) != 18:
        raise BootstrapError("initial invocation arguments are invalid")
    upload, workflow_run, workflow_attempt = Path(values[0]), values[1], values[2]
    source_uid, artifact_id = int(values[3]), int(values[4])
    api_sha, manifest_sha, qg_run, qg_attempt, target = values[5:10]
    plan_sha, confirmation = values[10:12]
    hashes = values[12:]
    if (
        any(not value.isdecimal() or int(value) < 1 for value in (workflow_run, workflow_attempt, qg_run, qg_attempt))
        or source_uid < 0
        or artifact_id < 1
        or _digest(api_sha) != api_sha
        or _digest(manifest_sha) != manifest_sha
        or _digest(plan_sha) != plan_sha
        or SHA_RE.fullmatch(target) is None
    ):
        raise BootstrapError("initial QG authority is invalid")
    if upload != Path(f"/tmp/linasbot-python-runtime-upload-{workflow_run}-{workflow_attempt}"):
        raise BootstrapError("initial upload root is not fixed")
    bootstrap = upload / "bootstrap"
    trusted = Path(f"/run/linas-python-runtime-bootstrap-{workflow_run}-{workflow_attempt}")
    module_root = trusted / "modules"
    _directory(trusted, 0o700, 0, 0, create=True)
    _directory(module_root, 0o700, 0, 0, create=True)
    _directory(module_root / "scripts", 0o755, 0, 0, create=True)
    _directory(module_root / "scripts/ha", 0o755, 0, 0, create=True)
    expected = dict(zip(NODE_MODULES, zip(hashes[::2], map(int, hashes[1::2]), strict=True), strict=True))
    for alias, (digest, size) in expected.items():
        raw = _read(bootstrap / alias, source_uid, 8 * 1024**2)
        if hashlib.sha256(raw).hexdigest() != _digest(digest) or len(raw) != size:
            raise BootstrapError("initial bootstrap module differs from workflow authority")
        if alias == "launcher.py":
            destination = trusted / alias
        else:
            relative = NODE_MODULES[alias]
            destination = module_root / relative
            _directory(destination.parent, 0o755, 0, 0, create=True)
        _publish(destination, raw, 0, 0, 0o600)
    # fmt: off
    ingest = _invoke([
        OS_PYTHON, "-B", "-I", "-S", str(trusted / "launcher.py"), "ingest", str(module_root),
        expected["ingest.py"][0], str(expected["ingest.py"][1]),
        expected["ingest_contract.py"][0], str(expected["ingest_contract.py"][1]),
        str(upload / "release"), str(source_uid), str(artifact_id), api_sha, manifest_sha, qg_run, qg_attempt, target,
    ])
    # fmt: on
    try:
        installed = json.loads(ingest)
    except json.JSONDecodeError as exc:
        raise BootstrapError("ingest acknowledgement is invalid") from exc
    key = f"{artifact_id}-{api_sha}"
    bundle = STATE_ROOT / "release-bundles" / key
    control = STATE_ROOT / "python-runtime-provision-control" / key
    if installed != {"schema": 1, "bundle_root": str(bundle), "control_root": str(control)}:
        raise BootstrapError("ingest acknowledgement path binding is invalid")
    output = _invoke(
        [
            OS_PYTHON,
            "-B",
            "-I",
            "-S",
            str(control / NODE_MODULES["launcher.py"]),
            "run-bundle",
            str(bundle),
            str(control),
            manifest_sha,
            "apply",
            str(artifact_id),
            api_sha,
            manifest_sha,
            qg_run,
            qg_attempt,
            target,
            plan_sha,
            confirmation,
        ]
    )
    print(output, end="")
    return 0


def _resume(values: list[str]) -> int:
    if len(values) not in {2, 4} or values[0] not in {"status", "recover", "rollback"}:
        raise BootstrapError("resume arguments are invalid")
    operation, tx_id = values[:2]
    if TX_RE.fullmatch(tx_id) is None or (operation == "status") != (len(values) == 2):
        raise BootstrapError("resume transaction authority is invalid")
    if operation != "status":
        _digest(values[2])
    tx_root, launcher, plan_sha256 = _launcher_authority(tx_id)
    arguments = [operation, tx_id] if operation == "status" else values
    output = _invoke(
        [
            OS_PYTHON,
            "-B",
            "-I",
            "-S",
            str(launcher),
            "run-transaction",
            str(tx_root),
            str(tx_root / "control"),
            plan_sha256,
            *arguments,
        ]
    )
    print(output, end="")
    return 0


def _bootstrap(values: list[str]) -> int:
    if len(values) < 6:
        raise BootstrapError("bootstrap dispatch arguments are incomplete")
    tx_id, plan_sha256, artifact_id_raw, api_sha, target_sha, operation = values[:6]
    if not artifact_id_raw.isdecimal() or int(artifact_id_raw) < 1:
        raise BootstrapError("bootstrap dispatch artifact ID is invalid")
    allowed = {
        "cluster-probe",
        "install-lb-ready-attestation",
        "plan",
        "apply",
        "recover-rollback",
        "recovery-status",
        "recover-decided",
    }
    if operation not in allowed:
        raise BootstrapError("bootstrap dispatch operation is outside the closed contract")
    tx_root, launcher, verified_plan_sha256 = _launcher_authority(
        tx_id,
        expected_plan_sha256=plan_sha256,
        expected_artifact_id=int(artifact_id_raw),
        expected_artifact_api_sha256=api_sha,
        expected_target_sha=target_sha,
    )
    input_bytes: bytes | None = None
    if operation == "install-lb-ready-attestation":
        input_bytes = sys.stdin.buffer.read(131_073)
        if not 1 <= len(input_bytes) <= 131_072 or sys.stdin.buffer.read(1):
            raise BootstrapError("bootstrap LB attestation input is invalid")
    output = _invoke(
        [
            OS_PYTHON,
            "-B",
            "-I",
            "-S",
            str(launcher),
            "run-bootstrap",
            str(tx_root),
            str(tx_root / "control"),
            verified_plan_sha256,
            operation,
            *values[6:],
        ],
        input_bytes=input_bytes,
    )
    print(output, end="")
    return 0


def main(argv: list[str] | None = None) -> int:
    values = sys.argv[1:] if argv is None else argv
    if os.geteuid() != 0 or not (sys.flags.isolated and sys.flags.no_site and sys.flags.dont_write_bytecode):
        raise BootstrapError("workflow bootstrap requires root OS Python with -B -I -S")
    if re.fullmatch(r"/usr/bin/python3(?:\.[0-9]{1,2})?", str(Path(sys.executable).resolve())) is None:
        raise BootstrapError("workflow bootstrap is not running under the OS Python")
    if any(name.startswith("PYTHON") for name in os.environ):
        raise BootstrapError("workflow bootstrap forbids ambient Python controls")
    if not values:
        raise BootstrapError("workflow bootstrap operation is missing")
    operation, arguments = values[0], values[1:]
    if operation == "prepare":
        return _prepare(arguments)
    if operation == "initial":
        return _initial(arguments)
    if operation == "resume":
        return _resume(arguments)
    if operation == "bootstrap":
        return _bootstrap(arguments)
    raise BootstrapError("workflow bootstrap operation is invalid")


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (BootstrapError, OSError, ValueError) as exc:
        print(f"[python-runtime-workflow-bootstrap] ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
