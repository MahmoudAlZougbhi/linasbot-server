#!/usr/bin/env python3
"""Closed QG authority, plan, and receipt schemas for CPython HA provisioning."""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final, cast

from scripts.ha import release_artifact_contract as release
from scripts.ha.python_runtime_archive_contract import ProvisionError

EXPECTED_REPOSITORY: Final = "MahmoudAlZougbhi/linasbot-server"
EXPECTED_WORKFLOW_REF: Final = "MahmoudAlZougbhi/linasbot-server/.github/workflows/quality-gates.yml@refs/heads/main"
PLAN_FORMAT: Final = "linas-python-runtime-plan-v1"
NODE_RECEIPT_FORMAT: Final = "linas-python-runtime-node-v2"
CLUSTER_RECEIPT_FORMAT: Final = "linas-python-runtime-cluster-v2"
CPYTHON_SOURCE_SHA256: Final = "1e66a7945a48390ee4c2a4268a0e4185884059a13c4aab6d148aa208deea4a76"
RUNTIME_PATH: Final = Path("/opt/linasbot-runtime/cpython-3.13.15")
STATE_ROOT: Final = Path("/var/lib/linasbot/meta-ha")
NODES: Final = ("node01", "node02")
SHA256_RE: Final = re.compile(r"[0-9a-f]{64}")
SHA_RE: Final = re.compile(r"[0-9a-f]{40}")
TX_RE: Final = re.compile(r"pyr_[0-9a-f]{32}")
EXPECTED_UID = 0
EXPECTED_GID = 0

PLAN_KEYS: Final = {
    "schema",
    "format",
    "transaction_id",
    "required_nodes",
    "runtime_path",
    "artifact_name",
    "artifact_sha256",
    "runtime_tree_sha256",
    "python_executable_sha256",
    "libpython_sha256",
    "control_plane_archive_sha256",
    "control_plane_tree_sha256",
    "wheelhouse_archive_sha256",
    "wheelhouse_tree_sha256",
    "wheelhouse_file_count",
    "wheelhouse_total_size",
    "runtime_archive_size",
    "qg_repository",
    "qg_workflow_ref",
    "qg_run_id",
    "qg_run_attempt",
    "qg_target_sha",
    "qg_artifact_id",
    "qg_artifact_api_sha256",
    "qg_manifest_sha256",
}
PROVENANCE_KEYS: Final = {
    "qg_repository",
    "qg_workflow_ref",
    "qg_run_id",
    "qg_run_attempt",
    "qg_target_sha",
    "qg_artifact_id",
    "qg_artifact_api_sha256",
    "qg_manifest_sha256",
}
COMMON_RECEIPT_KEYS: Final = {
    "schema",
    "format",
    "transaction_id",
    "decision",
    "status",
    "required_nodes",
    "runtime_path",
    "python_executable",
    "python_version",
    "implementation",
    "cache_tag",
    "soabi",
    "platform_system",
    "machine",
    "pip_version",
    "artifact_repository",
    "artifact_release",
    "artifact_name",
    "artifact_sha256",
    "cpython_source_sha256",
    "runtime_tree_sha256",
    "wheelhouse_archive_sha256",
    "wheelhouse_tree_sha256",
    "wheelhouse_file_count",
    "wheelhouse_total_size",
    "plan_sha256",
    *PROVENANCE_KEYS,
}


@dataclass(frozen=True)
class Authority:
    artifact_id: int
    artifact_api_sha256: str
    manifest_sha256: str
    run_id: int
    run_attempt: int
    target_sha: str

    @classmethod
    def build(
        cls,
        artifact_id: int | str,
        artifact_api_sha256: str,
        manifest_sha256: str,
        run_id: int | str,
        run_attempt: int | str,
        target_sha: str,
    ) -> Authority:
        raw_numbers = (artifact_id, run_id, run_attempt)
        try:
            numbers = tuple(int(value) for value in raw_numbers)
        except (TypeError, ValueError) as exc:
            raise ProvisionError("QG numeric authority is invalid") from exc
        if any(value < 1 or str(value) != str(raw) for value, raw in zip(numbers, raw_numbers, strict=True)):
            raise ProvisionError("QG numeric authority is not strict decimal")
        for value in (artifact_api_sha256, manifest_sha256):
            if SHA256_RE.fullmatch(value) is None or value == "0" * 64:
                raise ProvisionError("QG digest authority is invalid")
        if SHA_RE.fullmatch(target_sha) is None or target_sha == "0" * 40:
            raise ProvisionError("QG target SHA is invalid")
        return cls(numbers[0], artifact_api_sha256, manifest_sha256, numbers[1], numbers[2], target_sha)

    def bundle_path(self, state_root: Path = STATE_ROOT) -> Path:
        return state_root / "release-bundles" / f"{self.artifact_id}-{self.artifact_api_sha256}"


def canonical(payload: Mapping[str, Any]) -> bytes:
    try:
        return (
            json.dumps(payload, allow_nan=False, ensure_ascii=False, separators=(",", ":"), sort_keys=True) + "\n"
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeError) as exc:
        raise ProvisionError("runtime metadata is not canonicalizable") from exc


def digest_json(payload: Mapping[str, Any]) -> str:
    return hashlib.sha256(canonical(payload)).hexdigest()


def _exact(payload: Any, keys: set[str], label: str) -> dict[str, Any]:
    if not isinstance(payload, dict) or set(payload) != keys:
        raise ProvisionError(f"{label} schema is not closed")
    return payload


def _secure_bundle_files(bundle: Path) -> None:
    info = bundle.lstat()
    if (
        not stat.S_ISDIR(info.st_mode)
        or stat.S_ISLNK(info.st_mode)
        or info.st_uid != EXPECTED_UID
        or info.st_gid != EXPECTED_GID
        or stat.S_IMODE(info.st_mode) != 0o700
    ):
        raise ProvisionError("release bundle directory is unsafe")
    entries = list(os.scandir(bundle))
    if {entry.name for entry in entries} != release.FINAL_FILES:
        raise ProvisionError("release bundle file set is not closed")
    for entry in entries:
        observed = entry.stat(follow_symlinks=False)
        if (
            not stat.S_ISREG(observed.st_mode)
            or stat.S_ISLNK(observed.st_mode)
            or observed.st_uid != EXPECTED_UID
            or observed.st_gid != EXPECTED_GID
            or stat.S_IMODE(observed.st_mode) != 0o600
            or observed.st_nlink != 1
        ):
            raise ProvisionError("release bundle contains an unsafe file")


def verify_release_bundle(bundle: Path, authority: Authority, *, enforce_path: bool = True) -> dict[str, Any]:
    if enforce_path and bundle != authority.bundle_path():
        raise ProvisionError("release bundle is outside its artifact-derived root")
    _secure_bundle_files(bundle)
    manifest_sha, _size = release.file_evidence(bundle / "release-manifest.json", max_bytes=1024 * 1024)
    if manifest_sha != authority.manifest_sha256:
        raise ProvisionError("release manifest differs from workflow authority")
    try:
        return cast(
            dict[str, Any],
            release.verify_release_bundle(
                bundle,
                expected_repository=EXPECTED_REPOSITORY,
                expected_workflow_ref=EXPECTED_WORKFLOW_REF,
                expected_run_id=authority.run_id,
                expected_run_attempt=authority.run_attempt,
                expected_target_sha=authority.target_sha,
            ),
        )
    except release.ContractError as exc:
        raise ProvisionError("closed QG release bundle validation failed") from exc


def build_plan(authority: Authority, bundle: Path, *, enforce_path: bool = True) -> tuple[dict[str, Any], str]:
    manifest = verify_release_bundle(bundle, authority, enforce_path=enforce_path)
    plan: dict[str, Any] = {
        "schema": 1,
        "format": PLAN_FORMAT,
        "transaction_id": "",
        "required_nodes": list(NODES),
        "runtime_path": str(RUNTIME_PATH),
        "artifact_name": release.PYTHON_RUNTIME_NAME,
        "artifact_sha256": release.PYTHON_RUNTIME_SHA256,
        "runtime_tree_sha256": release.PYTHON_RUNTIME_TREE_SHA256,
        "python_executable_sha256": release.PYTHON_EXECUTABLE_SHA256,
        "libpython_sha256": release.PYTHON_LIBPYTHON_SHA256,
        "control_plane_archive_sha256": manifest["payloads"]["control_plane"]["archive_sha256"],
        "control_plane_tree_sha256": manifest["payloads"]["control_plane"]["tree_sha256"],
        "wheelhouse_archive_sha256": manifest["payloads"]["wheelhouse"]["archive_sha256"],
        "wheelhouse_tree_sha256": manifest["payloads"]["wheelhouse"]["tree_sha256"],
        "wheelhouse_file_count": manifest["payloads"]["wheelhouse"]["file_count"],
        "wheelhouse_total_size": manifest["payloads"]["wheelhouse"]["total_size"],
        "runtime_archive_size": manifest["payloads"]["python_runtime"]["size"],
        "qg_repository": EXPECTED_REPOSITORY,
        "qg_workflow_ref": EXPECTED_WORKFLOW_REF,
        "qg_run_id": authority.run_id,
        "qg_run_attempt": authority.run_attempt,
        "qg_target_sha": authority.target_sha,
        "qg_artifact_id": authority.artifact_id,
        "qg_artifact_api_sha256": authority.artifact_api_sha256,
        "qg_manifest_sha256": authority.manifest_sha256,
    }
    seed = digest_json(plan)
    plan["transaction_id"] = f"pyr_{seed[:32]}"
    return plan, digest_json(plan)


def validate_plan(plan: Mapping[str, Any], expected_sha256: str | None = None) -> dict[str, Any]:
    payload = _exact(plan, PLAN_KEYS, "runtime plan")
    fixed = {
        "schema": 1,
        "format": PLAN_FORMAT,
        "required_nodes": list(NODES),
        "runtime_path": str(RUNTIME_PATH),
        "artifact_name": release.PYTHON_RUNTIME_NAME,
        "artifact_sha256": release.PYTHON_RUNTIME_SHA256,
        "runtime_tree_sha256": release.PYTHON_RUNTIME_TREE_SHA256,
        "python_executable_sha256": release.PYTHON_EXECUTABLE_SHA256,
        "libpython_sha256": release.PYTHON_LIBPYTHON_SHA256,
        "qg_repository": EXPECTED_REPOSITORY,
        "qg_workflow_ref": EXPECTED_WORKFLOW_REF,
    }
    if any(payload.get(key) != value for key, value in fixed.items()):
        raise ProvisionError("runtime plan differs from the reviewed contract")
    transaction_id = str(payload.get("transaction_id"))
    seed_payload = dict(payload)
    seed_payload["transaction_id"] = ""
    expected_transaction_id = f"pyr_{digest_json(seed_payload)[:32]}"
    if TX_RE.fullmatch(transaction_id) is None or transaction_id != expected_transaction_id:
        raise ProvisionError("runtime transaction ID is invalid")
    for key in (
        "control_plane_archive_sha256",
        "control_plane_tree_sha256",
        "wheelhouse_archive_sha256",
        "wheelhouse_tree_sha256",
    ):
        if SHA256_RE.fullmatch(str(payload.get(key))) is None or payload[key] == "0" * 64:
            raise ProvisionError("runtime plan control-plane digest is invalid")
    if (
        type(payload.get("runtime_archive_size")) is not int
        or not 1 <= payload["runtime_archive_size"] <= 256 * 1024**2
    ):
        raise ProvisionError("runtime plan archive size is invalid")
    if (
        type(payload.get("wheelhouse_file_count")) is not int
        or not 1 <= payload["wheelhouse_file_count"] <= 100_000
        or type(payload.get("wheelhouse_total_size")) is not int
        or not 1 <= payload["wheelhouse_total_size"] <= 4 * 1024**3
    ):
        raise ProvisionError("runtime plan wheelhouse evidence is invalid")
    if any(
        type(payload.get(key)) is not int or payload[key] < 1
        for key in ("qg_run_id", "qg_run_attempt", "qg_artifact_id")
    ):
        raise ProvisionError("runtime plan numeric authority is invalid")
    if SHA_RE.fullmatch(str(payload.get("qg_target_sha"))) is None or payload["qg_target_sha"] == "0" * 40:
        raise ProvisionError("runtime plan target is invalid")
    for key in ("qg_artifact_api_sha256", "qg_manifest_sha256"):
        if SHA256_RE.fullmatch(str(payload.get(key))) is None or payload[key] == "0" * 64:
            raise ProvisionError("runtime plan QG digest is invalid")
    actual = digest_json(payload)
    if expected_sha256 is not None and actual != expected_sha256:
        raise ProvisionError("runtime plan digest differs from owner authority")
    return payload


def authority_from_plan(plan: Mapping[str, Any]) -> Authority:
    validate_plan(plan)
    return Authority.build(
        plan["qg_artifact_id"],
        str(plan["qg_artifact_api_sha256"]),
        str(plan["qg_manifest_sha256"]),
        plan["qg_run_id"],
        plan["qg_run_attempt"],
        str(plan["qg_target_sha"]),
    )


def _receipt_common(plan: Mapping[str, Any], plan_sha256: str, receipt_format: str) -> dict[str, Any]:
    validate_plan(plan, plan_sha256)
    return {
        "schema": 2,
        "format": receipt_format,
        "transaction_id": plan["transaction_id"],
        "decision": "commit",
        "status": "committed",
        "required_nodes": list(NODES),
        "runtime_path": str(RUNTIME_PATH),
        "python_executable": str(RUNTIME_PATH / "bin/python3.13"),
        "python_version": release.PYTHON_VERSION,
        "implementation": "cpython",
        "cache_tag": release.PYTHON_CACHE_TAG,
        "soabi": "cpython-313-x86_64-linux-gnu",
        "platform_system": "Linux",
        "machine": release.PYTHON_MACHINE,
        "pip_version": release.PIP_VERSION,
        "artifact_repository": "astral-sh/python-build-standalone",
        "artifact_release": "20260814",
        "artifact_name": release.PYTHON_RUNTIME_NAME,
        "artifact_sha256": release.PYTHON_RUNTIME_SHA256,
        "cpython_source_sha256": CPYTHON_SOURCE_SHA256,
        "runtime_tree_sha256": release.PYTHON_RUNTIME_TREE_SHA256,
        "wheelhouse_archive_sha256": plan["wheelhouse_archive_sha256"],
        "wheelhouse_tree_sha256": plan["wheelhouse_tree_sha256"],
        "wheelhouse_file_count": plan["wheelhouse_file_count"],
        "wheelhouse_total_size": plan["wheelhouse_total_size"],
        "plan_sha256": plan_sha256,
        **{key: plan[key] for key in PROVENANCE_KEYS},
    }


def node_receipt(plan: Mapping[str, Any], plan_sha256: str, node_id: str) -> dict[str, Any]:
    if node_id not in NODES:
        raise ProvisionError("runtime receipt node identity is invalid")
    return {
        **_receipt_common(plan, plan_sha256, NODE_RECEIPT_FORMAT),
        "node_id": node_id,
        "python_executable_sha256": release.PYTHON_EXECUTABLE_SHA256,
    }


def cluster_receipt(
    plan: Mapping[str, Any], plan_sha256: str, node_receipt_sha256: Mapping[str, str]
) -> dict[str, Any]:
    if set(node_receipt_sha256) != set(NODES) or any(
        SHA256_RE.fullmatch(str(value)) is None for value in node_receipt_sha256.values()
    ):
        raise ProvisionError("cluster node receipt map is invalid")
    return {
        **_receipt_common(plan, plan_sha256, CLUSTER_RECEIPT_FORMAT),
        "node_receipt_sha256": {node: node_receipt_sha256[node] for node in NODES},
    }


def validate_node_receipt(payload: Mapping[str, Any], plan: Mapping[str, Any], plan_sha256: str) -> dict[str, Any]:
    receipt = _exact(payload, COMMON_RECEIPT_KEYS | {"node_id", "python_executable_sha256"}, "node receipt")
    expected = node_receipt(plan, plan_sha256, str(receipt.get("node_id")))
    if receipt != expected:
        raise ProvisionError("node receipt differs from the committed plan")
    return receipt


def validate_cluster_receipt(payload: Mapping[str, Any], plan: Mapping[str, Any], plan_sha256: str) -> dict[str, Any]:
    receipt = _exact(payload, COMMON_RECEIPT_KEYS | {"node_receipt_sha256"}, "cluster receipt")
    expected = cluster_receipt(plan, plan_sha256, receipt["node_receipt_sha256"])
    if receipt != expected:
        raise ProvisionError("cluster receipt differs from the committed plan")
    return receipt
