"""Prove App A apply remote script survives drone-ssh 1.8.0 script_stop rewrite."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "meta-app-a-login-config-apply.yml"
DRONE_STOP = (
    "DRONE_SSH_PREV_COMMAND_EXIT_CODE=$? ; "
    "if [ $DRONE_SSH_PREV_COMMAND_EXIT_CODE -ne 0 ]; then "
    "exit $DRONE_SSH_PREV_COMMAND_EXIT_CODE; fi;"
)


def _apply_script() -> str:
    payload = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    script = payload["jobs"]["apply"]["steps"][0]["with"]["script"]
    assert isinstance(script, str)
    return script


def _drain_assignment() -> str:
    return next(
        line.strip()
        for line in _apply_script().splitlines()
        if line.strip().startswith("DRAIN_SECONDS=")
    )


def _drain_python_c() -> str:
    drain = _drain_assignment()
    marker = " -c '"
    start = drain.index(marker) + len(marker)
    end = drain.index("' \"$REPO_DIR/.env\"", start)
    code = drain[start:end]
    assert "import sys" in code
    assert "dotenv_values" in code
    assert "META_HA_LB_DRAIN_SECONDS" in code
    assert "sys.exit(" in code
    assert "raise SystemExit" not in code
    return code


def _drone_ssh_script_stop(script: str) -> str:
    commands: list[str] = []
    for raw in script.split("\n"):
        cmd = raw.strip()
        if not cmd:
            continue
        commands.append(cmd)
        if not cmd.endswith("\\"):
            commands.append(DRONE_STOP)
    return "\n".join(commands) + "\n"


def _run_drain_code(env_path: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-c", _drain_python_c(), str(env_path)],
        check=False,
        capture_output=True,
        text=True,
    )


def test_apply_workflow_keeps_script_stop_and_single_line_drain() -> None:
    source = WORKFLOW.read_text(encoding="utf-8")
    script = _apply_script()
    drain = _drain_assignment()
    assert "script_stop: true" in source
    assert "appleboy/ssh-action@7eaf76671a0d7eec5d98ee897acda4f968735a17" in source
    assert "<<'PY'" not in script
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


def test_script_stop_rewrite_executes_drain_assignment(tmp_path: Path) -> None:
    remote = _drone_ssh_script_stop(_apply_script())
    lines = remote.splitlines()
    drain_idx = next(i for i, line in enumerate(lines) if line.startswith("DRAIN_SECONDS="))
    fragment = "\n".join(lines[drain_idx : drain_idx + 2]) + "\n"
    assert fragment.startswith("DRAIN_SECONDS=")
    assert DRONE_STOP in fragment
    assert "sleep " not in fragment
    assert "<<'PY'" not in fragment

    repo = tmp_path / "repo"
    python = repo / "venv" / "bin" / "python"
    python.parent.mkdir(parents=True)
    (repo / ".env").write_text("META_HA_LB_DRAIN_SECONDS=45\n", encoding="utf-8")
    python.symlink_to(sys.executable)

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
