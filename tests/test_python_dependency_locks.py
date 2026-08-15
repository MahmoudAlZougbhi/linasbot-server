from __future__ import annotations

import re
from pathlib import Path

import pytest

from scripts import verify_python_locks as locks


def _write_lock(path: Path, headers: set[str], requirements: list[str]) -> None:
    path.write_text(
        "\n".join([*sorted(headers), "", "--only-binary :all:", "", *requirements, ""]),
        encoding="utf-8",
    )


def test_checked_in_python_locks_are_exact_and_consistent() -> None:
    assert locks.main() == 0


def test_lock_rejects_source_drift_unhashed_and_remote_entries(tmp_path: Path) -> None:
    source = tmp_path / "requirements.txt"
    source.write_text("safe-package==1\n", encoding="utf-8")
    lock = tmp_path / "requirements.lock"
    headers = locks.expected_headers(source)
    _write_lock(lock, headers, ["safe-package==1 --hash=sha256:" + "a" * 64])
    assert locks.validate_lock(lock, source)["safe-package"][0] == "1"

    source.write_text("safe-package==1\nomitted-package>=2\n", encoding="utf-8")
    omitted_headers = locks.expected_headers(source)
    _write_lock(lock, omitted_headers, ["safe-package==1 --hash=sha256:" + "a" * 64])
    with pytest.raises(RuntimeError, match="omits direct source requirements"):
        locks.validate_lock(lock, source)

    source.write_text("safe-package==2\n", encoding="utf-8")
    with pytest.raises(RuntimeError, match="authority is stale"):
        locks.validate_lock(lock, source)

    source.write_text("safe-package==1\n", encoding="utf-8")
    _write_lock(lock, headers, ["safe-package==1"])
    with pytest.raises(RuntimeError, match="unhashed"):
        locks.validate_lock(lock, source)

    _write_lock(
        lock,
        headers,
        ["safe-package @ https://example.invalid/package.whl --hash=sha256:" + "a" * 64],
    )
    with pytest.raises(RuntimeError, match="remote reference"):
        locks.validate_lock(lock, source)


def test_development_authority_must_match_production_pin_and_hash(tmp_path: Path) -> None:
    source = tmp_path / "requirements.txt"
    dev_source = tmp_path / "requirements-dev.txt"
    source.write_text("safe-package==1\n", encoding="utf-8")
    dev_source.write_text("pytest==9\n", encoding="utf-8")
    production = tmp_path / "requirements.lock"
    development = tmp_path / "requirements-dev.lock"
    _write_lock(
        production,
        locks.expected_headers(source),
        ["safe-package==1 --hash=sha256:" + "a" * 64],
    )
    _write_lock(
        development,
        locks.expected_headers(source, dev_source),
        [
            "safe-package==2 --hash=sha256:" + "b" * 64,
            "pytest==9 --hash=sha256:" + "c" * 64,
        ],
    )
    prod_entries = locks.validate_lock(production, source)
    dev_entries = locks.validate_lock(development, source, dev_source)
    with pytest.raises(RuntimeError, match="diverges"):
        locks.validate_pair(prod_entries, dev_entries)


def test_quality_gate_uses_immutable_runtime_locks_and_actions() -> None:
    source = (locks.ROOT / ".github/workflows/quality-gates.yml").read_text(encoding="utf-8")
    mypy_config = (locks.ROOT / "mypy.ini").read_text(encoding="utf-8")
    uses = re.findall(r"^\s*- uses:\s*([^\s#]+)", source, flags=re.MULTILINE)
    assert uses
    assert all(re.fullmatch(r"[^@]+@[0-9a-f]{40}", action) for action in uses)
    assert "actions/setup-python" not in source
    for contract in (
        "ubuntu-24.04",
        "cpython-3.13.15%2B20260814-x86_64-unknown-linux-gnu-install_only_stripped.tar.gz",
        "aaca2af2ab4d7b68a712660d1334c0cfd5ec13c0312ccd30c29122d8d0342320",
        'test "$(PYTHONDONTWRITEBYTECODE=1 "$runtime/bin/python3.13" -B --version)" = "Python 3.13.15"',
        '"$runtime/bin/python3.13" -B -m venv "$RUNNER_TEMP/linas-qg-venv"',
        "requirements-dev.lock",
        "requirements.lock --strict",
        "--only-binary=:all: --require-hashes",
        'node-version: "22.23.2"',
        'test "$(npm --version)" = "10.9.8"',
    ):
        assert contract in source
    assert "python_version = 3.13" in mypy_config
