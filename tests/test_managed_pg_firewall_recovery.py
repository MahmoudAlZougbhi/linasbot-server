from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from scripts.ha import managed_pg_firewall as firewall
from scripts.ha import managed_pg_firewall_authority as authority
from scripts.ha import managed_pg_firewall_state as transaction_state
from tests.test_managed_pg_firewall import _fake_doctl, _initial_rules, _output_value, _provider_calls


def test_restore_supersedes_source_before_its_own_intent_and_resumes_after_expiry(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    tmp_path.chmod(0o700)
    doctl = _fake_doctl(tmp_path, monkeypatch, _initial_rules())
    plan = tmp_path / "plan.json"
    rollback = tmp_path / "rollback.json"
    firewall.main(["--plan", "--plan-artifact", str(plan), "--doctl-bin", str(doctl)])
    apply_confirmation = _output_value(capsys.readouterr().out, "APPLY_CONFIRMATION")
    firewall.main(
        [
            "--apply",
            "--plan-artifact",
            str(plan),
            "--rollback-artifact",
            str(rollback),
            "--confirm",
            apply_confirmation,
            "--owner-confirm",
            firewall.OWNER_CONFIRMATION,
        ]
    )
    capsys.readouterr()
    restore_plan = tmp_path / "restore-plan.json"
    reverse_rollback = tmp_path / "reverse-rollback.json"
    firewall.main(
        [
            "--restore-plan",
            "--source-rollback-artifact",
            str(rollback),
            "--expected-source-rollback-sha256",
            firewall.sha256(rollback.read_bytes()),
            "--doctl-bin",
            str(doctl),
            "--plan-artifact",
            str(restore_plan),
        ]
    )
    restore_confirmation = _output_value(capsys.readouterr().out, "RESTORE_CONFIRMATION")
    restore_id = firewall._load_plan(restore_plan)[0]["plan_id"]
    restore_intent_path = transaction_state.receipt_path(tmp_path, restore_id, "intent")
    real_ensure = firewall.ensure_receipt

    def crash_before_restore_intent(path: Path, expected: dict[str, object]) -> None:
        if path == restore_intent_path:
            raise OSError("power loss before restore intent")
        real_ensure(path, expected)

    monkeypatch.setattr(firewall, "ensure_receipt", crash_before_restore_intent)
    arguments = [
        "--restore",
        "--plan-artifact",
        str(restore_plan),
        "--rollback-artifact",
        str(reverse_rollback),
        "--confirm",
        restore_confirmation,
        "--owner-confirm",
        firewall.OWNER_CONFIRMATION,
    ]
    with pytest.raises(OSError, match="power loss"):
        firewall.main(arguments)
    assert not restore_intent_path.exists()
    assert transaction_state.receipt_path(tmp_path, firewall._load_plan(plan)[0]["plan_id"], "superseded").is_file()
    provider_calls = len(_provider_calls(tmp_path))
    with pytest.raises(PermissionError, match="superseded"):
        firewall.main(
            [
                "--apply",
                "--plan-artifact",
                str(plan),
                "--rollback-artifact",
                str(rollback),
                "--confirm",
                apply_confirmation,
                "--owner-confirm",
                firewall.OWNER_CONFIRMATION,
            ]
        )
    assert len(_provider_calls(tmp_path)) == provider_calls

    monkeypatch.setattr(firewall, "ensure_receipt", real_ensure)
    real_datetime = firewall.datetime

    class FutureDateTime(datetime):
        @classmethod
        def now(cls, tz=None):  # noqa: ANN001, ANN206 - mirrors datetime's runtime API.
            return real_datetime.now(tz) + timedelta(hours=1)

    monkeypatch.setattr(firewall, "datetime", FutureDateTime)
    assert firewall.main(arguments) == 0
    assert reverse_rollback.is_file()
    assert transaction_state.receipt_path(tmp_path, restore_id, "complete").is_file()


def test_lost_completion_ack_reconciles_without_second_replace_and_later_drift_blocks(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    tmp_path.chmod(0o700)
    doctl = _fake_doctl(tmp_path, monkeypatch, _initial_rules())
    plan = tmp_path / "plan.json"
    rollback = tmp_path / "rollback.json"
    firewall.main(["--plan", "--plan-artifact", str(plan), "--doctl-bin", str(doctl)])
    confirmation = _output_value(capsys.readouterr().out, "APPLY_CONFIRMATION")
    plan_id = firewall._load_plan(plan)[0]["plan_id"]
    complete_path = transaction_state.receipt_path(tmp_path, plan_id, "complete")
    real_ensure = firewall.ensure_receipt

    def lose_completion_ack(path: Path, expected: dict[str, object]) -> None:
        if path == complete_path:
            raise OSError("lost completion ack")
        real_ensure(path, expected)

    arguments = [
        "--apply",
        "--plan-artifact",
        str(plan),
        "--rollback-artifact",
        str(rollback),
        "--confirm",
        confirmation,
        "--owner-confirm",
        firewall.OWNER_CONFIRMATION,
    ]
    monkeypatch.setattr(firewall, "ensure_receipt", lose_completion_ack)
    with pytest.raises(OSError, match="lost completion"):
        firewall.main(arguments)
    assert not complete_path.exists()
    assert sum(call[:3] == ["databases", "firewalls", "replace"] for call in _provider_calls(tmp_path)) == 1

    monkeypatch.setattr(firewall, "ensure_receipt", real_ensure)
    assert firewall.main(arguments) == 0
    assert complete_path.is_file()
    assert sum(call[:3] == ["databases", "firewalls", "replace"] for call in _provider_calls(tmp_path)) == 1

    (tmp_path / "provider.json").write_text('[{"type":"tag","value":"drifted"}]', encoding="utf-8")
    before = len(_provider_calls(tmp_path))
    with pytest.raises(PermissionError, match="no longer current"):
        firewall.main(arguments)
    assert len(_provider_calls(tmp_path)) == before + 4
    assert sum(call[:3] == ["databases", "firewalls", "replace"] for call in _provider_calls(tmp_path)) == 1


def test_conflicting_reverse_rollback_fails_before_source_is_superseded(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    tmp_path.chmod(0o700)
    doctl = _fake_doctl(tmp_path, monkeypatch, _initial_rules())
    plan = tmp_path / "plan.json"
    rollback = tmp_path / "rollback.json"
    firewall.main(["--plan", "--plan-artifact", str(plan), "--doctl-bin", str(doctl)])
    apply_confirmation = _output_value(capsys.readouterr().out, "APPLY_CONFIRMATION")
    apply_arguments = [
        "--apply",
        "--plan-artifact",
        str(plan),
        "--rollback-artifact",
        str(rollback),
        "--confirm",
        apply_confirmation,
        "--owner-confirm",
        firewall.OWNER_CONFIRMATION,
    ]
    firewall.main(apply_arguments)
    capsys.readouterr()
    restore_plan = tmp_path / "restore-plan.json"
    firewall.main(
        [
            "--restore-plan",
            "--source-rollback-artifact",
            str(rollback),
            "--expected-source-rollback-sha256",
            firewall.sha256(rollback.read_bytes()),
            "--doctl-bin",
            str(doctl),
            "--plan-artifact",
            str(restore_plan),
        ]
    )
    restore_confirmation = _output_value(capsys.readouterr().out, "RESTORE_CONFIRMATION")
    reverse_rollback = tmp_path / "reverse-rollback.json"
    reverse_rollback.write_bytes(b"different\n")
    reverse_rollback.chmod(0o600)
    source_id = firewall._load_plan(plan)[0]["plan_id"]
    restore_id = firewall._load_plan(restore_plan)[0]["plan_id"]
    replace_count = sum(call[:3] == ["databases", "firewalls", "replace"] for call in _provider_calls(tmp_path))

    with pytest.raises(firewall.FirewallContractError, match="already differs"):
        firewall.main(
            [
                "--restore",
                "--plan-artifact",
                str(restore_plan),
                "--rollback-artifact",
                str(reverse_rollback),
                "--confirm",
                restore_confirmation,
                "--owner-confirm",
                firewall.OWNER_CONFIRMATION,
            ]
        )
    assert not transaction_state.receipt_path(tmp_path, source_id, "superseded").exists()
    assert not transaction_state.receipt_path(tmp_path, restore_id, "intent").exists()
    assert firewall.main(apply_arguments) == 0
    assert sum(call[:3] == ["databases", "firewalls", "replace"] for call in _provider_calls(tmp_path)) == replace_count


@pytest.mark.parametrize(
    "reserved_name",
    [
        ".managed-pg-firewall.lock",
        f"managed-pg-firewall-mpf_{'a' * 64}.intent.json",
        f".managed-pg-firewall-mpf_{'b' * 64}.complete.json.writing",
        f"MANAGED-PG-FIREWALL-MPF_{'C' * 64}.SUPERSEDED.JSON",
    ],
)
def test_plan_rejects_reserved_transaction_names_without_touching_provider_or_artifact(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    reserved_name: str,
) -> None:
    tmp_path.chmod(0o700)
    initial = _initial_rules()
    doctl = _fake_doctl(tmp_path, monkeypatch, initial)
    artifact = tmp_path / reserved_name
    original = b"operator-owned-artifact\n"
    artifact.write_bytes(original)
    artifact.chmod(0o600)

    with pytest.raises(firewall.FirewallContractError, match="reserved transaction namespace"):
        firewall.main(["--plan", "--plan-artifact", str(artifact), "--doctl-bin", str(doctl)])

    assert artifact.read_bytes() == original
    assert _provider_calls(tmp_path) == []
    assert json.loads((tmp_path / "provider.json").read_text(encoding="utf-8")) == initial


@pytest.mark.parametrize("collision_kind", ["receipt", "receipt-temporary"])
def test_apply_rejects_own_receipt_namespace_before_provider_access(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    collision_kind: str,
) -> None:
    tmp_path.chmod(0o700)
    initial = _initial_rules()
    doctl = _fake_doctl(tmp_path, monkeypatch, initial)
    plan = tmp_path / "plan.json"
    firewall.main(["--plan", "--plan-artifact", str(plan), "--doctl-bin", str(doctl)])
    confirmation = _output_value(capsys.readouterr().out, "APPLY_CONFIRMATION")
    plan_id = firewall._load_plan(plan)[0]["plan_id"]
    if collision_kind == "receipt":
        rollback = transaction_state.receipt_path(tmp_path, plan_id, "superseded")
    else:
        intent = transaction_state.receipt_path(tmp_path, plan_id, "intent")
        rollback = tmp_path / f".{intent.name}.writing"
    provider_calls = len(_provider_calls(tmp_path))

    with pytest.raises(firewall.FirewallContractError, match="reserved transaction namespace"):
        firewall.main(
            [
                "--apply",
                "--plan-artifact",
                str(plan),
                "--rollback-artifact",
                str(rollback),
                "--confirm",
                confirmation,
                "--owner-confirm",
                firewall.OWNER_CONFIRMATION,
            ]
        )

    assert not rollback.exists()
    assert len(_provider_calls(tmp_path)) == provider_calls
    assert json.loads((tmp_path / "provider.json").read_text(encoding="utf-8")) == initial
    assert not transaction_state.receipt_path(tmp_path, plan_id, "intent").exists()


@pytest.mark.parametrize("target_exists", [False, True])
def test_write_once_quarantines_differing_temporary_and_exact_retry_recovers(
    tmp_path: Path,
    target_exists: bool,
) -> None:
    tmp_path.chmod(0o700)
    target = tmp_path / "artifact.json"
    expected = b"expected-authority\n"
    if target_exists:
        target.write_bytes(expected)
        target.chmod(0o600)
    temporary = tmp_path / ".artifact.json.writing"
    original = b"different-operator-artifact\n"
    temporary.write_bytes(original)
    temporary.chmod(0o600)

    with pytest.raises(authority.FirewallContractError, match="differed and was quarantined"):
        authority.write_once(target, expected)

    assert not temporary.exists()
    quarantines = list(tmp_path.glob(".managed-pg-firewall-quarantine-*.json"))
    assert len(quarantines) == 1
    quarantine = quarantines[0]
    assert quarantine.read_bytes() == original
    assert quarantine.stat().st_mode & 0o777 == 0o600
    assert target.exists() is target_exists
    if target_exists:
        assert target.read_bytes() == expected

    authority.write_once(target, expected)
    assert target.read_bytes() == expected
    assert quarantine.read_bytes() == original
