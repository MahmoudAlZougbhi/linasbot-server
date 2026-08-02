from __future__ import annotations

import subprocess
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "scan_tracked_secrets.sh"


def _run(command: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, cwd=cwd, capture_output=True, check=False, text=True)


def _init_repo(path: Path) -> None:
    assert _run(["git", "init", "-q"], path).returncode == 0
    assert _run(["git", "config", "user.email", "ci@example.invalid"], path).returncode == 0
    assert _run(["git", "config", "user.name", "CI"], path).returncode == 0


def test_secret_scan_passes_for_clean_tracked_files(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    (tmp_path / "app.py").write_text("SAFE = True\n", encoding="utf-8")
    assert _run(["git", "add", "app.py"], tmp_path).returncode == 0

    result = _run(["bash", str(SCRIPT)], tmp_path)

    assert result.returncode == 0
    assert result.stdout.strip() == "Secret scan passed"


def test_secret_scan_fails_without_rendering_matched_credential(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    fake_credential = "EAA" + ("A" * 40)
    (tmp_path / "app.py").write_text(f'VALUE = "{fake_credential}"\n', encoding="utf-8")
    assert _run(["git", "add", "app.py"], tmp_path).returncode == 0

    result = _run(["bash", str(SCRIPT)], tmp_path)

    assert result.returncode == 1
    assert "Potential secret or default password found" in result.stdout
    assert fake_credential not in result.stdout
    assert fake_credential not in result.stderr


def test_secret_scan_rejects_tracked_monty_key_without_rendering_it(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    fake_credential = "M" * 24
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    config_file = config_dir / "montymobile_templates.json"
    config_file.write_text(f'{{"api_config": {{"api_key": "{fake_credential}"}}}}\n', encoding="utf-8")
    assert _run(["git", "add", str(config_file.relative_to(tmp_path))], tmp_path).returncode == 0

    result = _run(["bash", str(SCRIPT)], tmp_path)

    assert result.returncode == 1
    assert "Tracked Monty API key must be empty" in result.stdout
    assert fake_credential not in result.stdout
    assert fake_credential not in result.stderr


def test_secret_scan_ignores_noncredential_monty_notes(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    config_file = config_dir / "montymobile_templates.json"
    config_file.write_text(
        '{"api_config": {"api_key": ""}, "notes": {"api_key": "Set it through the production environment only."}}\n',
        encoding="utf-8",
    )
    assert _run(["git", "add", str(config_file.relative_to(tmp_path))], tmp_path).returncode == 0

    result = _run(["bash", str(SCRIPT)], tmp_path)

    assert result.returncode == 0
    assert result.stdout.strip() == "Secret scan passed"


def test_secret_scan_fails_closed_when_git_scan_cannot_run(tmp_path: Path) -> None:
    result = _run(["bash", str(SCRIPT)], tmp_path)

    assert result.returncode == 2
    assert "Secret scan failed to execute" in result.stderr
