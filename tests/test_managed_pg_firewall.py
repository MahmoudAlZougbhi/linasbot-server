from __future__ import annotations

import json
import os
import re
import subprocess
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from scripts.ha import managed_pg_firewall as firewall
from scripts.ha import managed_pg_firewall_authority as authority
from scripts.ha import managed_pg_firewall_provider as provider


def _fake_doctl(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, rules: list[dict[str, str]]) -> Path:
    state = tmp_path / "provider.json"
    log = tmp_path / "provider.log"
    extra = tmp_path / "extra.flag"
    skip = tmp_path / "skip.flag"
    tags = tmp_path / "tags.json"
    state.write_text(json.dumps(rules), encoding="utf-8")
    tags.write_text(json.dumps(list(firewall.EXPECTED_TAG_MEMBERS)), encoding="utf-8")
    executable = tmp_path / "doctl"
    source = """#!/usr/bin/env python3
import json
import os
import sys
from pathlib import Path

log = Path(__LOG__)
tags = Path(__TAGS__)
args = sys.argv[1:]
assert args[:2] == ["--api-url", "https://api.digitalocean.com/v2"]
assert os.environ["HOME"] == "/nonexistent"
assert "FAKE_AMBIENT_AUTHORITY" not in os.environ
args = args[2:]
with log.open("a", encoding="utf-8") as handle:
    handle.write(json.dumps(args, separators=(",", ":")) + "\\n")
if args[:3] == ["compute", "droplet", "list"]:
    print(json.dumps([{"id": int(value), "tags": ["linas"]} for value in json.loads(tags.read_text())]))
    raise SystemExit(0)
raise SystemExit(4)
"""
    executable.write_text(
        source.replace("__LOG__", repr(str(log))).replace("__TAGS__", repr(str(tags))),
        encoding="utf-8",
    )
    executable.chmod(0o700)
    monkeypatch.setenv("DIGITALOCEAN_ACCESS_TOKEN", "test-token-" + "x" * 32)
    monkeypatch.setenv("FAKE_AMBIENT_AUTHORITY", "must-not-leak")

    def fake_api_request(method: str, path: str, body: object = None) -> object:
        assert path == f"/v2/databases/{firewall.CLUSTER_ID}/firewall"
        if method == "GET":
            call = ["databases", "firewalls", "list", firewall.CLUSTER_ID]
            with log.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(call, separators=(",", ":")) + "\n")
            stored = json.loads(state.read_text(encoding="utf-8"))
            rows = []
            for index, rule in enumerate(stored):
                row = {
                    "uuid": f"00000000-0000-0000-0000-{index:012d}",
                    "cluster_uuid": firewall.CLUSTER_ID,
                    "type": rule["type"],
                    "value": rule["value"],
                    "created_at": "2026-08-15T00:00:00Z",
                }
                if "description" in rule:
                    row["description"] = rule["description"]
                rows.append(row)
            if extra.exists():
                rows[0]["unexpected"] = True
            return {"rules": rows}
        assert method == "PUT"
        assert isinstance(body, dict) and set(body) == {"rules"} and isinstance(body["rules"], list)
        call = ["databases", "firewalls", "replace", firewall.CLUSTER_ID]
        with log.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(call, separators=(",", ":")) + "\n")
        if not skip.exists():
            state.write_text(json.dumps(body["rules"]), encoding="utf-8")
        return None

    monkeypatch.setattr(provider, "_api_request", fake_api_request)
    return executable


def _initial_rules() -> list[dict[str, str]]:
    return [
        {"type": "droplet", "value": "510629908"},
        {"type": "ip_addr", "value": "203.0.113.8", "description": "break-glass office"},
    ]


def _output_value(output: str, key: str) -> str:
    return next(line.split("=", 1)[1] for line in output.splitlines() if line.startswith(f"{key}="))


def _provider_calls(tmp_path: Path) -> list[list[str]]:
    log = tmp_path / "provider.log"
    if not log.exists():
        return []
    return [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]


def test_plan_and_apply_are_digest_bound_and_publish_rollback_before_replace(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    tmp_path.chmod(0o700)
    doctl = _fake_doctl(tmp_path, monkeypatch, _initial_rules())
    plan = tmp_path / "plan.json"
    rollback = tmp_path / "rollback.json"

    assert firewall.main(["--plan", "--plan-artifact", str(plan), "--doctl-bin", str(doctl)]) == 0
    confirmation = _output_value(capsys.readouterr().out, "APPLY_CONFIRMATION")
    assert plan.stat().st_mode & 0o777 == 0o600
    assert len(_provider_calls(tmp_path)) == 4

    with pytest.raises(PermissionError, match="ownership"):
        firewall.main(
            [
                "--apply",
                "--plan-artifact",
                str(plan),
                "--rollback-artifact",
                str(rollback),
                "--confirm",
                confirmation,
            ]
        )
    assert len(_provider_calls(tmp_path)) == 4

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
    assert rollback.stat().st_mode & 0o777 == 0o600
    calls = _provider_calls(tmp_path)
    replace_index = next(index for index, call in enumerate(calls) if call[:3] == ["databases", "firewalls", "replace"])
    assert rollback.exists()
    assert replace_index >= 8
    assert json.loads((tmp_path / "provider.json").read_text()) == firewall._desired_rules()


def test_apply_rejects_baseline_drift_and_mutated_token_before_provider_replace(
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
    mutated = f"{confirmation[:-1]}{'0' if confirmation[-1] != '0' else '1'}"

    with pytest.raises(PermissionError, match="confirmation"):
        firewall.main(
            [
                "--apply",
                "--plan-artifact",
                str(plan),
                "--rollback-artifact",
                str(rollback),
                "--confirm",
                mutated,
                "--owner-confirm",
                firewall.OWNER_CONFIRMATION,
            ]
        )
    (tmp_path / "provider.json").write_text(
        json.dumps([{"type": "tag", "value": "changed-after-plan"}]),
        encoding="utf-8",
    )
    with pytest.raises(PermissionError, match="baseline changed"):
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
    assert not any(call[:3] == ["databases", "firewalls", "replace"] for call in _provider_calls(tmp_path))


def test_apply_rejects_tag_membership_drift_before_provider_replace(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    tmp_path.chmod(0o700)
    doctl = _fake_doctl(tmp_path, monkeypatch, _initial_rules())
    plan = tmp_path / "plan.json"
    firewall.main(["--plan", "--plan-artifact", str(plan), "--doctl-bin", str(doctl)])
    confirmation = _output_value(capsys.readouterr().out, "APPLY_CONFIRMATION")
    (tmp_path / "tags.json").write_text(json.dumps(["510629908", "999999999"]), encoding="utf-8")

    with pytest.raises(PermissionError, match="tag membership changed"):
        firewall.main(
            [
                "--apply",
                "--plan-artifact",
                str(plan),
                "--rollback-artifact",
                str(tmp_path / "rollback.json"),
                "--confirm",
                confirmation,
                "--owner-confirm",
                firewall.OWNER_CONFIRMATION,
            ]
        )
    assert not any(call[:3] == ["databases", "firewalls", "replace"] for call in _provider_calls(tmp_path))


def test_restore_requires_a_fresh_current_bound_plan_and_preserves_reverse_rollback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    tmp_path.chmod(0o700)
    initial = _initial_rules()
    doctl = _fake_doctl(tmp_path, monkeypatch, initial)
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
    rollback_sha256 = authority.sha256(rollback.read_bytes())
    firewall.main(
        [
            "--restore-plan",
            "--source-rollback-artifact",
            str(rollback),
            "--expected-source-rollback-sha256",
            rollback_sha256,
            "--doctl-bin",
            str(doctl),
            "--plan-artifact",
            str(restore_plan),
        ]
    )
    restore_confirmation = _output_value(capsys.readouterr().out, "RESTORE_CONFIRMATION")
    assert (
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
        == 0
    )
    assert json.loads((tmp_path / "provider.json").read_text()) == initial
    assert reverse_rollback.is_file()
    replace_count = sum(call[:3] == ["databases", "firewalls", "replace"] for call in _provider_calls(tmp_path))
    with pytest.raises(PermissionError, match="superseded"):
        firewall.main(
            [
                "--apply",
                "--plan-artifact",
                str(plan),
                "--rollback-artifact",
                str(tmp_path / "replayed-rollback.json"),
                "--confirm",
                apply_confirmation,
                "--owner-confirm",
                firewall.OWNER_CONFIRMATION,
            ]
        )
    assert sum(call[:3] == ["databases", "firewalls", "replace"] for call in _provider_calls(tmp_path)) == replace_count


def test_plan_cannot_move_to_a_fresh_receipt_namespace(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    tmp_path.chmod(0o700)
    doctl = _fake_doctl(tmp_path, monkeypatch, _initial_rules())
    plan = tmp_path / "plan.json"
    firewall.main(["--plan", "--plan-artifact", str(plan), "--doctl-bin", str(doctl)])
    confirmation = _output_value(capsys.readouterr().out, "APPLY_CONFIRMATION")
    copied_dir = tmp_path / "copied"
    copied_dir.mkdir(mode=0o700)
    copied_plan = copied_dir / "plan.json"
    copied_plan.write_bytes(plan.read_bytes())
    copied_plan.chmod(0o600)
    before = len(_provider_calls(tmp_path))

    with pytest.raises(firewall.FirewallContractError, match="canonical"):
        firewall.main(
            [
                "--apply",
                "--plan-artifact",
                str(copied_plan),
                "--rollback-artifact",
                str(copied_dir / "rollback.json"),
                "--confirm",
                confirmation,
                "--owner-confirm",
                firewall.OWNER_CONFIRMATION,
            ]
        )
    assert len(_provider_calls(tmp_path)) == before


def test_durable_intent_resumes_after_expiry_without_double_replace(
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
    real_replace = firewall._replace_rules
    monkeypatch.setattr(firewall, "_replace_rules", lambda *_args: (_ for _ in ()).throw(OSError("crash")))
    with pytest.raises(OSError, match="crash"):
        firewall.main(arguments)
    monkeypatch.setattr(firewall, "_replace_rules", real_replace)

    real_datetime = firewall.datetime

    class FutureDateTime(datetime):
        @classmethod
        def now(cls, tz=None):  # noqa: ANN001, ANN206 - mirrors datetime's runtime API.
            return real_datetime.now(tz) + timedelta(hours=1)

    monkeypatch.setattr(firewall, "datetime", FutureDateTime)
    assert firewall.main(arguments) == 0
    assert sum(call[:3] == ["databases", "firewalls", "replace"] for call in _provider_calls(tmp_path)) == 1


def test_provider_ambiguity_keeps_durable_rollback_and_fails_closed(
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
    (tmp_path / "skip.flag").touch()

    with pytest.raises(firewall.FirewallContractError, match="postcondition differs"):
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
    assert rollback.is_file()


def test_unknown_provider_fields_and_unsafe_artifacts_fail_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tmp_path.chmod(0o700)
    doctl = _fake_doctl(tmp_path, monkeypatch, _initial_rules())
    (tmp_path / "extra.flag").touch()
    with pytest.raises(firewall.FirewallContractError, match="schema"):
        firewall.main(["--plan", "--plan-artifact", str(tmp_path / "plan.json"), "--doctl-bin", str(doctl)])

    unsafe = tmp_path / "unsafe.json"
    unsafe.write_text("{}\n", encoding="utf-8")
    unsafe.chmod(0o644)
    with pytest.raises(firewall.FirewallContractError, match="unsafe"):
        authority.secure_read(unsafe)


def test_hardlink_publication_crash_prefix_is_adopted(tmp_path: Path) -> None:
    tmp_path.chmod(0o700)
    target = tmp_path / "plan.json"
    temporary = tmp_path / ".plan.json.writing"
    temporary.write_bytes(b"authority\n")
    temporary.chmod(0o600)
    os.link(temporary, target)
    assert target.stat().st_nlink == 2

    assert authority.secure_read(target) == b"authority\n"
    assert target.stat().st_nlink == 1
    assert not temporary.exists()


def test_shell_entrypoint_is_isolated_and_contains_no_provider_mutation() -> None:
    root = Path(__file__).resolve().parents[1]
    wrapper = root / "scripts" / "ha" / "managed_pg_firewall.sh"
    source = wrapper.read_text(encoding="utf-8")
    assert "/usr/bin/python3 -B -I -S" in source
    assert "doctl" not in source
    subprocess.run(["bash", "-n", str(wrapper)], check=True)
    hashes = dict(re.findall(r'"(managed_pg_firewall[^\"]*\.py)": "([0-9a-f]{64})"', source))
    assert set(hashes) == {
        "managed_pg_firewall.py",
        "managed_pg_firewall_authority.py",
        "managed_pg_firewall_contract.py",
        "managed_pg_firewall_provider.py",
        "managed_pg_firewall_state.py",
    }
    for name, expected in hashes.items():
        assert authority.sha256((wrapper.parent / name).read_bytes()) == expected


def test_shell_entrypoint_ignores_hostile_path_and_symlink_siblings(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1]
    wrapper = root / "scripts" / "ha" / "managed_pg_firewall.sh"
    marker = tmp_path / "executed"
    fake_dirname = tmp_path / "dirname"
    fake_dirname.write_text(f'#!/bin/sh\ntouch {marker!s}\n/bin/dirname "$@"\n', encoding="utf-8")
    fake_dirname.chmod(0o700)
    symlink = tmp_path / "managed_pg_firewall.sh"
    symlink.symlink_to(wrapper)
    (tmp_path / "managed_pg_firewall.py").write_text(
        f"from pathlib import Path\nPath({str(marker)!r}).touch()\n",
        encoding="utf-8",
    )
    result = subprocess.run(
        ["/bin/bash", str(symlink), "--help"],
        check=False,
        capture_output=True,
        env={"PATH": f"{tmp_path}:/usr/bin:/bin"},
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert not marker.exists()
