from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.ha import managed_pg_firewall as firewall
from scripts.ha import managed_pg_firewall_contract as contract
from tests.test_managed_pg_firewall import _fake_doctl, _initial_rules, _output_value, _provider_calls


def _plan_apply(
    doctl: Path,
    capsys: pytest.CaptureFixture[str],
    plan: Path,
    rollback: Path,
) -> str:
    firewall.main(["--plan", "--plan-artifact", str(plan), "--doctl-bin", str(doctl)])
    confirmation = _output_value(capsys.readouterr().out, "APPLY_CONFIRMATION")
    assert (
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
        == 0
    )
    capsys.readouterr()
    return confirmation


def _restore_plan(
    source: Path,
    destination: Path,
    doctl: Path,
    capsys: pytest.CaptureFixture[str],
) -> str:
    firewall.main(
        [
            "--restore-plan",
            "--source-rollback-artifact",
            str(source),
            "--expected-source-rollback-sha256",
            firewall.sha256(source.read_bytes()),
            "--doctl-bin",
            str(doctl),
            "--plan-artifact",
            str(destination),
        ]
    )
    return _output_value(capsys.readouterr().out, "RESTORE_CONFIRMATION")


def _restore(plan: Path, rollback: Path, confirmation: str) -> None:
    assert (
        firewall.main(
            [
                "--restore",
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
        == 0
    )


def test_empty_rules_rollback_round_trips_through_official_put(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    tmp_path.chmod(0o700)
    doctl = _fake_doctl(tmp_path, monkeypatch, [])
    plan = tmp_path / "plan.json"
    rollback = tmp_path / "rollback.json"
    _plan_apply(doctl, capsys, plan, rollback)
    assert json.loads((tmp_path / "provider.json").read_text(encoding="utf-8")) == firewall._desired_rules()
    restore_plan = tmp_path / "restore-plan.json"
    confirmation = _restore_plan(rollback, restore_plan, doctl, capsys)
    restored = json.loads(restore_plan.read_text(encoding="utf-8"))
    assert restored["desired_rules"] == []
    assert restored["doctl_sha256"] == firewall.sha256(doctl.read_bytes())
    _restore(restore_plan, tmp_path / "reverse-rollback.json", confirmation)
    assert json.loads((tmp_path / "provider.json").read_text(encoding="utf-8")) == []
    calls = _provider_calls(tmp_path)
    assert any(call[:3] == ["compute", "droplet", "list"] for call in calls)
    assert any(call[:3] == ["databases", "firewalls", "list"] for call in calls)
    assert sum(call[:3] == ["databases", "firewalls", "replace"] for call in calls) == 2


def test_restore_of_restore_enforces_exact_linas_tag_members_before_put(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    tmp_path.chmod(0o700)
    initial = _initial_rules()
    doctl = _fake_doctl(tmp_path, monkeypatch, initial)
    plan = tmp_path / "plan.json"
    rollback = tmp_path / "rollback.json"
    _plan_apply(doctl, capsys, plan, rollback)
    restore_plan = tmp_path / "restore-plan.json"
    _restore(restore_plan, tmp_path / "reverse-rollback.json", _restore_plan(rollback, restore_plan, doctl, capsys))
    reverse = tmp_path / "reverse-rollback.json"
    assert json.loads((tmp_path / "provider.json").read_text(encoding="utf-8")) == initial
    replace_count = sum(call[:3] == ["databases", "firewalls", "replace"] for call in _provider_calls(tmp_path))
    (tmp_path / "tags.json").write_text(json.dumps(["510629908"]), encoding="utf-8")
    with pytest.raises(firewall.FirewallContractError, match="tag membership differs"):
        firewall.main(
            [
                "--restore-plan",
                "--source-rollback-artifact",
                str(reverse),
                "--expected-source-rollback-sha256",
                firewall.sha256(reverse.read_bytes()),
                "--doctl-bin",
                str(doctl),
                "--plan-artifact",
                str(tmp_path / "restore-of-restore.json"),
            ]
        )
    assert not (tmp_path / "restore-of-restore.json").exists()
    assert sum(call[:3] == ["databases", "firewalls", "replace"] for call in _provider_calls(tmp_path)) == replace_count
    (tmp_path / "tags.json").write_text(json.dumps(list(firewall.EXPECTED_TAG_MEMBERS)), encoding="utf-8")
    second_plan = tmp_path / "restore-of-restore.json"
    second_confirmation = _restore_plan(reverse, second_plan, doctl, capsys)
    assert json.loads(second_plan.read_text(encoding="utf-8"))["desired_rules"] == firewall._desired_rules()
    _restore(second_plan, tmp_path / "second-reverse.json", second_confirmation)
    assert json.loads((tmp_path / "provider.json").read_text(encoding="utf-8")) == firewall._desired_rules()


def test_restore_plan_requires_fresh_reviewed_doctl_and_preserves_descriptions(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    tmp_path.chmod(0o700)
    initial = _initial_rules()
    doctl = _fake_doctl(tmp_path, monkeypatch, initial)
    plan = tmp_path / "plan.json"
    rollback = tmp_path / "rollback.json"
    _plan_apply(doctl, capsys, plan, rollback)
    original_sha = json.loads(plan.read_text(encoding="utf-8"))["doctl_sha256"]
    reviewed = tmp_path / "reviewed-doctl"
    reviewed.write_bytes(doctl.read_bytes() + b"\n# reviewed\n")
    reviewed.chmod(0o700)
    with pytest.raises(firewall.FirewallContractError, match="restore-plan arguments"):
        firewall.main(
            [
                "--restore-plan",
                "--source-rollback-artifact",
                str(rollback),
                "--expected-source-rollback-sha256",
                firewall.sha256(rollback.read_bytes()),
                "--plan-artifact",
                str(tmp_path / "restore-plan.json"),
            ]
        )
    restore_plan = tmp_path / "restore-plan.json"
    confirmation = _restore_plan(rollback, restore_plan, reviewed, capsys)
    restored_plan = json.loads(restore_plan.read_text(encoding="utf-8"))
    assert restored_plan["doctl_path"] == str(reviewed)
    assert restored_plan["doctl_sha256"] == firewall.sha256(reviewed.read_bytes()) != original_sha
    assert restored_plan["desired_rules"] == initial
    assert any(rule.get("description") == "break-glass office" for rule in restored_plan["desired_rules"])
    _restore(restore_plan, tmp_path / "reverse-rollback.json", confirmation)
    assert json.loads((tmp_path / "provider.json").read_text(encoding="utf-8")) == initial


def test_normalize_rules_preserves_descriptions_and_allows_empty_list() -> None:
    assert contract.normalize_rules({"rules": []}) == []
    assert contract.normalize_rules(
        {
            "rules": [
                {
                    "uuid": "00000000-0000-0000-0000-000000000001",
                    "cluster_uuid": firewall.CLUSTER_ID,
                    "type": "ip_addr",
                    "value": "203.0.113.8",
                    "created_at": "2026-08-15T00:00:00Z",
                    "description": "break-glass office",
                }
            ]
        }
    ) == [{"description": "break-glass office", "type": "ip_addr", "value": "203.0.113.8"}]
