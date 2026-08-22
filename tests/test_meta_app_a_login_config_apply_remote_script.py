"""Prove the App A apply script runs intact and keeps fail-closed cleanup."""

from __future__ import annotations

import os
import shlex
import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "meta-app-a-login-config-apply.yml"


def _apply_step() -> dict[str, object]:
    payload = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    step = payload["jobs"]["apply"]["steps"][0]
    assert isinstance(step, dict)
    return step


def _apply_script() -> str:
    step = _apply_step()
    with_config = step["with"]
    assert isinstance(with_config, dict)
    script = with_config["script"]
    assert isinstance(script, str)
    return script


def _drain_assignment() -> str:
    return next(line.strip() for line in _apply_script().splitlines() if line.strip().startswith("DRAIN_SECONDS="))


def _drain_python_c() -> str:
    drain = _drain_assignment()
    marker = " -c '"
    start = drain.index(marker) + len(marker)
    end = drain.index('\' "$REPO_DIR/.env"', start)
    code = drain[start:end]
    assert "import sys" in code
    assert "dotenv_values" in code
    assert "META_HA_LB_DRAIN_SECONDS" in code
    assert "sys.exit(" in code
    assert "raise SystemExit" not in code
    return code


def _cleanup_function() -> str:
    script = _apply_script()
    start = script.index("fail_closed_cleanup() {")
    end = script.index("trap fail_closed_cleanup EXIT", start)
    cleanup = script[start:end]
    assert cleanup.rstrip().endswith("}")
    return cleanup


def _run_drain_code(env_path: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-c", _drain_python_c(), str(env_path)],
        check=False,
        capture_output=True,
        text=True,
    )


def _run_cleanup_harness(
    tmp_path: Path, *, transaction_complete: bool
) -> tuple[subprocess.CompletedProcess[str], Path, Path]:
    backup = tmp_path / "env.before"
    maintenance = tmp_path / "runtime-maintenance"
    state_root = tmp_path / "meta-ha"
    backup.write_text("exact pre-stage backup\n", encoding="utf-8")

    stub_bin = tmp_path / "bin"
    stub_bin.mkdir()
    sudo = stub_bin / "sudo"
    sudo.write_text(
        '#!/bin/sh\nif [ "$1" = "rm" ]; then\n  shift\n  exec /bin/rm "$@"\nfi\nexit 0\n',
        encoding="utf-8",
    )
    sudo.chmod(0o755)
    ssh = stub_bin / "ssh"
    ssh.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    ssh.chmod(0o755)

    trigger = "true" if transaction_complete else "false"
    harness = "\n".join(
        (
            "set -euo pipefail",
            f"ENV_BACKUP={shlex.quote(str(backup))}",
            f"META_HA_STATE_ROOT={shlex.quote(str(state_root))}",
            f"PERSISTENT_MAINTENANCE_FILE={shlex.quote(str(state_root / 'maintenance'))}",
            f"MAINTENANCE_FILE={shlex.quote(str(maintenance))}",
            "PEER_HOST=peer.invalid",
            f"MAINTENANCE_ARMED={'false' if transaction_complete else 'true'}",
            f"TRANSACTION_COMPLETE={'true' if transaction_complete else 'false'}",
            _cleanup_function(),
            "trap fail_closed_cleanup EXIT",
            trigger,
        )
    )
    completed = subprocess.run(
        ["/bin/bash", "-c", harness],
        check=False,
        capture_output=True,
        text=True,
        env={**os.environ, "PATH": f"{stub_bin}{os.pathsep}{os.environ['PATH']}"},
    )
    return completed, backup, maintenance


def test_apply_workflow_disables_script_stop_and_has_no_heredoc() -> None:
    source = WORKFLOW.read_text(encoding="utf-8")
    step = _apply_step()
    with_config = step["with"]
    assert isinstance(with_config, dict)
    script = _apply_script()
    drain = _drain_assignment()
    assert with_config["script_stop"] is False
    assert "script_stop: false" in source
    assert "script_stop: true" not in source
    assert "appleboy/ssh-action@7eaf76671a0d7eec5d98ee897acda4f968735a17" in source
    assert script.startswith("set -euo pipefail\n")
    assert "trap fail_closed_cleanup EXIT" in script
    assert "<<" not in script
    assert "python" in drain and " -c " in drain
    assert drain.count("\n") == 0
    _drain_python_c()


def test_extracted_drain_command_accepts_valid_and_rejects_invalid_intervals(
    tmp_path: Path,
) -> None:
    valid = tmp_path / "valid.env"
    low = tmp_path / "low.env"
    high = tmp_path / "high.env"
    empty = tmp_path / "empty.env"
    valid.write_text("META_HA_LB_DRAIN_SECONDS=45\n", encoding="utf-8")
    low.write_text("META_HA_LB_DRAIN_SECONDS=29\n", encoding="utf-8")
    high.write_text("META_HA_LB_DRAIN_SECONDS=301\n", encoding="utf-8")
    empty.write_text("", encoding="utf-8")

    accepted = _run_drain_code(valid)
    assert accepted.returncode == 0, accepted.stderr
    assert accepted.stdout.strip() == "45"

    for path in (low, high, empty):
        rejected = _run_drain_code(path)
        assert rejected.returncode != 0, path
        assert "invalid HA drain interval" in rejected.stderr or rejected.returncode != 0
        if path != empty:
            assert "invalid HA drain interval" in rejected.stderr


def test_intact_drain_assignment_executes_without_heredoc(tmp_path: Path) -> None:
    fragment = _drain_assignment() + "\n"
    assert fragment.startswith("DRAIN_SECONDS=")
    assert "sleep " not in fragment
    assert "<<" not in fragment

    repo = tmp_path / "repo"
    python = repo / "venv" / "bin" / "python"
    python.parent.mkdir(parents=True)
    (repo / ".env").write_text("META_HA_LB_DRAIN_SECONDS=45\n", encoding="utf-8")
    python.write_text(
        "#!/bin/sh\n" + f'exec {shlex.quote(sys.executable)} "$@"\n',
        encoding="utf-8",
    )
    python.chmod(0o755)

    completed = subprocess.run(
        ["/bin/bash", "-c", fragment + 'printf "%s\\n" "$DRAIN_SECONDS"\n'],
        check=False,
        capture_output=True,
        text=True,
        env={**os.environ, "REPO_DIR": str(repo)},
    )
    assert "syntax error near unexpected token `then'" not in completed.stderr
    assert completed.returncode == 0, (completed.stdout, completed.stderr)
    assert completed.stdout.strip() == "45"


def test_intact_cleanup_success_path_returns_zero(tmp_path: Path) -> None:
    completed, backup, maintenance = _run_cleanup_harness(tmp_path, transaction_complete=True)
    assert completed.returncode == 0, (completed.stdout, completed.stderr)
    assert not backup.exists()
    assert not maintenance.exists()
    assert "retained after uncertain transaction" not in completed.stderr


def test_intact_cleanup_failure_path_remains_fail_closed(tmp_path: Path) -> None:
    completed, backup, maintenance = _run_cleanup_harness(tmp_path, transaction_complete=False)
    assert completed.returncode == 1, (completed.stdout, completed.stderr)
    assert backup.is_file()
    assert maintenance.is_file()
    assert "HA maintenance retained after uncertain transaction" in completed.stderr
    assert "exact pre-stage backup retained" in completed.stderr
