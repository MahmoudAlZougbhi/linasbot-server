#!/usr/bin/env python3
"""Fail closed unless Python production/dev locks match their reviewed inputs."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PRODUCTION_SOURCE = ROOT / "requirements.txt"
DEVELOPMENT_SOURCE = ROOT / "requirements-dev.txt"
PRODUCTION_LOCK = ROOT / "requirements.lock"
DEVELOPMENT_LOCK = ROOT / "requirements-dev.lock"
LOCK_FORMAT = "linas-python-lock-v1"
PYTHON_VERSION = "3.13.15"
PIP_VERSION = "26.2.1"
PIP_TOOLS_VERSION = "7.6.1"
PLATFORM = "linux-x86_64"
NAME_RE = re.compile(r"^([A-Za-z0-9][A-Za-z0-9_.-]*)(?:\[[^]]+\])?==([^ ;\\]+)")
SOURCE_NAME_RE = re.compile(
    r"^([A-Za-z0-9][A-Za-z0-9_.-]*)(?:\[[^]]+\])?\s*"
    r"(?:===|==|~=|!=|<=|>=|<|>|$)"
)
HASH_RE = re.compile(r"--hash=sha256:([0-9a-f]{64})(?:\s|$)")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def expected_headers(*sources: Path) -> set[str]:
    headers = {
        f"# linas-lock-format: {LOCK_FORMAT}",
        f"# linas-python: {PYTHON_VERSION}",
        f"# linas-pip: {PIP_VERSION}",
        f"# linas-pip-tools: {PIP_TOOLS_VERSION}",
        f"# linas-platform: {PLATFORM}",
        "# linas-binary-only: true",
    }
    headers.update(f"# linas-source: {source.name} sha256={_sha256(source)}" for source in sources)
    return headers


def _logical_requirements(text: str) -> list[str]:
    logical: list[str] = []
    pending = ""
    for raw_line in text.splitlines():
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped == "--only-binary :all:":
            continue
        if stripped.startswith("--hash=sha256:"):
            if not pending or re.fullmatch(r"--hash=sha256:[0-9a-f]{64}(?:\s*\\)?", stripped) is None:
                raise RuntimeError("Python lock contains an invalid hash continuation")
        elif stripped.startswith(("--", "-r ", "-c ", "-e ")):
            raise RuntimeError("Python lock contains an unauthorized resolver directive")
        content = stripped[:-1].rstrip() if stripped.endswith("\\") else stripped
        pending = f"{pending} {content}".strip()
        if not stripped.endswith("\\"):
            logical.append(pending)
            pending = ""
    if pending:
        raise RuntimeError("Python lock ends with an incomplete requirement")
    return logical


def _source_requirement_names(*sources: Path) -> set[str]:
    names: set[str] = set()
    for source in sources:
        for raw_line in source.read_text(encoding="utf-8").splitlines():
            stripped = raw_line.split("#", 1)[0].strip()
            if not stripped:
                continue
            if stripped.startswith(("-", "http://", "https://")) or " @ " in stripped:
                raise RuntimeError("Python dependency source contains an unauthorized directive")
            match = SOURCE_NAME_RE.match(stripped)
            if match is None:
                raise RuntimeError("Python dependency source contains an invalid requirement")
            names.add(re.sub(r"[-_.]+", "-", match.group(1)).lower())
    return names


def validate_lock(path: Path, *sources: Path) -> dict[str, tuple[str, frozenset[str]]]:
    payload = path.read_bytes()
    if b"\r" in payload or b"\0" in payload:
        raise RuntimeError("Python lock encoding is invalid")
    text = payload.decode("utf-8", "strict")
    present_headers = {line.strip() for line in text.splitlines() if line.startswith("# linas-")}
    if present_headers != expected_headers(*sources):
        raise RuntimeError("Python lock source or toolchain authority is stale")
    if " @ " in text or "://" in text:
        raise RuntimeError("Python lock contains an unauthorized direct or remote reference")
    if text.splitlines().count("--only-binary :all:") != 1:
        raise RuntimeError("Python lock does not enforce binary-only installation")
    entries: dict[str, tuple[str, frozenset[str]]] = {}
    for logical in _logical_requirements(text):
        match = NAME_RE.match(logical)
        hashes = frozenset(HASH_RE.findall(logical))
        if match is None or not hashes:
            raise RuntimeError("Python lock contains an unpinned or unhashed requirement")
        name = re.sub(r"[-_.]+", "-", match.group(1)).lower()
        if name in entries:
            raise RuntimeError("Python lock contains a duplicate distribution")
        entries[name] = (match.group(2), hashes)
    if not entries:
        raise RuntimeError("Python lock is empty")
    if missing := _source_requirement_names(*sources) - entries.keys():
        raise RuntimeError(f"Python lock omits direct source requirements: {','.join(sorted(missing))}")
    return entries


def validate_pair(
    production: dict[str, tuple[str, frozenset[str]]],
    development: dict[str, tuple[str, frozenset[str]]],
) -> None:
    for name, authority in production.items():
        if development.get(name) != authority:
            raise RuntimeError("Development lock diverges from production dependency authority")


def main() -> int:
    production = validate_lock(PRODUCTION_LOCK, PRODUCTION_SOURCE)
    development = validate_lock(DEVELOPMENT_LOCK, PRODUCTION_SOURCE, DEVELOPMENT_SOURCE)
    validate_pair(production, development)
    print(
        "[python-lock] verified=true "
        f"production_distributions={len(production)} development_distributions={len(development)}"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, RuntimeError, UnicodeError) as exc:
        print(f"[python-lock] blocked={type(exc).__name__}")
        raise SystemExit(1) from None
