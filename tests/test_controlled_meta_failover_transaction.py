"""Focused safety contracts for the signed controlled Meta failover producer."""

from __future__ import annotations

import importlib.util
import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
PRODUCER_PATH = ROOT / "scripts" / "ha" / "controlled_meta_failover.py"
LB_PATH = ROOT / "scripts" / "ha" / "manage_do_lb_ready_healthcheck.py"


def _load(path: Path, name: str):  # type: ignore[no-untyped-def]
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


producer = _load(PRODUCER_PATH, "controlled_meta_failover_test")
lb = _load(LB_PATH, "controlled_meta_failover_lb_test")


def _context(*, now: datetime | None = None) -> dict[str, object]:
    now = now or datetime.now(UTC)
    return producer._validate_context(
        {
            "transaction_id": "mft_" + "f" * 64,
            "test_run_id": "mtr_" + "b" * 64,
            "manifest_sha256": "c" * 64,
            "release_sha": "a" * 40,
            "initial_node": "node01",
            "replay_node": "node02",
            "lb_ready_projection_sha256": "d" * 64,
            "minimum_drain_seconds": 30,
            "manifest_start": (now + timedelta(minutes=3)).isoformat(timespec="seconds").replace("+00:00", "Z"),
            "manifest_initial_cutoff": (now + timedelta(minutes=8))
            .isoformat(timespec="seconds")
            .replace("+00:00", "Z"),
            "manifest_final_cutoff": (now + timedelta(minutes=15)).isoformat(timespec="seconds").replace("+00:00", "Z"),
            "helper_sha256": "e" * 64,
        }
    )


def _observed_lb() -> dict[str, object]:
    return {
        "algorithm": "round_robin",
        "created_at": "2026-08-01T00:00:00Z",
        "disable_lets_encrypt_dns_records": False,
        "droplet_ids": [591901417, 510629908],
        "enable_backend_keepalive": True,
        "enable_proxy_protocol": False,
        "forwarding_rules": [
            {"entry_protocol": "http", "entry_port": 80, "target_protocol": "http", "target_port": 80},
            {
                "entry_protocol": "https",
                "entry_port": 443,
                "target_protocol": "http",
                "target_port": 80,
                "certificate_id": "ccd5-observed",
            },
        ],
        "health_check": {
            "protocol": "http",
            "port": 8003,
            "path": "/api/health",
            "check_interval_seconds": 5,
            "response_timeout_seconds": 3,
            "healthy_threshold": 2,
            "unhealthy_threshold": 3,
        },
        "http_idle_timeout_seconds": 60,
        "id": lb.LB_ID,
        "ip": lb.LB_IP,
        "ipv6": "",
        "name": lb.LB_NAME,
        "network_stack": "DUALSTACK",
        "project_id": "70160077-6e21-4fc7-9c81-45e6b60d8919",
        "redirect_http_to_https": True,
        "region": {"slug": "lon1", "name": "London 1"},
        "size": "lb-small",
        "size_unit": 1,
        "status": "active",
        "sticky_sessions": {"type": "none"},
        "subnet_uuid": "2415d1ce-b8e6-4707-bc89-56e234548d60",
        "tag": "",
        "type": "REGIONAL",
        "vpc_uuid": "d0e11d67-3fba-4966-b2db-6a471307df85",
    }


def test_plan_parser_builds_manifest_start_context_end_to_end(monkeypatch: pytest.MonkeyPatch) -> None:
    args = producer.build_parser().parse_args(
        [
            "plan-initial",
            "--manifest",
            "/protected/manifest.json",
            "--manifest-sha256",
            "c" * 64,
            "--transaction-id",
            "mft_" + "f" * 64,
            "--initial-node",
            "node01",
            "--lb-ready-attestation",
            "/protected/lb.json",
        ]
    )
    now = datetime.now(UTC)
    monkeypatch.setattr(
        producer,
        "_read_manifest",
        lambda *_args, **_kwargs: {
            "test_run_id": "mtr_" + "b" * 64,
            "release_sha": "a" * 40,
            "replay_node": "node02",
            "start": (now + timedelta(minutes=3)).isoformat(timespec="seconds").replace("+00:00", "Z"),
            "initial_cutoff": (now + timedelta(minutes=8)).isoformat(timespec="seconds").replace("+00:00", "Z"),
            "final_cutoff": (now + timedelta(minutes=15)).isoformat(timespec="seconds").replace("+00:00", "Z"),
        },
    )
    monkeypatch.setattr(
        producer,
        "_read_lb_attestation",
        lambda *_args, **_kwargs: ("d" * 64, 30, "1" * 64, _kwargs["manifest_start"]),
    )
    monkeypatch.setattr(producer, "_helper_sha256", lambda: "e" * 64)
    monkeypatch.setattr(producer, "_assert_initial_window", lambda _context: None)
    monkeypatch.setattr(
        producer,
        "_node_preflight",
        lambda _context: {
            "node_id": "node01",
            "release_sha": "a" * 40,
            "helper_sha256": "e" * 64,
            "machine_id_sha256": "1" * 64,
        },
    )
    monkeypatch.setattr(
        producer,
        "_remote",
        lambda _context, action: (
            {
                "node_id": "node02",
                "release_sha": "a" * 40,
                "helper_sha256": "e" * 64,
                "machine_id_sha256": "2" * 64,
            }
            if action == "preflight"
            else None
        ),
    )

    plan, context = producer._plan(args)
    assert context["manifest_start"] == plan["context"]["manifest_start"]
    assert context["minimum_drain_seconds"] == 30


def test_lb_helper_attestation_is_the_exact_importable_canonical_shape(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    before = lb.validate_observed_identity(_observed_lb())
    ready = lb.desired_projection(before)
    now = datetime.now(UTC)
    transaction_id = "mft_" + "f" * 64
    manifest_sha = "c" * 64
    manifest_start = (now + timedelta(minutes=3)).isoformat(timespec="seconds").replace("+00:00", "Z")
    payload = lb._failover_attestation_payload(ready, transaction_id, manifest_sha, "initial", "pre")
    digest = str(payload["ready_mutable_sha256"])
    state_root = tmp_path / "state"
    state_root.mkdir(mode=0o700)
    path = lb.failover_attestation_path_for(transaction_id, manifest_sha, "initial", "pre", state_root)
    path.write_bytes(producer._canonical(payload) + b"\n")
    path.chmod(0o600)
    monkeypatch.setattr(producer, "STATE_ROOT", state_root)
    monkeypatch.setattr(producer, "_secure_file", lambda candidate: candidate.stat())

    observed_digest, minimum, artifact_sha256, observed_at = producer._read_lb_attestation(
        path,
        transaction_id=transaction_id,
        manifest_sha256=manifest_sha,
        phase="initial",
        observation="pre",
        manifest_start=manifest_start,
        manifest_initial_cutoff=(now + timedelta(minutes=8)).isoformat(timespec="seconds").replace("+00:00", "Z"),
        manifest_final_cutoff=(now + timedelta(minutes=15)).isoformat(timespec="seconds").replace("+00:00", "Z"),
        require_fresh=True,
    )
    assert path.name == f"{lb.LB_ID}.failover.{transaction_id}.{manifest_sha}.initial.pre.json"
    assert observed_digest == digest
    assert minimum == 30
    assert artifact_sha256 == producer._digest(path.read_bytes())
    assert observed_at == payload["observed_at"]
    assert "install-lb-attestation" in producer.build_parser()._subparsers._group_actions[0].choices
    assert "plan-failover" in lb.build_parser()._subparsers._group_actions[0].choices
    assert "attest-failover" in lb.build_parser()._subparsers._group_actions[0].choices


def test_stale_or_wrong_manifest_lb_observation_cannot_authorize_plan(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    before = lb.validate_observed_identity(_observed_lb())
    ready = lb.desired_projection(before)
    transaction_id = "mft_" + "f" * 64
    manifest_sha = "c" * 64
    now = datetime.now(UTC)
    manifest_start = (now + timedelta(minutes=2)).isoformat(timespec="seconds").replace("+00:00", "Z")
    payload = lb._failover_attestation_payload(ready, transaction_id, manifest_sha, "initial", "pre")
    payload["observed_at"] = (now - timedelta(minutes=6)).isoformat(timespec="seconds").replace("+00:00", "Z")
    digest = str(payload["ready_mutable_sha256"])
    state_root = tmp_path / "state"
    state_root.mkdir(mode=0o700)
    path = lb.failover_attestation_path_for(transaction_id, manifest_sha, "initial", "pre", state_root)
    path.write_bytes(producer._canonical(payload) + b"\n")
    path.chmod(0o600)
    monkeypatch.setattr(producer, "STATE_ROOT", state_root)
    monkeypatch.setattr(producer, "_secure_file", lambda candidate: candidate.stat())

    with pytest.raises(RuntimeError, match="not fresh enough"):
        producer._read_lb_attestation(
            path,
            transaction_id=transaction_id,
            manifest_sha256=manifest_sha,
            phase="initial",
            observation="pre",
            manifest_start=manifest_start,
            manifest_initial_cutoff=(now + timedelta(minutes=8)).isoformat(timespec="seconds").replace("+00:00", "Z"),
            manifest_final_cutoff=(now + timedelta(minutes=15)).isoformat(timespec="seconds").replace("+00:00", "Z"),
            require_fresh=True,
        )
    with pytest.raises(RuntimeError, match="binding"):
        lb._validate_failover_attestation(
            payload,
            transaction_id=transaction_id,
            manifest_sha256="9" * 64,
            ready_sha256=digest,
            phase="initial",
            observation="pre",
        )


def test_each_failover_phase_requires_distinct_fresh_provider_pre_and_post_observations(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    observed = _observed_lb()
    observed["health_check"] = {**observed["health_check"], "path": "/api/ready"}  # type: ignore[index]
    ready = lb.validate_observed_identity(observed)
    ready_sha = lb._digest(ready)
    transaction_id = "mft_" + "f" * 64
    manifest_sha = "c" * 64
    state_dir = tmp_path / "operator-state"

    def args_for(observation: str) -> SimpleNamespace:
        return SimpleNamespace(
            state_dir=state_dir,
            expected_current_sha256=ready_sha,
            transaction_id=transaction_id,
            manifest_sha256=manifest_sha,
            phase="initial",
            observation=observation,
            confirm=lb.failover_attest_confirmation(ready_sha, transaction_id, manifest_sha, "initial", observation),
        )

    monkeypatch.setattr(lb, "_get_load_balancer", lambda: observed)
    assert lb._attest_failover(args_for("pre")) == 0
    pre = lb.failover_attestation_path_for(transaction_id, manifest_sha, "initial", "pre", state_dir)
    post = lb.failover_attestation_path_for(transaction_id, manifest_sha, "initial", "post", state_dir)
    assert pre.exists() and pre != post and not post.exists()

    observed["health_check"] = {**observed["health_check"], "path": "/api/health"}  # type: ignore[index]
    with pytest.raises(RuntimeError, match="owner-authorized /api/ready"):
        lb._attest_failover(args_for("post"))
    assert not post.exists()

    observed["health_check"] = {**observed["health_check"], "path": "/api/ready"}  # type: ignore[index]
    assert lb._attest_failover(args_for("post")) == 0
    assert post.exists()
    assert producer._digest(pre.read_bytes()) != producer._digest(post.read_bytes())


def test_post_lb_observation_must_follow_the_durable_topology_transition(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        producer,
        "_assert_context_lb_attestation",
        lambda *_args, **_kwargs: ("1" * 64, "2026-08-14T12:00:29Z"),
    )
    with pytest.raises(producer.AwaitingPostLBAttestation, match="strictly follow"):
        producer._post_transition_lb_binding(_context(), "initial", "2026-08-14T12:00:30Z")


@pytest.mark.parametrize("phase", ["initial", "replay", "closeout"])
def test_same_second_post_lb_observation_is_not_transition_authority(
    monkeypatch: pytest.MonkeyPatch, phase: str
) -> None:
    monkeypatch.setattr(
        producer,
        "_assert_context_lb_attestation",
        lambda *_args, **_kwargs: ("1" * 64, "2026-08-14T12:00:30.100000Z"),
    )
    with pytest.raises(producer.AwaitingPostLBAttestation, match="strictly follow"):
        producer._post_transition_lb_binding(_context(), phase, "2026-08-14T12:00:30.100000Z")
    assert "." in producer._now() and "." in lb._now()


def test_phase_proof_is_verified_before_immutable_write(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    calls: list[str] = []
    monkeypatch.setattr(producer, "_verify_phase_attestation", lambda *_args: calls.append("verified"))
    monkeypatch.setattr(producer, "_atomic_write", lambda *_args, **_kwargs: calls.append("written"))
    monkeypatch.setattr(producer, "_read_secure", lambda _path: b"{}\n")
    monkeypatch.setattr(producer, "_digest", lambda _value: "0" * 64)
    producer._write_once_or_verify(tmp_path / "proof.json", {"phase": "initial"}, _context(), "initial")
    assert calls[:2] == ["verified", "written"]


def test_existing_initial_proof_is_reused_after_lost_journal_ack(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    raw = (
        json.dumps(
            {
                "phase_started_at": "2026-08-14T12:00:00Z",
                "lb_post_observed_at": "2026-08-14T12:00:30Z",
            }
        ).encode()
        + b"\n"
    )
    proof = tmp_path / "initial.json"
    proof.write_bytes(raw)
    writes: list[tuple[str, str]] = []
    monkeypatch.setattr(producer, "_proof_path", lambda *_args: proof)
    monkeypatch.setattr(producer, "_read_secure", lambda path: path.read_bytes())
    monkeypatch.setattr(producer, "_verify_phase_attestation", lambda *_args: {})
    monkeypatch.setattr(producer, "_assert_current_phase_topology", lambda *_args: None)
    monkeypatch.setattr(
        producer,
        "_write_journal",
        lambda _context, status, started, _transition="": writes.append((status, started)),
    )
    monkeypatch.setattr(
        producer,
        "_signed_phase_attestation",
        lambda *_args, **_kwargs: pytest.fail("immutable proof must be reused, not regenerated"),
    )

    assert producer._complete_initial(_context(), "2026-08-14T11:59:00Z") == producer._digest(raw)
    assert writes == [("initial-proved", "2026-08-14T12:00:00Z")]


def test_lb_drain_timer_is_published_only_after_direct_drain_ack(monkeypatch: pytest.MonkeyPatch) -> None:
    class StopAfterJournal(Exception):
        pass

    calls: list[tuple[str, str]] = []

    def on_node(_context, node, action, **_kwargs):  # type: ignore[no-untyped-def]
        calls.append((action, node))

    def write(_context, status, started, _transition=""):  # type: ignore[no-untyped-def]
        calls.append((status, started))
        if status == "initial-drained":
            raise StopAfterJournal

    monkeypatch.setattr(producer, "_proof_path", lambda *_args: Path("/definitely/absent/initial.json"))
    monkeypatch.setattr(producer, "_assert_initial_window", lambda _context: None)
    monkeypatch.setattr(
        producer,
        "_assert_context_lb_attestation",
        lambda *_args, **_kwargs: ("1" * 64, "2026-08-14T12:00:00Z"),
    )
    monkeypatch.setattr(producer, "_on_node", on_node)
    monkeypatch.setattr(producer, "_now", lambda: "2026-08-14T12:00:30Z")
    monkeypatch.setattr(producer, "_write_journal", write)

    with pytest.raises(StopAfterJournal):
        producer._complete_initial(_context(), "2026-08-14T12:00:00Z")
    assert calls.index(("drain", "node02")) < calls.index(("initial-drained", "2026-08-14T12:00:30Z"))


def test_admission_recovery_rearms_maintenance_after_marker_clear_reboot(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    class StopAfterRearm(Exception):
        pass

    persistent = tmp_path / "maintenance"
    volatile = tmp_path / "volatile"
    calls: list[str] = []
    monkeypatch.setattr(producer, "PERSISTENT_MAINTENANCE", persistent)
    monkeypatch.setattr(producer, "VOLATILE_MAINTENANCE", volatile)
    monkeypatch.setattr(producer, "_node_arm", lambda _context: None)
    monkeypatch.setattr(producer, "_direct_ready_status", lambda: (_ for _ in ()).throw(RuntimeError("down")))
    monkeypatch.setattr(producer, "_read_admission_state", lambda _context: "processes-proved")
    monkeypatch.setattr(producer, "_arm_marker", lambda path: calls.append(path.name))

    def run(argv, **_kwargs):  # type: ignore[no-untyped-def]
        if argv[1:3] == ["disable", "--now"]:
            raise StopAfterRearm
        return SimpleNamespace(returncode=0, stdout="")

    monkeypatch.setattr(producer, "_run", run)
    with pytest.raises(StopAfterRearm):
        producer._node_admit(_context())
    assert calls == ["maintenance", "volatile"]


def test_drain_crash_after_worker_stop_is_recoverable_because_markers_precede_mutation(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    class StopCrash(BaseException):
        pass

    persistent = tmp_path / "maintenance"
    volatile = tmp_path / "volatile"
    runtime_guard = tmp_path / "runtime.guard"
    events: list[str] = []
    monkeypatch.setattr(producer, "PERSISTENT_MAINTENANCE", persistent)
    monkeypatch.setattr(producer, "VOLATILE_MAINTENANCE", volatile)
    monkeypatch.setattr(producer, "RUNTIME_GUARD", runtime_guard)
    monkeypatch.setattr(producer, "_node_arm", lambda _context: events.append("sentinel"))

    def arm_runtime(_context: dict[str, object]) -> None:
        runtime_guard.write_text("drain-intent\n", encoding="utf-8")
        runtime_guard.chmod(0o600)
        events.append("runtime-guard")

    def unlink_runtime(_context: dict[str, object]) -> None:
        runtime_guard.unlink(missing_ok=True)
        events.append("remove-runtime-guard")

    monkeypatch.setattr(producer, "_arm_runtime_guard", arm_runtime)
    monkeypatch.setattr(producer, "_unlink_runtime_guard", unlink_runtime)

    def arm(path: Path) -> None:
        path.write_text("maintenance\n", encoding="utf-8")
        path.chmod(0o600)
        events.append(path.name)

    monkeypatch.setattr(producer, "_arm_marker", arm)
    monkeypatch.setattr(producer, "_direct_ready_status", lambda: 503 if persistent.exists() else 200)

    def crashing_run(argv, **_kwargs):  # type: ignore[no-untyped-def]
        action = argv[1]
        if action == "is-enabled":
            return SimpleNamespace(returncode=1, stdout="")
        events.append(action + ":" + str(argv[-1]))
        if action == "stop" and argv[-1] == producer.WORKER_UNITS[-1]:
            raise StopCrash
        return SimpleNamespace(returncode=0, stdout="")

    monkeypatch.setattr(producer, "_run", crashing_run)
    with pytest.raises(StopCrash):
        producer._node_drain(_context())
    assert persistent.exists() and volatile.exists()
    first_process_mutation = next(
        index for index, event in enumerate(events) if event.startswith(("disable:", "stop:"))
    )
    assert (
        events.index("runtime-guard") < events.index("maintenance") < events.index("volatile") < first_process_mutation
    )

    enabled = False

    def recovery_run(argv, **_kwargs):  # type: ignore[no-untyped-def]
        nonlocal enabled
        if argv[1] == "enable":
            enabled = True
        if argv[1] == "is-enabled":
            return SimpleNamespace(returncode=0 if enabled else 1, stdout="")
        return SimpleNamespace(returncode=0, stdout="")

    monkeypatch.setattr(producer, "_run", recovery_run)
    monkeypatch.setattr(producer, "_assert_processes_ready", lambda: None)
    monkeypatch.setattr(producer, "_unlink_durable", lambda path: path.unlink(missing_ok=True))
    states: list[str] = []
    monkeypatch.setattr(producer, "_write_admission_state", lambda _context, state: states.append(state))
    producer._node_admit(_context())
    assert not persistent.exists() and not volatile.exists()
    assert enabled is True
    assert states == ["processes-proved", "enabled"]


def test_drain_intent_before_maintenance_is_exact_recovery_authority(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A reboot after the one-file intent cannot strand both nodes."""

    class StopCrash(BaseException):
        pass

    runtime_guard = tmp_path / "runtime.guard"
    persistent = tmp_path / "maintenance"
    volatile = tmp_path / "volatile"
    context = _context()
    monkeypatch.setattr(producer, "RUNTIME_GUARD", runtime_guard)
    monkeypatch.setattr(producer, "PERSISTENT_MAINTENANCE", persistent)
    monkeypatch.setattr(producer, "VOLATILE_MAINTENANCE", volatile)
    monkeypatch.setattr(producer, "_node_arm", lambda _context: None)

    def crash_after_intent(_context: dict[str, object]) -> None:
        runtime_guard.write_text("exact-intent\n", encoding="utf-8")
        runtime_guard.chmod(0o600)
        raise StopCrash

    monkeypatch.setattr(producer, "_arm_runtime_guard", crash_after_intent)
    with pytest.raises(StopCrash):
        producer._node_drain(context)
    assert runtime_guard.exists()
    assert not persistent.exists() and not volatile.exists()

    # Reboot leaves all statically guarded units down. The exact runtime marker
    # authorizes re-arming maintenance and replaying admission while disabled.
    monkeypatch.setattr(producer, "_read_runtime_guard", lambda _context: None)
    monkeypatch.setattr(producer, "_read_admission_state", lambda _context: "")

    api_active = False

    def direct_ready() -> int:
        if persistent.exists():
            return 503
        if api_active:
            return 200
        raise RuntimeError("down")

    monkeypatch.setattr(producer, "_direct_ready_status", direct_ready)

    def arm_marker(path: Path) -> None:
        path.write_text("maintenance\n", encoding="utf-8")
        path.chmod(0o600)

    monkeypatch.setattr(producer, "_arm_marker", arm_marker)
    monkeypatch.setattr(producer, "_unlink_runtime_guard", lambda _context: runtime_guard.unlink(missing_ok=True))
    monkeypatch.setattr(producer, "_unlink_durable", lambda path: path.unlink(missing_ok=True))
    monkeypatch.setattr(producer, "_assert_processes_ready", lambda: None)
    monkeypatch.setattr(producer, "_write_admission_state", lambda *_args: None)
    enabled = False

    def run(argv, **_kwargs):  # type: ignore[no-untyped-def]
        nonlocal api_active, enabled
        if argv[1] == "start" and argv[-1] == producer.API_UNIT:
            api_active = True
        if argv[1] == "enable":
            enabled = True
        if argv[1] == "is-enabled":
            return SimpleNamespace(returncode=0 if enabled else 1, stdout="")
        return SimpleNamespace(returncode=0, stdout="")

    monkeypatch.setattr(producer, "_run", run)
    producer._node_admit(context)
    assert enabled is True
    assert not runtime_guard.exists() and not persistent.exists() and not volatile.exists()


def test_live_failover_never_installs_or_removes_multi_file_systemd_guards() -> None:
    source = PRODUCER_PATH.read_text(encoding="utf-8")
    drain = source[source.index("def _node_drain(") : source.index("def _node_admit(")]
    admit = source[source.index("def _node_admit(") : source.index("def _node_observe(")]
    assert '["/usr/bin/systemctl", "daemon-reload"]' not in drain + admit
    assert "STATIC_GUARD_PATHS" not in drain + admit
    assert "_arm_runtime_guard(context)" in drain
    assert "_unlink_runtime_guard(context)" in admit


def test_admission_receipt_precedes_marker_clear_and_enable_last() -> None:
    source = PRODUCER_PATH.read_text(encoding="utf-8")
    admit = source[source.index("def _node_admit(") : source.index("def _node_observe(")]
    assert admit.index('_write_admission_state(context, "processes-proved")') < admit.index(
        "_unlink_durable(VOLATILE_MAINTENANCE)"
    )
    assert admit.index("_unlink_durable(PERSISTENT_MAINTENANCE)") < admit.rindex(
        '["/usr/bin/systemctl", "enable", *ALL_UNITS]'
    )
    assert admit.rindex('["/usr/bin/systemctl", "enable", *ALL_UNITS]') < admit.rindex(
        '_write_admission_state(context, "enabled")'
    )


def test_process_proof_rejects_wrong_live_worker_queue(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    proc_root = tmp_path / "proc"
    env_path = repo / ".env"
    (repo / "venv" / "bin").mkdir(parents=True)
    (repo / "venv" / "bin" / "python").write_text("", encoding="utf-8")
    env_path.write_text("FOO=bar\n", encoding="utf-8")
    pids = {unit: str(100 + index) for index, unit in enumerate(producer.ALL_UNITS)}
    queues = dict(zip(producer.WORKER_UNITS, producer.WORKER_QUEUES, strict=True))
    for unit, pid in pids.items():
        proc = proc_root / pid
        proc.mkdir(parents=True)
        queue = queues.get(unit)
        argv = [str(repo / "venv/bin/python"), "main.py"]
        if queue is not None:
            argv = [str(repo / "venv/bin/python"), "scripts/run_queue_worker.py", "--queue", queue]
        if unit == producer.WORKER_UNITS[1]:
            argv[-1] = "background"
        (proc / "cmdline").write_bytes(b"\0".join(item.encode() for item in argv) + b"\0")
        (proc / "environ").write_bytes(
            (
                "FOO=bar\0PYTHONUNBUFFERED=1\0"
                f"PATH={repo}/venv/bin:/usr/local/bin:/usr/bin:/bin\0"
                + (f"LINAS_WORKER_QUEUE={queue}\0" if queue else "")
            ).encode()
        )
        os.symlink(repo, proc / "cwd")

    def run(argv, **_kwargs):  # type: ignore[no-untyped-def]
        unit = argv[2] if len(argv) > 2 else ""
        if argv[1] == "is-active":
            return SimpleNamespace(returncode=0, stdout="")
        prop = next(item for item in argv if item.startswith("--property="))
        if prop == "--property=WorkingDirectory":
            output = str(repo)
        elif prop == "--property=EnvironmentFiles":
            output = f"{env_path} (ignore_errors=yes)"
        elif prop == "--property=NeedDaemonReload":
            output = "no"
        elif prop == "--property=MainPID":
            output = pids[unit]
        else:
            queue = queues.get(unit)
            tail = "main.py" if queue is None else f"scripts/run_queue_worker.py --queue {queue}"
            output = f"{{ path={repo}/venv/bin/python ; argv[]={repo}/venv/bin/python {tail} ; }}"
        return SimpleNamespace(returncode=0, stdout=output + "\n")

    monkeypatch.setattr(producer, "REPO_DIR", repo)
    monkeypatch.setattr(producer, "ENV_PATH", env_path)
    monkeypatch.setattr(producer, "PROC_ROOT", proc_root)
    monkeypatch.setattr(producer, "_node_id", lambda: "node01")
    monkeypatch.setattr(producer, "_assert_ha_env_contract", lambda _node: {"FOO": "bar"})
    monkeypatch.setattr(producer, "_run", run)
    with pytest.raises(RuntimeError, match="argv/queue identity"):
        producer._assert_processes_ready()

    fault_unit = producer.WORKER_UNITS[1]
    fault_pid = pids[fault_unit]
    fault_queue = queues[fault_unit]
    correct_argv = [
        str(repo / "venv/bin/python"),
        "scripts/run_queue_worker.py",
        "--queue",
        fault_queue,
    ]
    (proc_root / fault_pid / "cmdline").write_bytes(b"\0".join(item.encode() for item in correct_argv) + b"\0")
    with (proc_root / fault_pid / "environ").open("ab") as handle:
        handle.write(b"LD_AUDIT=/outside/libaudit.so\0")
    with pytest.raises(RuntimeError, match="execution-control"):
        producer._assert_processes_ready()


def test_closed_readiness_schema_rejects_arbitrary_200_and_accepts_exact_maintenance() -> None:
    with pytest.raises(RuntimeError, match="closed schema"):
        producer._assert_ready_payload({"ok": True, "role": "readiness", "checks": {}, "extra": True}, 200)
    producer._assert_ready_payload({"ok": False, "role": "readiness", "checks": {"maintenance": {"ok": False}}}, 503)


def test_collision_set_includes_every_other_meta_mutation_family() -> None:
    assert {path.name for path in producer.COLLISION_PATHS} >= {
        "bootstrap.active",
        "deploy.active",
        "deploy-node.active",
        "transaction.json",
        "runtime.guard",
        "registry-nfs-retire.active",
    }


def test_expired_post_drain_recovery_publishes_abort_instead_of_dead_ending(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    class Aborted(Exception):
        pass

    context = _context()
    journal = {
        "context": context,
        "status": "initial-drained",
        "phase_started_at": "2026-08-14T12:00:00Z",
    }
    monkeypatch.setattr(producer, "_read_journal", lambda *_args: (journal, "9" * 64))
    monkeypatch.setattr(
        producer,
        "_complete_initial",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("window expired")),
    )
    monkeypatch.setattr(producer, "_proof_path", lambda *_args: tmp_path / "absent.json")
    calls: list[str] = []

    def abort(_context, cause):  # type: ignore[no-untyped-def]
        calls.append(str(cause))
        raise Aborted

    monkeypatch.setattr(producer, "_publish_abort_and_restore", abort)
    args = SimpleNamespace(
        transaction_id=context["transaction_id"],
        expected_journal_sha256="9" * 64,
        lb_ready_attestation=None,
        confirm="RECOVER_META_FAILOVER_" + "9" * 16 + "_INITIAL-DRAINED",
    )
    with pytest.raises(Aborted):
        producer._recover(args)
    assert calls == ["window expired"]


def test_abort_authority_is_durable_before_restore_and_release(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, str]] = []
    raw = b'{"signed":"abort"}\n'
    monkeypatch.setattr(producer, "_abort_authority", lambda _context: (raw, "8" * 64))

    def on_node(_context, node, action, **_kwargs):  # type: ignore[no-untyped-def]
        calls.append((action, node))

    monkeypatch.setattr(producer, "_on_node", on_node)
    monkeypatch.setattr(producer, "_assert_current_phase_topology", lambda *_args: calls.append(("prove", "both")))
    monkeypatch.setattr(
        producer,
        "_write_journal",
        lambda _context, status, _started: calls.append((status, "journal")),
    )
    assert producer._complete_abort(_context(), "2026-08-14T12:00:00Z") == "8" * 64
    assert calls == [
        ("admit", "node02"),
        ("admit", "node01"),
        ("prove", "both"),
        ("abort-release", "node02"),
        ("abort-release", "node01"),
        ("aborted", "journal"),
    ]
    assert (
        "abort-release"
        in producer.build_parser()._subparsers._group_actions[0].choices["node-phase"]._actions[1].choices
    )


@pytest.mark.parametrize("key", ["PYTHONPATH", "PYTHONHOME", "LD_PRELOAD", "LD_AUDIT", "BASH_ENV", "NODE_OPTIONS"])
def test_controlled_failover_rejects_code_loader_environment_controls(
    key: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(producer, "_read_secure", lambda _path: f"SAFE=value\n{key}=/outside\n".encode())
    with pytest.raises(RuntimeError, match="forbidden code-loader control"):
        producer._canonical_env_values()
