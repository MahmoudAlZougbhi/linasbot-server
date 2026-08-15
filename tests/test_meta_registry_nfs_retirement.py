from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Any

import pytest

from scripts.ha import registry_nfs_config as config
from scripts.ha import retire_meta_registry_nfs_ha as retire

RELEASE_SHA = "a" * 40
PG_SHA = "b" * 64
TX_ID = "mnr_" + "c" * 64
STAMP = "20260814T120000Z"


def _journal(*, phase: str = "prepared", decision: str = "rollback") -> dict[str, Any]:
    return retire._journal_payload(
        tx_id=TX_ID,
        expected_release_sha=RELEASE_SHA,
        expected_pg_sha256=PG_SHA,
        stamp=STAMP,
        node01_config_sha256="1" * 64,
        node01_runtime_sha256="2" * 64,
        node01_post_config_sha256="a" * 64,
        node02_config_sha256="3" * 64,
        node02_runtime_sha256="4" * 64,
        node02_post_config_sha256="b" * 64,
        phase=phase,
        decision=decision,
    )


def _lock_fd(tmp_path: Path) -> int:
    return os.open(tmp_path / "lock", os.O_RDWR | os.O_CREAT, 0o600)


def _receipt_payload(journal: dict[str, Any], outcome: str) -> dict[str, Any]:
    return {
        "schema": retire.SCHEMA,
        **retire._journal_identity(journal),
        "outcome": outcome,
        "completed_at": "2026-08-14T12:30:00Z",
    }


def test_plan_checks_both_active_baselines_without_mutation(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    calls: list[tuple[str, str]] = []

    class Peer:
        def call(self, request: dict[str, Any]) -> dict[str, Any]:
            calls.append(("node02", str(request["action"])))
            if request["action"] == "preimage":
                return {
                    "ok": True,
                    "config_sha256": "3" * 64,
                    "runtime_sha256": "4" * 64,
                    "post_config_sha256": "b" * 64,
                }
            return {"ok": True, "status": "active"}

        def close(self) -> None:
            calls.append(("node02", "close"))

    monkeypatch.setattr(retire, "ACTIVE_JOURNAL", tmp_path / "absent.active")
    monkeypatch.setattr(retire, "_new_tx_id", lambda *_args: TX_ID)
    monkeypatch.setattr(retire, "_open_application_lock", lambda: _lock_fd(tmp_path))
    monkeypatch.setattr(retire, "_assert_no_other_transaction", lambda: None)
    monkeypatch.setattr(retire, "PeerSession", Peer)
    monkeypatch.setattr(
        retire,
        "_preimage_digests",
        lambda role: {
            "config_sha256": "1" * 64,
            "runtime_sha256": "2" * 64,
            "post_config_sha256": "a" * 64,
        },
    )
    monkeypatch.setattr(
        retire,
        "_node_command",
        lambda role, _journal, *, lock_fd, action: calls.append((role, action)),
    )

    assert retire._plan(RELEASE_SHA, PG_SHA) == 0
    assert calls[:2] == [("node02", "preflight"), ("node01", "preflight")]
    assert all(action != "apply" for _, action in calls)
    assert "PLAN_OK" in capsys.readouterr().out


def test_recovery_seeds_absent_peer_prepared_prefix_before_abort(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    journal = _journal()
    calls: list[str] = []
    peer_journal: dict[str, Any] | None = None

    class Peer:
        def call(self, request: dict[str, Any]) -> dict[str, Any]:
            nonlocal peer_journal
            action = str(request["action"])
            calls.append(action)
            if action == "journal-read":
                if peer_journal is None:
                    return {"ok": True, "journal": None, "receipt_status": "absent"}
                return {"ok": True, "journal": peer_journal, "journal_sha256": "d" * 64}
            if action == "journal-write":
                peer_journal = dict(request["journal"])
                return {"ok": True, "status": "prepared", "journal_sha256": "d" * 64}
            if action == "state":
                return {"ok": True, "status": "active"}
            if action == "finalize":
                return {"ok": True, "status": "aborted"}
            raise AssertionError(action)

        def close(self) -> None:
            calls.append("close")

    monkeypatch.setattr(retire, "_load_journal", lambda: dict(journal))
    monkeypatch.setattr(retire, "_journal_digest", lambda: "e" * 64)
    monkeypatch.setattr(retire, "_read_receipt", lambda _tx: None)
    monkeypatch.setattr(retire, "_open_application_lock", lambda: _lock_fd(tmp_path))
    monkeypatch.setattr(retire, "_assert_no_other_transaction", lambda: None)
    monkeypatch.setattr(retire, "PeerSession", Peer)
    monkeypatch.setattr(retire, "_config_state", lambda *_args, **_kwargs: "active")
    monkeypatch.setattr(retire, "_write_receipt", lambda *_args, **_kwargs: tmp_path / "receipt")
    monkeypatch.setattr(retire, "_durable_unlink", lambda _path: calls.append("unlink-local"))

    confirmation = retire._confirm_recovery(TX_ID, "rollback", "e" * 64)
    assert (
        retire._recover(
            expected_journal_sha256="e" * 64,
            decision="rollback",
            confirmation=confirmation,
        )
        == 0
    )
    assert calls[:3] == ["journal-read", "journal-write", "state"]
    assert "finalize" in calls
    assert calls.index("journal-write") < calls.index("finalize")


def test_forward_recovery_refuses_durable_aborted_peer_receipt(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    journal = _journal()

    class Peer:
        def call(self, request: dict[str, Any]) -> dict[str, Any]:
            if request["action"] == "journal-read":
                return {
                    "ok": True,
                    "journal": None,
                    "receipt": _receipt_payload(journal, "aborted"),
                    "receipt_status": "aborted",
                }
            raise AssertionError(request["action"])

        def close(self) -> None:
            pass

    monkeypatch.setattr(retire, "_load_journal", lambda: dict(journal))
    monkeypatch.setattr(retire, "_journal_digest", lambda: "e" * 64)
    monkeypatch.setattr(retire, "_read_receipt", lambda _tx: None)
    monkeypatch.setattr(retire, "_open_application_lock", lambda: _lock_fd(tmp_path))
    monkeypatch.setattr(retire, "_assert_no_other_transaction", lambda: None)
    monkeypatch.setattr(retire, "PeerSession", Peer)

    with pytest.raises(PermissionError, match="aborted"):
        retire._recover(
            expected_journal_sha256="e" * 64,
            decision="forward",
            confirmation=retire._confirm_recovery(TX_ID, "forward", "e" * 64),
        )


def _patch_transaction_runtime(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    *,
    lose_peer_apply_ack: bool = False,
) -> tuple[list[str], Any, dict[str, str], Path]:
    state_root = tmp_path / "state"
    state_root.mkdir(mode=0o700)
    active = state_root / "registry-nfs-retire.active"
    real_load = retire._load_journal
    real_digest = retire._journal_digest
    events: list[str] = []
    local = {"state": "active"}

    class Peer:
        def __init__(self) -> None:
            self.state = "active"
            self.journal: dict[str, Any] | None = None
            self.receipt: dict[str, Any] | None = None
            self.lose_ack = lose_peer_apply_ack

        def call(self, request: dict[str, Any]) -> dict[str, Any]:
            action = str(request["action"])
            events.append(f"peer-{action}")
            if action == "preflight":
                return {"ok": True, "status": self.state}
            if action == "preimage":
                return {
                    "ok": True,
                    "config_sha256": "3" * 64,
                    "runtime_sha256": "4" * 64,
                    "post_config_sha256": "b" * 64,
                }
            if action == "journal-write":
                self.journal = dict(request["journal"])
                return {
                    "ok": True,
                    "status": self.journal["phase"],
                    "journal_sha256": retire._sha256_bytes(retire._canonical(self.journal)),
                }
            if action == "journal-read":
                if self.journal is not None:
                    return {
                        "ok": True,
                        "journal": dict(self.journal),
                        "journal_sha256": retire._sha256_bytes(retire._canonical(self.journal)),
                    }
                return {
                    "ok": True,
                    "journal": None,
                    "receipt": self.receipt,
                    "receipt_status": "absent" if self.receipt is None else self.receipt["outcome"],
                }
            if action == "apply":
                self.state = "retired"
                if self.lose_ack:
                    self.lose_ack = False
                    raise retire.NfsRetirementError("simulated node02 apply ACK loss")
                return {"ok": True, "status": self.state}
            if action == "rollback":
                self.state = "active"
                return {"ok": True, "status": self.state}
            if action == "state":
                return {"ok": True, "status": self.state}
            if action == "postverify":
                return {"ok": True, "status": "verified"}
            if action == "finalize":
                self.receipt = _receipt_payload(dict(request["journal"]), str(request["outcome"]))
                self.journal = None
                return {"ok": True, "status": self.receipt["outcome"]}
            raise AssertionError(action)

        def close(self) -> None:
            events.append("peer-close")

    peer = Peer()

    def node_command(
        role: str,
        _journal_value: dict[str, Any],
        *,
        lock_fd: int,
        action: str,
    ) -> None:
        assert role == "node01"
        assert lock_fd >= 0
        events.append(f"local-{action}")
        if action == "apply":
            local["state"] = "retired"
        elif action == "rollback":
            local["state"] = "active"

    monkeypatch.setattr(retire, "STATE_ROOT", state_root)
    monkeypatch.setattr(retire, "ACTIVE_JOURNAL", active)

    def ensure_state_root(path: Path = state_root) -> None:
        path.mkdir(parents=True, exist_ok=True)
        path.chmod(0o700)

    monkeypatch.setattr(retire, "_ensure_state_root", ensure_state_root)
    monkeypatch.setattr(retire, "_load_journal", lambda path=active: real_load(path))
    monkeypatch.setattr(retire, "_journal_digest", lambda path=active: real_digest(path))
    monkeypatch.setattr(retire, "_new_tx_id", lambda *_args: TX_ID)
    monkeypatch.setattr(retire, "_open_application_lock", lambda: _lock_fd(tmp_path))
    monkeypatch.setattr(retire, "_assert_no_other_transaction", lambda: None)
    monkeypatch.setattr(retire, "PeerSession", lambda: peer)
    monkeypatch.setattr(retire, "_node_command", node_command)
    monkeypatch.setattr(
        retire,
        "_preimage_digests",
        lambda role: {
            "config_sha256": "1" * 64,
            "runtime_sha256": "2" * 64,
            "post_config_sha256": "a" * 64,
        },
    )
    monkeypatch.setattr(retire, "_journaled_config_state", lambda role, journal: local["state"])
    monkeypatch.setattr(retire, "_postverify_node", lambda *_args: events.append("local-postverify"))
    return events, peer, local, active


def test_apply_commits_node02_then_node01_with_preimages_bound_before_mutation(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    events, peer, local, active = _patch_transaction_runtime(monkeypatch, tmp_path)

    assert retire._apply(RELEASE_SHA, PG_SHA, retire._confirm_apply(RELEASE_SHA, PG_SHA)) == 0
    assert not active.exists()
    assert retire._receipt_status(TX_ID) == "committed"
    assert peer.receipt is not None and peer.receipt["node02_runtime_sha256"] == "4" * 64
    assert local["state"] == "retired"
    assert events.index("peer-apply") < events.index("local-apply")
    assert events.index("local-postverify") < events.index("peer-finalize")


def test_lost_node02_apply_ack_is_recoverable_to_exact_active_baseline(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    events, peer, local, active = _patch_transaction_runtime(
        monkeypatch,
        tmp_path,
        lose_peer_apply_ack=True,
    )
    with pytest.raises(retire.NfsRetirementError, match="ACK loss"):
        retire._apply(RELEASE_SHA, PG_SHA, retire._confirm_apply(RELEASE_SHA, PG_SHA))
    assert active.is_file()
    assert peer.state == "retired"
    assert local["state"] == "active"

    digest = retire._journal_digest()
    confirmation = retire._confirm_recovery(TX_ID, "rollback", digest)
    assert (
        retire._recover(
            expected_journal_sha256=digest,
            decision="rollback",
            confirmation=confirmation,
        )
        == 0
    )
    assert peer.state == "active"
    assert local["state"] == "active"
    assert not active.exists()
    assert retire._receipt_status(TX_ID) == "aborted"
    assert "peer-rollback" in events


@pytest.mark.parametrize(
    ("source", "target", "fstype", "expected"),
    [
        (f"10.106.0.3:{retire.REGISTRY_DIR}", str(retire.REGISTRY_DIR), "nfs4", "active"),
        (f"10.106.0.9:{retire.REGISTRY_DIR}", str(retire.REGISTRY_DIR), "nfs4", "inconsistent"),
        (f"10.106.0.3:{retire.REGISTRY_DIR}", str(retire.REGISTRY_DIR), "ext4", "inconsistent"),
    ],
)
def test_node02_state_requires_exact_mount_source_target_and_type(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    source: str,
    target: str,
    fstype: str,
    expected: str,
) -> None:
    fstab = tmp_path / "fstab"
    fstab.write_text("one exact entry\n", encoding="utf-8")
    monkeypatch.setattr(retire, "FSTAB_PATH", fstab)

    def fake_run(command: list[str], **_kwargs: Any) -> subprocess.CompletedProcess[str]:
        if "fstab-count" in command:
            return subprocess.CompletedProcess(command, 0, stdout="1\n", stderr="")
        if command[0] == "findmnt":
            return subprocess.CompletedProcess(
                command,
                0,
                stdout=f"{source} {target} {fstype}\n",
                stderr="",
            )
        raise AssertionError(command)

    monkeypatch.setattr(retire, "_capture", fake_run)
    assert retire._config_state("node02") == expected


def test_retired_state_rejects_unrelated_config_change_before_rollback(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    fstab = tmp_path / "fstab"
    fstab.write_text("unrelated baseline\n", encoding="utf-8")
    expected_post = retire._sha256_bytes(fstab.read_bytes())
    monkeypatch.setattr(retire, "FSTAB_PATH", fstab)

    def fake_run(command: list[str], **_kwargs: Any) -> subprocess.CompletedProcess[str]:
        if "fstab-count" in command:
            return subprocess.CompletedProcess(command, 0, stdout="0\n", stderr="")
        if command[0] == "findmnt":
            return subprocess.CompletedProcess(command, 1, stdout="", stderr="")
        raise AssertionError(command)

    monkeypatch.setattr(retire, "_capture", fake_run)
    assert retire._config_state("node02", expected_post_config_sha256=expected_post) == "retired"

    fstab.write_text("unrelated baseline\nnew unrelated line\n", encoding="utf-8")
    assert retire._config_state("node02", expected_post_config_sha256=expected_post) == "inconsistent"


def test_exact_parser_can_capture_only_the_target_export() -> None:
    target = "/opt/linasbot_data/meta_registry"
    lines = [
        f"{target} 10.106.0.4(rw,sync)\n",
        f"{target}_backup 10.106.0.4(ro)\n",
        f"# {target} 10.106.0.9(rw)\n",
    ]
    assert config.selected_text(lines, lambda line: config.export_entry_matches(line, target=target)) == lines[0]


def test_node_script_gates_peer_retired_check_to_node01_apply_only() -> None:
    script = (Path(__file__).resolve().parents[1] / "scripts/ha/remove_registry_nfs.sh").read_text()
    apply_gate = 'if [[ "$APPLY" -eq 1 ]]; then'
    peer_error = "peer node02 registry NFS mount must be retired first"
    assert script.index(apply_gate, script.index('if [[ "$ROLE" == "node02" ]]')) < script.index(peer_error)
    assert "active_export_exact_snapshot" in script
    assert 'cmp -s -- "$active_backup" "$active_current"' in script
    assert "umount -l" not in script


def test_child_timeout_terminates_the_process_group(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    signals: list[tuple[int, int]] = []

    class Process:
        pid = 4242
        returncode: int | None = None

        def communicate(self, *, timeout: float) -> tuple[bytes, bytes]:
            assert timeout == retire.NODE_COMMAND_TIMEOUT_SECONDS
            raise subprocess.TimeoutExpired(["blocked-child"], timeout)

        def poll(self) -> int | None:
            return self.returncode

        def wait(self, *, timeout: float) -> int:
            assert timeout == 2.0
            self.returncode = -15
            return self.returncode

    process = Process()
    monkeypatch.setattr(retire.subprocess, "Popen", lambda *_args, **_kwargs: process)
    monkeypatch.setattr(retire.os, "killpg", lambda pid, sig: signals.append((pid, sig)))

    with pytest.raises(retire.NfsRetirementError, match="child timed out"):
        retire._run(["blocked-child"])

    assert signals == [(process.pid, retire.signal.SIGTERM)]


def test_captured_probe_timeout_terminates_the_process_group(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    signals: list[tuple[int, int]] = []

    class Process:
        pid = 4343
        returncode: int | None = None

        def communicate(
            self,
            *,
            input: bytes | str | None,
            timeout: float,
        ) -> tuple[bytes, bytes]:
            assert input is None
            assert timeout == retire.NODE_PROBE_TIMEOUT_SECONDS
            raise subprocess.TimeoutExpired(["blocked-probe"], timeout)

        def poll(self) -> int | None:
            return self.returncode

        def wait(self, *, timeout: float) -> int:
            assert timeout == 2.0
            self.returncode = -15
            return self.returncode

    process = Process()
    monkeypatch.setattr(retire.subprocess, "Popen", lambda *_args, **_kwargs: process)
    monkeypatch.setattr(retire.os, "killpg", lambda pid, sig: signals.append((pid, sig)))

    with pytest.raises(retire.NfsRetirementError, match="child timed out"):
        retire._capture(["blocked-probe"])

    assert signals == [(process.pid, retire.signal.SIGTERM)]


def test_peer_rpc_timeout_terminates_the_half_open_channel(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    terminated: list[bool] = []

    class Input:
        closed = False

        def write(self, payload: bytes) -> None:
            assert payload.endswith(b"\n")

        def flush(self) -> None:
            pass

    class Output:
        def fileno(self) -> int:
            return 99

    class Process:
        stdin = Input()
        stdout = Output()

        def poll(self) -> None:
            return None

    session = retire.PeerSession.__new__(retire.PeerSession)
    session._process = Process()
    session._buffer = b""
    monkeypatch.setattr(retire, "PEER_RPC_TIMEOUT_SECONDS", 0.0)
    monkeypatch.setattr(session, "_terminate", lambda: terminated.append(True))

    with pytest.raises(retire.NfsRetirementError, match="response timed out"):
        session.call({"action": "preimage"})

    assert terminated == [True]


def test_peer_rpc_deadlines_cover_bounded_nested_work_without_becoming_unbounded() -> None:
    assert retire._peer_rpc_timeout({"action": "preimage"}) == retire.PEER_RPC_TIMEOUT_SECONDS
    assert retire._peer_rpc_timeout({"action": "apply"}) == max(
        retire.PEER_RPC_TIMEOUT_SECONDS,
        retire.NODE_COMMAND_TIMEOUT_SECONDS + (4 * retire.NODE_PROBE_TIMEOUT_SECONDS) + 30.0,
    )
    assert retire._peer_rpc_timeout({"action": "postverify"}) == max(
        retire.PEER_RPC_TIMEOUT_SECONDS,
        (3 * retire.NODE_COMMAND_TIMEOUT_SECONDS) + 30.0,
    )


def test_application_lock_contention_fails_fast(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(retire, "APPLICATION_LOCK", tmp_path / "live.lock")

    def busy(_fd: int, operation: int) -> None:
        assert operation & retire.fcntl.LOCK_NB
        raise BlockingIOError

    monkeypatch.setattr(retire.fcntl, "flock", busy)
    with pytest.raises(retire.NfsRetirementError, match="holds the application lock"):
        retire._open_application_lock()
