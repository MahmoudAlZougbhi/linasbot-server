"""Pathspec contract for the production mutation untracked/ignored source audit."""

from __future__ import annotations

import inspect
import os
import subprocess
from pathlib import Path

import pytest

from scripts.ha import production_mutation_guard as guard

RUNTIME_DIRS = ("scripts", "services", "db", "modules", "handlers", "storage")
GIT_ENV = {
    "GIT_AUTHOR_NAME": "test",
    "GIT_AUTHOR_EMAIL": "test@example.invalid",
    "GIT_COMMITTER_NAME": "test",
    "GIT_COMMITTER_EMAIL": "test@example.invalid",
}


def _commit_repo(repo: Path) -> str:
    script = repo / "scripts" / "prod_cm_backup.sh"
    script.parent.mkdir(parents=True)
    script.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
    (repo / ".gitignore").write_text(
        "\n".join(
            (
                "venv/",
                "dashboard/node_modules/",
                "/ignored_root.py",
                *(f"{directory}/ignored.py" for directory in RUNTIME_DIRS),
                "",
            )
        ),
        encoding="utf-8",
    )
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    subprocess.run(["git", "-C", str(repo), "add", "."], check=True)
    env = {**os.environ, **GIT_ENV}
    subprocess.run(["git", "-C", str(repo), "commit", "-q", "-m", "fixture"], check=True, env=env)
    return subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _write_python(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("raise RuntimeError('shadow')\n", encoding="utf-8")


def test_root_python_pathspec_is_top_glob_only() -> None:
    source = inspect.getsource(guard._require_no_untracked_runtime_source)
    assert 'pathspecs = ("scripts", "services", "db", "modules", "handlers", "storage", ":(top,glob)*.py")' in source
    assert '"*.py"' not in source
    assert "'*.py'" not in source
    assert "for ignored in (False, True):" in source


def test_ignored_nested_python_under_venv_is_allowed(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    sha = _commit_repo(repo)
    _write_python(repo / "venv" / "lib" / "python3.12" / "site-packages" / "pkg.py")
    guard._require_exact_release(repo, sha, "scripts/prod_cm_backup.sh")


def test_ignored_nested_python_under_dashboard_node_modules_is_allowed(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    sha = _commit_repo(repo)
    _write_python(repo / "dashboard" / "node_modules" / "pkg" / "index.py")
    guard._require_exact_release(repo, sha, "scripts/prod_cm_backup.sh")


def test_ignored_root_python_is_rejected(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    sha = _commit_repo(repo)
    _write_python(repo / "ignored_root.py")
    with pytest.raises(RuntimeError, match="shadow the authorized release"):
        guard._require_exact_release(repo, sha, "scripts/prod_cm_backup.sh")


def test_untracked_root_python_is_rejected(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    sha = _commit_repo(repo)
    _write_python(repo / "untracked_root.py")
    with pytest.raises(RuntimeError, match="shadow the authorized release"):
        guard._require_exact_release(repo, sha, "scripts/prod_cm_backup.sh")


@pytest.mark.parametrize("directory", RUNTIME_DIRS)
def test_untracked_python_inside_protected_runtime_dirs_is_rejected(tmp_path: Path, directory: str) -> None:
    repo = tmp_path / "repo"
    sha = _commit_repo(repo)
    _write_python(repo / directory / "shadow.py")
    with pytest.raises(RuntimeError, match="shadow the authorized release"):
        guard._require_exact_release(repo, sha, "scripts/prod_cm_backup.sh")


@pytest.mark.parametrize("directory", RUNTIME_DIRS)
def test_ignored_python_inside_protected_runtime_dirs_is_rejected(tmp_path: Path, directory: str) -> None:
    repo = tmp_path / "repo"
    sha = _commit_repo(repo)
    _write_python(repo / directory / "ignored.py")
    with pytest.raises(RuntimeError, match="shadow the authorized release"):
        guard._require_exact_release(repo, sha, "scripts/prod_cm_backup.sh")
