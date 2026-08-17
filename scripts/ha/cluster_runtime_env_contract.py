#!/usr/bin/env python3
"""Secret-safe parity proof for the complete two-node runtime environment."""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import re
import stat
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.ha.production_mutation_guard import (  # noqa: E402
    ENV_KEY_RE,
    FORBIDDEN_EXECUTION_ENV_KEYS,
    FORBIDDEN_EXECUTION_ENV_PREFIXES,
)

FORMAT = "linas-cluster-runtime-env-v1"
SHA_RE = re.compile(r"[0-9a-f]{40}")
NODE_LOCAL_VALUES = {
    "node01": {
        "LINAS_HA_PEER_HOST": "10.106.0.4",
        "META_DELETION_NODE_ID": "node01",
    },
    "node02": {
        "LINAS_HA_PEER_HOST": "10.106.0.3",
        "META_DELETION_NODE_ID": "node02",
    },
}
NODE_LOCAL_KEYS = frozenset(next(iter(NODE_LOCAL_VALUES.values())))
WORKER_QUEUES = frozenset({"high_priority", "interactive", "background", "expensive"})
FIXED_RUNTIME_VALUES = {
    "PYTHONUNBUFFERED": "1",
    "PYTHONDONTWRITEBYTECODE": "1",
    "PATH": "/opt/linasbot/venv/bin:/usr/local/bin:/usr/bin:/bin",
}
FIXED_ROOT_PROCESS_VALUES = {
    "HOME": "/root",
    "USER": "root",
    "LOGNAME": "root",
    "LANG": "C.UTF-8",
    "LC_ALL": "C.UTF-8",
    "PWD": "/opt/linasbot",
}
ALLOWED_ROOT_SHELLS = frozenset(
    {
        "/bin/bash",
        "/bin/sh",
        "/bin/dash",
        "/usr/bin/bash",
        "/usr/bin/sh",
        "/usr/bin/dash",
        "/usr/sbin/nologin",
        "/sbin/nologin",
    }
)
SYSTEMD_EPHEMERAL_KEYS = frozenset(
    {
        "INVOCATION_ID",
        "JOURNAL_STREAM",
        "SYSTEMD_EXEC_PID",
        "MEMORY_PRESSURE_WATCH",
        "MEMORY_PRESSURE_WRITE",
        "NOTIFY_SOCKET",
        "WATCHDOG_PID",
        "WATCHDOG_USEC",
    }
)


def _canonical(payload: object) -> bytes:
    return json.dumps(payload, allow_nan=False, separators=(",", ":"), sort_keys=True).encode("utf-8")


def _read_secure(path: Path, *, owner_uid: int = 0, owner_gid: int = 0) -> bytes:
    before = path.lstat()
    if (
        not stat.S_ISREG(before.st_mode)
        or stat.S_ISLNK(before.st_mode)
        or before.st_uid != owner_uid
        or before.st_gid != owner_gid
        or stat.S_IMODE(before.st_mode) != 0o600
    ):
        raise RuntimeError("Canonical runtime environment security contract is invalid")
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    try:
        opened = os.fstat(descriptor)
        if (before.st_dev, before.st_ino) != (opened.st_dev, opened.st_ino):
            raise RuntimeError("Canonical runtime environment changed while opening")
        chunks: list[bytes] = []
        while True:
            chunk = os.read(descriptor, 65536)
            if not chunk:
                break
            chunks.append(chunk)
        return b"".join(chunks)
    finally:
        os.close(descriptor)


def _validate_values(values: dict[str, str], *, node_id: str) -> dict[str, str]:
    if node_id not in NODE_LOCAL_VALUES:
        raise RuntimeError("Cluster runtime node identity is invalid")
    if not values:
        raise RuntimeError("Canonical runtime environment is empty")
    for key, value in values.items():
        if ENV_KEY_RE.fullmatch(key) is None or any(character in value for character in ("\0", "\r", "\n")):
            raise RuntimeError("Canonical runtime environment contains an invalid entry")
        if key in FORBIDDEN_EXECUTION_ENV_KEYS or key.startswith(FORBIDDEN_EXECUTION_ENV_PREFIXES):
            raise RuntimeError("Canonical runtime environment contains an execution-control key")
        if key.startswith("PYTHON") and key not in FIXED_RUNTIME_VALUES:
            raise RuntimeError("Canonical runtime environment contains a Python semantic-control key")
    expected_local = NODE_LOCAL_VALUES[node_id]
    if any(values.get(key) != value for key, value in expected_local.items()):
        raise RuntimeError("Canonical runtime environment has invalid node-local identity")
    return {key: value for key, value in values.items() if key not in NODE_LOCAL_KEYS}


def load_projection(
    path: Path,
    *,
    node_id: str,
    owner_uid: int = 0,
    owner_gid: int = 0,
) -> dict[str, str]:
    payload = _read_secure(path, owner_uid=owner_uid, owner_gid=owner_gid)
    try:
        text = payload.decode("utf-8", "strict")
    except UnicodeDecodeError as exc:
        raise RuntimeError("Canonical runtime environment is not UTF-8") from exc
    seen: set[str] = set()
    for raw_line in text.splitlines():
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        raw_key = raw_line.split("=", 1)[0].strip() if "=" in raw_line else ""
        if ENV_KEY_RE.fullmatch(raw_key) is None or raw_key in seen:
            raise RuntimeError("Canonical runtime environment is ambiguous")
        seen.add(raw_key)
    values: dict[str, str] = {}
    for raw_line in text.splitlines():
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        raw_key, separator, raw_value = raw_line.partition("=")
        if not separator:
            raise RuntimeError("Canonical runtime environment is ambiguous")
        key = raw_key.strip()
        value_text = raw_value.strip()
        if value_text[:1] in {"'", '"'}:
            if len(value_text) < 2 or value_text[-1] != value_text[0]:
                raise RuntimeError("Canonical runtime environment quoting is invalid")
            try:
                parsed_value = ast.literal_eval(value_text)
            except (SyntaxError, ValueError) as exc:
                raise RuntimeError("Canonical runtime environment quoting is invalid") from exc
            if not isinstance(parsed_value, str):
                raise RuntimeError("Canonical runtime environment value is not text")
            value = parsed_value
        else:
            value = value_text
        values[key] = value
    if set(values) != seen:
        raise RuntimeError("Canonical runtime environment parse contract is ambiguous")
    return _validate_values(values, node_id=node_id)


def projection_evidence(projection: dict[str, str], *, node_id: str, expected_sha: str) -> dict[str, object]:
    if SHA_RE.fullmatch(expected_sha) is None or node_id not in NODE_LOCAL_VALUES:
        raise RuntimeError("Cluster runtime evidence binding is invalid")
    names = sorted(projection)
    projection_payload = {
        "expected_release_sha": expected_sha,
        "values": projection,
    }
    return {
        "format": FORMAT,
        "node_id": node_id,
        "expected_release_sha": expected_sha,
        "projection_sha256": hashlib.sha256(_canonical(projection_payload)).hexdigest(),
        "keyset_sha256": hashlib.sha256(_canonical(names)).hexdigest(),
        "key_count": len(names),
        "node_local_schema_sha256": hashlib.sha256(_canonical(sorted(NODE_LOCAL_KEYS))).hexdigest(),
    }


def verify_process_environment(
    projection: dict[str, str],
    process_environ: Path,
    *,
    node_id: str,
    transient_release_sha: str | None = None,
) -> None:
    payload = process_environ.read_bytes()
    actual: dict[str, str] = {}
    for entry in payload.split(b"\0"):
        if not entry:
            continue
        if b"=" not in entry:
            raise RuntimeError("Runtime process environment is malformed")
        raw_key, raw_value = entry.split(b"=", 1)
        key = raw_key.decode("utf-8", "strict")
        value = raw_value.decode("utf-8", "strict")
        if key in actual:
            raise RuntimeError("Runtime process environment contains a duplicate key")
        actual[key] = value
    # Canonical .env validation is insufficient: a unit/drop-in can inject a
    # loader control directly into the live process. PATH is the one forbidden
    # canonical key intentionally supplied by the reviewed systemd unit and is
    # verified against its fixed value by the projection caller.
    forbidden_live_keys = FORBIDDEN_EXECUTION_ENV_KEYS - {"PATH"}
    if any(key in forbidden_live_keys or key.startswith(FORBIDDEN_EXECUTION_ENV_PREFIXES) for key in actual):
        raise RuntimeError("Runtime process environment contains an execution-control key")
    if any(key.startswith("PYTHON") and key not in FIXED_RUNTIME_VALUES for key in actual):
        raise RuntimeError("Runtime process environment contains a Python semantic-control key")
    expected = {**projection, **NODE_LOCAL_VALUES[node_id], **FIXED_RUNTIME_VALUES}
    if transient_release_sha is not None:
        expected.update(
            {
                "LINAS_HA_VERIFY_ONLY": "true",
                "LINAS_HA_VERIFY_RELEASE_SHA": transient_release_sha,
                "DISABLE_API_DOCS": "1",
            }
        )
    if any(actual.get(key) != value for key, value in expected.items()):
        raise RuntimeError("Runtime process environment is stale or divergent")
    unexpected = set(actual) - set(expected)
    extra_names: list[str] = []
    for key in unexpected:
        value = actual[key]
        if key == "LINAS_WORKER_QUEUE":
            if value not in WORKER_QUEUES:
                raise RuntimeError("Runtime process environment contains an invalid worker queue")
            continue
        if key == "SHELL":
            shell = value.strip()
            if shell not in ALLOWED_ROOT_SHELLS:
                raise RuntimeError(
                    "Runtime process environment contains an invalid root identity: SHELL="
                    + (shell if re.fullmatch(r"/[A-Za-z0-9._/-]+", shell) else "invalid")
                )
            continue
        if key in FIXED_ROOT_PROCESS_VALUES:
            if value != FIXED_ROOT_PROCESS_VALUES[key]:
                raise RuntimeError("Runtime process environment contains an invalid root identity")
            continue
        if key == "INVOCATION_ID" and re.fullmatch(r"[0-9a-f]{32}", value):
            continue
        if key == "JOURNAL_STREAM" and re.fullmatch(r"[0-9]+:[0-9]+", value):
            continue
        if key in {"SYSTEMD_EXEC_PID", "WATCHDOG_PID", "WATCHDOG_USEC"} and re.fullmatch(r"[1-9][0-9]*", value):
            continue
        if key == "MEMORY_PRESSURE_WATCH" and value.startswith("/sys/fs/cgroup/"):
            continue
        if key == "MEMORY_PRESSURE_WRITE" and re.fullmatch(r"[A-Za-z0-9+/=]+", value):
            continue
        if key == "NOTIFY_SOCKET" and value in {
            "/run/systemd/notify",
            "@/org/freedesktop/systemd1/notify",
        }:
            continue
        if key in SYSTEMD_EPHEMERAL_KEYS:
            raise RuntimeError("Runtime process systemd metadata is malformed")
        extra_names.append(key)
    if extra_names:
        raise RuntimeError(
            "Runtime process environment contains an unauthorized extra key: " + ",".join(sorted(extra_names))
        )


def validate_evidence_pair(node01: dict[str, object], node02: dict[str, object], *, expected_sha: str) -> None:
    expected_keys = {
        "format",
        "node_id",
        "expected_release_sha",
        "projection_sha256",
        "keyset_sha256",
        "key_count",
        "node_local_schema_sha256",
    }
    for node_id, evidence in (("node01", node01), ("node02", node02)):
        key_count = evidence.get("key_count")
        if (
            set(evidence) != expected_keys
            or evidence.get("format") != FORMAT
            or evidence.get("node_id") != node_id
            or evidence.get("expected_release_sha") != expected_sha
            or not isinstance(key_count, int)
            or key_count <= 0
            or not all(
                re.fullmatch(r"[0-9a-f]{64}", str(evidence.get(key) or ""))
                for key in ("projection_sha256", "keyset_sha256", "node_local_schema_sha256")
            )
        ):
            raise RuntimeError("Cluster runtime environment evidence is invalid")
    compared = ("projection_sha256", "keyset_sha256", "key_count", "node_local_schema_sha256")
    if any(node01[key] != node02[key] for key in compared):
        raise RuntimeError("Cluster runtime environments are divergent")


def _load_evidence(path: Path) -> dict[str, object]:
    raw = json.loads(path.read_text(encoding="utf-8", errors="strict"))
    if not isinstance(raw, dict):
        raise RuntimeError("Cluster runtime environment evidence is invalid")
    return {str(key): value for key, value in raw.items()}


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    fingerprint = commands.add_parser("fingerprint")
    fingerprint.add_argument("--env-file", type=Path, default=Path("/opt/linasbot/.env"))
    fingerprint.add_argument("--node-id", choices=sorted(NODE_LOCAL_VALUES), required=True)
    fingerprint.add_argument("--expected-release-sha", required=True)
    fingerprint.add_argument("--process-environ", type=Path)
    fingerprint.add_argument(
        "--transient-verifier",
        action="store_true",
        help="require the closed precommit verification-only process additions",
    )
    compare = commands.add_parser("compare")
    compare.add_argument("--node01-evidence", type=Path, required=True)
    compare.add_argument("--node02-evidence", type=Path, required=True)
    compare.add_argument("--expected-release-sha", required=True)
    return parser


def main() -> int:
    args = _parser().parse_args()
    if args.command == "fingerprint":
        if os.geteuid() != 0 or os.getegid() != 0:
            raise RuntimeError("Cluster runtime environment proof requires root")
        projection = load_projection(args.env_file, node_id=args.node_id)
        if args.process_environ is not None:
            verify_process_environment(
                projection,
                args.process_environ,
                node_id=args.node_id,
                transient_release_sha=(args.expected_release_sha if args.transient_verifier else None),
            )
        print(json.dumps(projection_evidence(projection, node_id=args.node_id, expected_sha=args.expected_release_sha)))
        return 0
    if args.command == "compare":
        validate_evidence_pair(
            _load_evidence(args.node01_evidence),
            _load_evidence(args.node02_evidence),
            expected_sha=args.expected_release_sha,
        )
        print("[cluster-env] parity_verified=true")
        return 0
    raise AssertionError("unreachable")


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, RuntimeError, UnicodeError, json.JSONDecodeError) as exc:
        print(f"[cluster-env] blocked={type(exc).__name__}", file=sys.stderr)
        if str(exc) and "=" not in str(exc):
            print(f"[cluster-env] reason={exc}", file=sys.stderr)
        raise SystemExit(1) from None
