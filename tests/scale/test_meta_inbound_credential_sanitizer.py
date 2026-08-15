from __future__ import annotations

import json
import os
import stat
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

import services.scale.inbound_event_store as store
from scripts import sanitize_meta_inbound_ledgers as sanitizer_cli
from services.scale.inbound_event_store import InboundEventRecord


def _record(settings_snapshot: dict[str, object]) -> InboundEventRecord:
    now = time.time()
    return InboundEventRecord(
        event_id="ibe_sanitizer_test",
        kind="meta_dm",
        tenant_id="linas",
        claim_namespace="meta_social_dm_global",
        claim_key="linas:instagram:mid-sanitizer",
        state="accepted",
        created_at=now,
        updated_at=now,
        settings_snapshot=settings_snapshot,
    )


def _summary(
    *,
    apply: bool = False,
    changed: int = 1,
    sanitized: int | None = None,
) -> dict[str, int | bool]:
    sanitized_count = changed if apply and sanitized is None else int(sanitized or 0)
    return {
        "apply": apply,
        "local_scanned": 1,
        "local_changed": changed,
        "local_sanitized": sanitized_count,
        "local_errors": 0,
        "firestore_available": False,
        "firestore_scanned": 0,
        "firestore_changed": 0,
        "firestore_sanitized": 0,
        "firestore_errors": 0,
    }


def test_record_serialization_and_hydration_drop_meta_credentials() -> None:
    secret = "meta-credential-sentinel"
    unsafe = {
        "tenant_id": "linas",
        "binding_id": "binding-1",
        "app_secret": secret,
        "page_access_token": f"page-{secret}",
        "verify_token": f"verify-{secret}",
        "page_id": {"nested_secret": secret},
    }

    serialized = _record(unsafe).to_dict()

    assert serialized["settings_snapshot"] == {
        "tenant_id": "linas",
        "binding_id": "binding-1",
    }
    assert secret not in json.dumps(serialized)

    hydrated = InboundEventRecord.from_dict(serialized | {"settings_snapshot": unsafe})
    assert hydrated.settings_snapshot == {
        "tenant_id": "linas",
        "binding_id": "binding-1",
    }
    assert secret not in json.dumps(hydrated.to_dict())


def test_local_sanitizer_dry_run_then_apply_preserves_other_fields(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    secret = "historical-meta-secret-sentinel"
    root = tmp_path / "inbound_events"
    root.mkdir()
    unsafe_path = root / "ibe_unsafe.json"
    unsafe_path.write_text(
        json.dumps(
            {
                "event_id": "ibe_unsafe",
                "settings_snapshot": {
                    "tenant_id": "linas",
                    "binding_id": "binding-1",
                    "app_secret": secret,
                    "page_access_token": f"page-{secret}",
                },
                "future_top_level_field": {"must": "survive"},
            }
        ),
        encoding="utf-8",
    )
    clean_path = root / "ibe_clean.json"
    clean_path.write_text(
        json.dumps({"event_id": "ibe_clean", "settings_snapshot": {"tenant_id": "linas"}}),
        encoding="utf-8",
    )
    monkeypatch.setattr(store, "_store_dir", lambda: root)

    dry_run = store.sanitize_persisted_meta_credentials(apply=False, include_firestore=False)

    assert dry_run == {
        "apply": False,
        "local_scanned": 2,
        "local_changed": 1,
        "local_sanitized": 0,
        "local_errors": 0,
        "firestore_available": False,
        "firestore_scanned": 0,
        "firestore_changed": 0,
        "firestore_sanitized": 0,
        "firestore_errors": 0,
    }
    assert secret in unsafe_path.read_text(encoding="utf-8")

    applied = store.sanitize_persisted_meta_credentials(apply=True, include_firestore=False)

    assert applied["local_changed"] == 1
    assert applied["local_sanitized"] == 1
    assert applied["local_errors"] == 0
    sanitized = json.loads(unsafe_path.read_text(encoding="utf-8"))
    assert sanitized["settings_snapshot"] == {"tenant_id": "linas", "binding_id": "binding-1"}
    assert sanitized["future_top_level_field"] == {"must": "survive"}
    assert secret not in json.dumps(sanitized)
    assert stat.S_IMODE(unsafe_path.stat().st_mode) == 0o600


def test_local_sanitizer_reports_unreadable_records(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "inbound_events"
    root.mkdir()
    (root / "ibe_invalid.json").write_text("not-json", encoding="utf-8")
    monkeypatch.setattr(store, "_store_dir", lambda: root)

    result = store.sanitize_persisted_meta_credentials(apply=False, include_firestore=False)

    assert result["local_scanned"] == 0
    assert result["local_errors"] == 1


def test_public_local_document_helpers_preserve_unknown_fields_and_enforce_store_boundary(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "inbound_events"
    root.mkdir()
    ledger_path = root / "ibe_helper.json"
    ledger_path.write_text(
        json.dumps({"event_id": "ibe_helper", "future_field": {"keep": True}}),
        encoding="utf-8",
    )
    outside_path = tmp_path / "ibe_outside.json"
    outside_path.write_text(json.dumps({"event_id": "ibe_outside"}), encoding="utf-8")
    monkeypatch.setattr(store, "_store_dir", lambda: root)

    documents = list(store.iter_local_inbound_event_documents())
    assert documents == [(ledger_path, {"event_id": "ibe_helper", "future_field": {"keep": True}})]

    replacement = documents[0][1] | {"retention_status": "redacted"}
    with store.local_inbound_event_ledger_lock():
        store.replace_local_inbound_event_document(ledger_path, replacement)

    assert json.loads(ledger_path.read_text(encoding="utf-8")) == replacement
    assert stat.S_IMODE(ledger_path.stat().st_mode) == 0o600
    with pytest.raises(ValueError, match="outside"):
        store.replace_local_inbound_event_document(outside_path, {"event_id": "ibe_outside"})


def test_sanitizer_apply_lock_blocks_cross_process_file_put_until_scan_finishes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    data_root = tmp_path / "data"
    root = data_root / "logs" / "inbound_events"
    root.mkdir(parents=True)
    ready_path = tmp_path / "child-ready"
    complete_path = tmp_path / "child-complete"
    monkeypatch.setattr(store, "_store_dir", lambda: root)
    scan_entered = threading.Event()
    release_scan = threading.Event()
    sanitizer_errors: list[Exception] = []

    def blocking_local_scan(*, apply: bool) -> dict[str, int]:
        assert apply is True
        scan_entered.set()
        if not release_scan.wait(timeout=5):
            raise TimeoutError("test did not release sanitizer scan")
        return {
            "local_scanned": 0,
            "local_changed": 0,
            "local_sanitized": 0,
            "local_errors": 0,
        }

    def run_sanitizer() -> None:
        try:
            store.sanitize_persisted_meta_credentials(apply=True, include_firestore=False)
        except Exception as exc:
            sanitizer_errors.append(exc)

    monkeypatch.setattr(store, "_sanitize_local_meta_credentials", blocking_local_scan)
    sanitizer_thread = threading.Thread(target=run_sanitizer)
    child_code = "\n".join(
        (
            "import sys",
            "from pathlib import Path",
            "from services.scale.inbound_event_store import InboundEventRecord, _file_put",
            "ready, complete = (Path(value) for value in sys.argv[1:3])",
            "ready.write_text('ready', encoding='utf-8')",
            "record = InboundEventRecord(event_id='ibe_child', kind='meta_dm', tenant_id='linas', "
            "claim_namespace='claims', claim_key='key', state='accepted', created_at=1.0, updated_at=1.0)",
            "_file_put(record)",
            "complete.write_text('complete', encoding='utf-8')",
        )
    )
    env = os.environ.copy()
    env["LINASBOT_DATA_ROOT"] = str(data_root)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    process: subprocess.Popen[str] | None = None
    try:
        sanitizer_thread.start()
        assert scan_entered.wait(timeout=5)
        process = subprocess.Popen(
            [sys.executable, "-c", child_code, str(ready_path), str(complete_path)],
            cwd=Path(__file__).resolve().parents[2],
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        deadline = time.monotonic() + 5
        while not ready_path.exists() and time.monotonic() < deadline:
            time.sleep(0.01)
        assert ready_path.exists()
        time.sleep(0.2)
        assert process.poll() is None
        assert not complete_path.exists()

        release_scan.set()
        sanitizer_thread.join(timeout=5)
        assert not sanitizer_thread.is_alive()
        assert sanitizer_errors == []
        stdout, stderr = process.communicate(timeout=5)
        assert process.returncode == 0, (stdout, stderr)
        assert complete_path.is_file()
        assert (root / "ibe_child.json").is_file()
    finally:
        release_scan.set()
        sanitizer_thread.join(timeout=5)
        if process is not None and process.poll() is None:
            process.kill()
            process.communicate()


def test_cli_dirty_dry_run_is_nonzero_and_not_ok(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    calls: list[tuple[bool, bool]] = []

    def fake_sanitize(*, apply: bool, include_firestore: bool) -> dict[str, int | bool]:
        calls.append((apply, include_firestore))
        return _summary(apply=apply)

    monkeypatch.setattr(store, "sanitize_persisted_meta_credentials", fake_sanitize)

    assert sanitizer_cli.main(["--local-only"]) == 2

    captured = capsys.readouterr()
    assert calls == [(False, False)]
    assert captured.err == ""
    assert json.loads(captured.out) == {
        "ok": False,
        "mode": "dry-run",
        "remaining_unsafe": 1,
        **_summary(),
    }


def test_cli_clean_dry_run_is_ok(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(
        store,
        "sanitize_persisted_meta_credentials",
        lambda *, apply, include_firestore: _summary(apply=apply, changed=0),
    )

    assert sanitizer_cli.main(["--local-only"]) == 0

    captured = capsys.readouterr()
    assert captured.err == ""
    assert json.loads(captured.out) == {
        "ok": True,
        "mode": "dry-run",
        "remaining_unsafe": 0,
        **_summary(changed=0),
    }


def test_cli_mutates_only_with_explicit_apply(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    calls: list[tuple[bool, bool]] = []

    def fake_sanitize(*, apply: bool, include_firestore: bool) -> dict[str, int | bool]:
        calls.append((apply, include_firestore))
        return _summary(apply=apply)

    monkeypatch.setattr(store, "sanitize_persisted_meta_credentials", fake_sanitize)

    assert sanitizer_cli.main(["--apply", "--local-only"]) == 0

    captured = capsys.readouterr()
    assert calls == [(True, False)]
    assert captured.err == ""
    assert json.loads(captured.out) == {
        "ok": True,
        "mode": "apply",
        "remaining_unsafe": 0,
        **_summary(apply=True),
    }


def test_cli_never_renders_exception_text(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    secret = "exception-meta-secret-sentinel"

    def fail_sanitize(*, apply: bool, include_firestore: bool) -> dict[str, int | bool]:
        del apply, include_firestore
        raise RuntimeError(secret)

    monkeypatch.setattr(store, "sanitize_persisted_meta_credentials", fail_sanitize)

    assert sanitizer_cli.main(["--local-only"]) == 2

    captured = capsys.readouterr()
    assert secret not in captured.err
    assert json.loads(captured.err) == {
        "ok": False,
        "mode": "dry-run",
        "error_type": "RuntimeError",
    }
