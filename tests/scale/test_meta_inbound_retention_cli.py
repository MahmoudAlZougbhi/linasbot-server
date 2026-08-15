from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts import redact_meta_inbound_retention as retention_cli


def _summary(
    *,
    apply: bool,
    changed: int,
    redacted: int = 0,
    errors: int = 0,
    firestore_available: bool = True,
) -> dict[str, int | bool]:
    return {
        "apply": apply,
        "local_scanned": 1,
        "local_matched": changed,
        "local_changed": changed,
        "local_redacted": redacted,
        "local_active_matches": 0,
        "local_errors": errors,
        "firestore_requested": True,
        "firestore_available": firestore_available,
        "firestore_scanned": 0,
        "firestore_matched": 0,
        "firestore_changed": 0,
        "firestore_redacted": 0,
        "firestore_active_matches": 0,
        "firestore_errors": 0,
    }


def _patch_runtime(monkeypatch: pytest.MonkeyPatch, result: dict[str, int | bool]) -> None:
    import services.meta_inbound_retention as retention

    monkeypatch.setattr(retention_cli, "_load_runtime_environment", lambda _path: None)
    monkeypatch.setattr(
        retention,
        "redact_expired_terminal_inbound_events",
        lambda **_kwargs: result,
    )


def test_dirty_retention_dry_run_is_count_only_and_nonzero(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _patch_runtime(monkeypatch, _summary(apply=False, changed=2))

    exit_code = retention_cli.main([])

    output = json.loads(capsys.readouterr().out)
    assert exit_code == 3
    assert output["ok"] is False
    assert output["mode"] == "dry-run"
    assert output["remaining_expired"] == 2
    assert "payload" not in output


def test_retention_apply_requires_every_changed_row_to_be_redacted(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _patch_runtime(monkeypatch, _summary(apply=True, changed=2, redacted=1))

    exit_code = retention_cli.main(["--apply"])

    output = json.loads(capsys.readouterr().out)
    assert exit_code == 2
    assert output["ok"] is False
    assert output["remaining_expired"] == 1


def test_retention_apply_success_is_count_only(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _patch_runtime(monkeypatch, _summary(apply=True, changed=2, redacted=2))

    exit_code = retention_cli.main(["--apply"])

    output = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert output["ok"] is True
    assert output["remaining_expired"] == 0


def test_retention_cli_requires_explicit_existing_environment_file(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    missing = tmp_path / "missing.env"

    exit_code = retention_cli.main(["--env-file", str(missing)])

    captured = capsys.readouterr()
    output = json.loads(captured.err)
    assert exit_code == 2
    assert output == {"error_type": "RuntimeError", "mode": "dry-run", "ok": False}
    assert str(missing) not in captured.err


def test_retention_workflow_schedules_dry_run_and_manual_apply_requires_confirmation() -> None:
    workflow = Path(".github/workflows/meta-inbound-payload-retention.yml").read_text(encoding="utf-8")

    assert "schedule:" in workflow
    assert "RETENTION_OPERATION=dry_run" in workflow
    assert 'if [ "$RETENTION_OPERATION" = "apply" ]; then' in workflow
    assert "inputs.confirmation == 'APPLY_META_RETENTION'" in workflow
    assert 'ENV_FILE="$APP_DIR/.env"' in workflow
    assert '"$PYTHON_BIN" "$SCRIPT" --apply --env-file "$ENV_FILE"' in workflow
    assert workflow.count('"$PYTHON_BIN" "$SCRIPT" --env-file "$ENV_FILE"') == 2
    assert "no mutation performed" in workflow
