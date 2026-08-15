"""Regression: Meta registry backend env name has no misspelled alias."""

from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STALE = "META_APP_" + "REGISTRY_BACKEND"
CANONICAL = "META_REGISTRY_BACKEND"


def test_repo_has_zero_misspelled_registry_backend_env_names() -> None:
    completed = subprocess.run(
        ["git", "grep", "-n", STALE],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 1, completed.stdout
    assert completed.stdout == ""
    assert completed.stderr == ""


def test_ha_verifier_requires_explicit_canonical_registry_backend() -> None:
    source = (ROOT / "scripts" / "ha" / "verify_meta_release_ha.sh").read_text(encoding="utf-8")
    assert f'values.get("{CANONICAL}")' in source
    assert 'registry_backend != "postgres"' in source
    assert STALE not in source
    assert "or values.get" not in source.split("registry_backend =", 1)[1].split("\n", 1)[0]
