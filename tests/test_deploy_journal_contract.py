"""Functional contracts for deploy journal writer/reader bootstrap authority."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / "scripts" / "ha" / "deploy_meta_release_ha.sh"


def _helper_source() -> str:
    return HELPER.read_text(encoding="utf-8")


def _embedded_python(function_name: str) -> str:
    source = _helper_source()
    start = source.index(f"{function_name}() {{")
    marker = "<<'PY'\n"
    python_start = source.index(marker, start) + len(marker)
    python_end = source.index("\nPY\n}", python_start)
    return source[python_start:python_end]


def _relax_owner_checks(code: str) -> str:
    replacements = {
        "parent_info.st_uid != 0": "False",
        "parent_info.st_gid != 0": "False",
        "before.st_uid != 0": "False",
        "before.st_gid != 0": "False",
        "opened.st_uid != 0": "False",
        "opened.st_gid != 0": "False",
        "os.chown(path, 0, 0, follow_symlinks=False)": "pass",
    }
    for old, new in replacements.items():
        code = code.replace(old, new)
    return code


WRITE_CODE = _relax_owner_checks(_embedded_python("write_deploy_journal"))
READ_CODE = _relax_owner_checks(_embedded_python("read_deploy_journal"))


def _digest_hex(value: str, *, width: int) -> str:
    seed = hashlib.sha256(value.encode()).hexdigest()
    return seed[:width]


def _journal_args(
    journal_path: Path,
    *,
    deploy_mode: str = "steady-confirmed",
    bootstrap: str = "b" * 64,
    node01_previous: str | None = None,
    node02_previous: str | None = None,
    phase: str = "preflight-proven",
    decision: str = "rollback",
    target_sha: str | None = None,
) -> list[str]:
    target = target_sha or _digest_hex("target", width=40)
    node01 = node01_previous or _digest_hex("node01", width=40)
    if deploy_mode == "steady-confirmed":
        node02 = node02_previous or node01
    else:
        node02 = node02_previous or _digest_hex("node02", width=40)
    tx_dir = f"/var/backups/linasbot-ha/{target}-20260815120000-12345"
    return [
        str(journal_path),
        _digest_hex("tx", width=32),
        target,
        node01,
        node02,
        "10.106.0.4",
        tx_dir,
        deploy_mode,
        bootstrap,
        "120",
        phase,
        decision,
        _digest_hex("helper", width=64),
        _digest_hex("runtime", width=64),
        _digest_hex("lb-attest", width=64),
        _digest_hex("lb-ready", width=64),
        "2026-08-15T12:00:00Z",
        "42",
        _digest_hex("artifact-api", width=64),
        _digest_hex("manifest", width=64),
        "99",
        "1",
        _digest_hex("target-tree", width=40),
    ]


def _write_journal(
    tmp_path: Path,
    *,
    deploy_mode: str = "steady-confirmed",
    bootstrap: str = "b" * 64,
    node01_previous: str | None = None,
    node02_previous: str | None = None,
    phase: str = "preflight-proven",
    decision: str = "rollback",
    target_sha: str | None = None,
) -> tuple[Path, list[str]]:
    state_root = tmp_path / "meta-ha-state"
    state_root.mkdir(mode=0o700)
    journal_path = state_root / "deploy.active"
    args = _journal_args(
        journal_path,
        deploy_mode=deploy_mode,
        bootstrap=bootstrap,
        node01_previous=node01_previous,
        node02_previous=node02_previous,
        phase=phase,
        decision=decision,
        target_sha=target_sha,
    )
    completed = subprocess.run(
        [sys.executable, "-B", "-I", "-c", WRITE_CODE, *args],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr or completed.stdout
    journal_path.chmod(0o600)
    return journal_path, args


def _read_journal(journal_path: Path) -> list[str]:
    completed = subprocess.run(
        [sys.executable, "-B", "-I", "-c", READ_CODE, str(journal_path)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr or completed.stdout
    fields = completed.stdout.splitlines()
    assert len(fields) == 22
    return fields


def _write_journal_expect_failure(tmp_path: Path, **kwargs: object) -> str:
    state_root = tmp_path / "meta-ha-state"
    state_root.mkdir(mode=0o700)
    journal_path = state_root / "deploy.active"
    args = _journal_args(journal_path, **kwargs)  # type: ignore[arg-type]
    completed = subprocess.run(
        [sys.executable, "-B", "-I", "-c", WRITE_CODE, *args],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode != 0
    return completed.stderr or completed.stdout


def _read_journal_expect_failure(journal_path: Path) -> str:
    completed = subprocess.run(
        [sys.executable, "-B", "-I", "-c", READ_CODE, str(journal_path)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode != 0
    return completed.stderr or completed.stdout


def test_steady_valid_digest_equal_baselines_round_trips_22_fields(tmp_path: Path) -> None:
    bootstrap = "b" * 64
    journal_path, _args = _write_journal(tmp_path, deploy_mode="steady-confirmed", bootstrap=bootstrap)
    fields = _read_journal(journal_path)
    assert fields[6] == "steady-confirmed"
    assert fields[7] == bootstrap
    assert fields[2] == fields[3]


@pytest.mark.parametrize("bootstrap", ["", "B" * 64, "abc", "b" * 63])
def test_steady_empty_or_malformed_bootstrap_rejects(tmp_path: Path, bootstrap: str) -> None:
    message = _write_journal_expect_failure(
        tmp_path,
        deploy_mode="steady-confirmed",
        bootstrap=bootstrap,
    )
    assert "bootstrap" in message.lower()


def test_steady_unequal_baselines_rejects(tmp_path: Path) -> None:
    message = _write_journal_expect_failure(
        tmp_path,
        deploy_mode="steady-confirmed",
        bootstrap="b" * 64,
        node01_previous="1" * 40,
        node02_previous="2" * 40,
    )
    assert "steady deployment journal contract is invalid" in message


def test_reconcile_valid_digest_unequal_baselines_round_trips(tmp_path: Path) -> None:
    bootstrap = "c" * 64
    journal_path, _args = _write_journal(
        tmp_path,
        deploy_mode="reconcile",
        bootstrap=bootstrap,
        node01_previous="1" * 40,
        node02_previous="2" * 40,
    )
    fields = _read_journal(journal_path)
    assert fields[6] == "reconcile"
    assert fields[7] == bootstrap
    assert fields[2] != fields[3]


def test_reconcile_equal_baselines_rejects(tmp_path: Path) -> None:
    baseline = "1" * 40
    message = _write_journal_expect_failure(
        tmp_path,
        deploy_mode="reconcile",
        bootstrap="c" * 64,
        node01_previous=baseline,
        node02_previous=baseline,
    )
    assert "reconciliation deployment journal contract is invalid" in message


@pytest.mark.parametrize("bootstrap", ["", "C" * 64, "abc", "c" * 63])
def test_reconcile_empty_or_malformed_bootstrap_rejects(tmp_path: Path, bootstrap: str) -> None:
    message = _write_journal_expect_failure(
        tmp_path,
        deploy_mode="reconcile",
        bootstrap=bootstrap,
        node01_previous="1" * 40,
        node02_previous="2" * 40,
    )
    assert "bootstrap" in message.lower()


def test_phase_update_preserves_bootstrap_and_rejects_digest_change(tmp_path: Path) -> None:
    bootstrap = "d" * 64
    journal_path, args = _write_journal(
        tmp_path,
        deploy_mode="steady-confirmed",
        bootstrap=bootstrap,
        phase="preflight-proven",
    )
    assert _read_journal(journal_path)[7] == bootstrap

    args[10] = "target-parity-awaiting-fresh-lb"
    completed = subprocess.run(
        [sys.executable, "-B", "-I", "-c", WRITE_CODE, *args],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr or completed.stdout
    journal_path.chmod(0o600)
    fields = _read_journal(journal_path)
    assert fields[9] == "target-parity-awaiting-fresh-lb"
    assert fields[7] == bootstrap

    args[8] = "e" * 64
    completed = subprocess.run(
        [sys.executable, "-B", "-I", "-c", WRITE_CODE, *args],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode != 0
    assert "immutable contract changed" in (completed.stderr or completed.stdout)


def test_steady_target_parity_journal_accepted_by_reader_paths(tmp_path: Path) -> None:
    bootstrap = "f" * 64
    journal_path, args = _write_journal(
        tmp_path,
        deploy_mode="steady-confirmed",
        bootstrap=bootstrap,
        phase="preflight-proven",
        decision="rollback",
    )
    args[10] = "target-parity-awaiting-fresh-lb"
    completed = subprocess.run(
        [sys.executable, "-B", "-I", "-c", WRITE_CODE, *args],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr or completed.stdout
    journal_path.chmod(0o600)
    digest = hashlib.sha256(journal_path.read_bytes()).hexdigest()

    install_fields = _read_journal(journal_path)
    assert len(install_fields) == 22
    assert install_fields[1] == args[2]
    assert install_fields[9] == "target-parity-awaiting-fresh-lb"
    assert install_fields[10] == "rollback"
    assert install_fields[14] == args[15]
    assert hashlib.sha256(journal_path.read_bytes()).hexdigest() == digest

    for reader in (
        lambda: _read_journal(journal_path),
        lambda: _read_journal(journal_path),
        lambda: _read_journal(journal_path),
    ):
        fields = reader()
        assert fields[7] == bootstrap
        assert fields[6] == "steady-confirmed"
        assert fields[2] == fields[3]
        assert fields[9] == "target-parity-awaiting-fresh-lb"
        assert fields[10] == "rollback"


def test_reader_rejects_steady_journal_with_empty_bootstrap(tmp_path: Path) -> None:
    journal_path, _args = _write_journal(tmp_path, deploy_mode="steady-confirmed", bootstrap="b" * 64)
    payload = json.loads(journal_path.read_text(encoding="utf-8"))
    payload["bootstrap_plan_sha256"] = ""
    journal_path.write_text(
        json.dumps(payload, allow_nan=False, separators=(",", ":"), sort_keys=True) + "\n",
        encoding="utf-8",
    )
    journal_path.chmod(0o600)
    message = _read_journal_expect_failure(journal_path)
    assert "deployment bootstrap digest is required" in message
