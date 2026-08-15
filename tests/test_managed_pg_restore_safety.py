from __future__ import annotations

import subprocess
from pathlib import Path

SCRIPT = Path("scripts/ha/managed_pg_restore_verify.sh")


def test_legacy_full_database_apply_is_unconditionally_retired(tmp_path: Path) -> None:
    result = subprocess.run(
        [
            "bash",
            str(SCRIPT),
            str(tmp_path / "managed.env"),
            "--apply",
            "--expected-dump-sha256",
            "a" * 64,
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 2
    assert "legacy in-place restore is retired" in result.stderr


def test_verifier_is_read_only_deep_and_never_transports_secret_env_to_tmp() -> None:
    source = SCRIPT.read_text(encoding="utf-8")

    assert 'if [[ "$APPLY" -eq 1 ]]; then' in source
    assert '["pg_restore", "--list", str(DUMP)]' in source
    assert "--expected-dump-sha256" in source
    assert "CREATE DATABASE" not in source
    assert '"pg_restore",\n        "-Fc"' not in source
    assert "scp -o" not in source
    assert "/tmp/managed_pg_restore_env" not in source
    assert "source and restored target are the same live PostgreSQL database" in source
    assert "table_content_sha256" in source
    assert "row_content_digest" in source
    assert "last_value" in source
    assert "cannot authenticate" in source
    assert "VERIFY_PASS" not in source


def test_verifier_requires_an_exact_immutable_dump_digest(tmp_path: Path) -> None:
    result = subprocess.run(
        ["bash", str(SCRIPT), str(tmp_path / "managed.env"), "--expected-dump-sha256", "bad"],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 2
    assert "must be 64 lowercase hexadecimal" in result.stderr
