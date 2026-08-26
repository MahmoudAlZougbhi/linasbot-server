"""Isolated omnichannel live certification against local Docker Postgres/Redis.

Requires LINAS_OMNI_CERT_STAGING=1. Never targets production hosts or providers.
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.loadtest.omnichannel_cert_guards import (  # noqa: E402
    TEST_TENANT_PREFIX,
    assert_staging_cert_allowed,
    should_abort,
)
from scripts.loadtest.omnichannel_cert_runtime import (  # noqa: E402
    artifact_dir,
    mix_event,
    percentile,
    post_inbound,
    write_checkpoint,
)

COMPOSE = ROOT / "docker-compose.omnichannel-cert.yml"
TENANT = f"{TEST_TENANT_PREFIX}local"
PG_URL = "postgresql://omnicert:omnicert@127.0.0.1:55432/omnicert"
REDIS_URL = "redis://127.0.0.1:56379/0"
GATEWAY = "http://127.0.0.1:18080/"


def _run(cmd: list[str], *, env: dict[str, str] | None = None) -> None:
    subprocess.run(cmd, check=True, cwd=str(ROOT), env=env)


def _compose(*args: str) -> list[str]:
    return ["docker", "compose", "-f", str(COMPOSE), "-p", "omnichannel-cert", *args]


def _prepare_env() -> dict[str, str]:
    env = os.environ.copy()
    env["LINAS_OMNI_CERT_STAGING"] = "1"
    env["LINAS_OMNI_CERT_TENANT"] = TENANT
    env["LINAS_WHATSAPP_DATABASE_URL"] = PG_URL
    env["LINAS_WHATSAPP_ALLOW_SQLITE"] = "false"
    env["REDIS_URL"] = REDIS_URL
    env["LINAS_REQUIRE_REDIS"] = "true"
    env["LINAS_PROVIDER_LIMIT_PREFIX"] = "omni-cert:prov"
    env["LINAS_OPENAI_RPM"] = "20000"
    env["LINAS_OPENAI_INFLIGHT"] = "256"
    env["LINAS_META_RPM"] = "20000"
    env["LINAS_META_INFLIGHT"] = "256"
    env["LINAS_TENANT_PROVIDER_INFLIGHT"] = "64"
    env["LINAS_QUEUE_TENANT_INFLIGHT"] = "64"
    env["LINAS_QUEUE_CONCURRENCY_HIGH"] = "16"
    env["LINAS_QUEUE_CONCURRENCY_BACKGROUND"] = "8"
    env["PYTHONPATH"] = str(ROOT)
    env["PYTHONUNBUFFERED"] = "1"
    return env


def _wait_tcp(host: str, port: int, timeout: float = 40.0) -> None:
    import socket

    deadline = time.time() + timeout
    while time.time() < deadline:
        with socket.socket() as sock:
            sock.settimeout(0.4)
            if sock.connect_ex((host, port)) == 0:
                return
        time.sleep(0.2)
    raise TimeoutError(f"not_ready:{host}:{port}")


def _create_schema(env: dict[str, str]) -> None:
    code = """
from db.models.omnichannel import OmnichannelInboundEvent, OmnichannelOutboundOutbox
from db.session import get_engine, reset_engine_for_tests
reset_engine_for_tests()
engine = get_engine(require=True)
OmnichannelInboundEvent.__table__.create(engine, checkfirst=True)
OmnichannelOutboundOutbox.__table__.create(engine, checkfirst=True)
print("schema_ok")
"""
    subprocess.run([sys.executable, "-c", code], check=True, cwd=str(ROOT), env=env)


def _start_worker(env: dict[str, str], queue: str) -> subprocess.Popen:
    wenv = env.copy()
    wenv["LINAS_WORKER_QUEUE"] = queue
    log_path = artifact_dir() / f"worker-{queue}.log"
    log_file = log_path.open("a", encoding="utf-8")
    return subprocess.Popen(
        [sys.executable, "scripts/loadtest/omnichannel_cert_worker.py"],
        cwd=str(ROOT),
        env=wenv,
        stdout=log_file,
        stderr=log_file,
    )


def _start_gateway(env: dict[str, str]) -> subprocess.Popen:
    gateway = env.copy()
    gateway["LINAS_OMNI_CERT_BIND"] = "127.0.0.1"
    gateway["LINAS_OMNI_CERT_PORT"] = "18080"
    return subprocess.Popen(
        [sys.executable, "scripts/loadtest/omnichannel_cert_gateway.py"],
        cwd=str(ROOT),
        env=gateway,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def _start_stack(env: dict[str, str]) -> dict:
    workers: list[tuple[str, subprocess.Popen]] = []
    for queue in ("high_priority", "background"):
        for _ in range(2):
            workers.append((queue, _start_worker(env, queue)))
    return {"gateway": _start_gateway(env), "workers": workers}


def _respawn(stack: dict, env: dict[str, str]) -> None:
    if stack["gateway"].poll() is not None:
        stack["gateway"] = _start_gateway(env)
    stack["workers"] = [
        (queue, proc if proc.poll() is None else _start_worker(env, queue)) for queue, proc in stack["workers"]
    ]


def _stack_procs(stack: dict) -> list[subprocess.Popen]:
    return [stack["gateway"]] + [proc for _queue, proc in stack["workers"]]


def _stop_procs(procs: list[subprocess.Popen]) -> None:
    for proc in procs:
        if proc.poll() is None:
            proc.send_signal(signal.SIGTERM)
    deadline = time.time() + 8
    for proc in procs:
        if time.time() > deadline:
            break
        try:
            proc.wait(timeout=max(0.1, deadline - time.time()))
        except subprocess.TimeoutExpired:
            proc.kill()


def _ledger_counts(env: dict[str, str]) -> dict[str, int]:
    code = """
from sqlalchemy import text
from db.session import get_engine, reset_engine_for_tests
reset_engine_for_tests()
eng = get_engine(require=True)
with eng.connect() as c:
    inn = int(c.execute(text("select count(*) from omnichannel_inbound_events")).scalar() or 0)
    out = int(c.execute(text("select count(*) from omnichannel_outbound_outbox")).scalar() or 0)
print(inn, out)
"""
    last_error = None
    for _attempt in range(8):
        try:
            result = subprocess.check_output(
                [sys.executable, "-c", code], cwd=str(ROOT), env=env, text=True, stderr=subprocess.STDOUT
            )
            inbound, outbound = result.strip().split()[-2:]
            return {"inbound": int(inbound), "outbound": int(outbound)}
        except (subprocess.CalledProcessError, ValueError) as exc:
            last_error = exc
            time.sleep(0.4)
    raise RuntimeError(f"ledger_counts_failed:{last_error}")


def run_phase(
    *,
    name: str,
    seconds: int,
    per_minute: int,
    gateway: str,
    env: dict[str, str],
    stack: dict | None = None,
) -> dict:
    latencies: list[float] = []
    accepted = 0
    duplicates = 0
    errors = 0
    seq = 0
    started = time.time()
    deadline = started + seconds
    interval = 60.0 / max(1, per_minute)
    before = _ledger_counts(env)
    last_ckpt = started
    abort = None
    while time.time() < deadline:
        if stack is not None:
            _respawn(stack, env)
        replay = seq > 0 and seq % 10 == 0
        event = mix_event(seq=(seq - 1) if replay else seq, tenant_id=TENANT, nonce=name)
        seq += 1
        status, ms, created = post_inbound(gateway, event)
        latencies.append(ms)
        if status == 200 and created:
            accepted += 1
        elif status == 200:
            duplicates += 1
        else:
            errors += 1
        if time.time() - last_ckpt >= 30:
            counts = _ledger_counts(env)
            lost_now = max(0, accepted - max(0, counts["inbound"] - before["inbound"]))
            abort = should_abort(lost=lost_now, errors=errors, accepted=max(1, accepted + duplicates))
            write_checkpoint(
                f"partial-{name}",
                {
                    "phase": name,
                    "elapsed_s": int(time.time() - started),
                    "posted": seq,
                    "accepted": accepted,
                    "lost": lost_now,
                    "inbound_rows": counts["inbound"],
                    "outbound_rows": counts["outbound"],
                    "ack_p95_ms": percentile(latencies, 95),
                },
            )
            print(
                json.dumps(
                    {
                        "phase": name,
                        "elapsed_s": int(time.time() - started),
                        "posted": seq,
                        "accepted": accepted,
                        "lost": lost_now,
                        "ack_p95_ms": percentile(latencies, 95),
                    }
                ),
                flush=True,
            )
            last_ckpt = time.time()
            if abort:
                break
        sleep_for = interval - (ms / 1000.0)
        if sleep_for > 0:
            time.sleep(min(sleep_for, interval))
    counts = _ledger_counts(env)
    inbound_delta = max(0, counts["inbound"] - before["inbound"])
    lost = max(0, accepted - inbound_delta)
    abort = abort or should_abort(lost=lost, errors=errors, accepted=max(1, accepted + duplicates))
    return {
        "name": name,
        "seconds": seconds,
        "target_per_minute": per_minute,
        "posted": seq,
        "accepted": accepted,
        "duplicates": duplicates,
        "errors": errors,
        "lost": lost,
        "inbound_delta": inbound_delta,
        "inbound_rows": counts["inbound"],
        "outbound_rows": counts["outbound"],
        "ack_p50_ms": percentile(latencies, 50),
        "ack_p95_ms": percentile(latencies, 95),
        "ack_p99_ms": percentile(latencies, 99),
        "abort": abort,
        "passed": abort is None and lost == 0,
    }


def _replace_workers(stack: dict, env: dict[str, str], *, fault: str = "") -> None:
    wenv = env.copy()
    if fault:
        wenv["LINAS_OMNI_CERT_FAULT"] = fault
    for _queue, proc in stack["workers"]:
        if proc.poll() is None:
            proc.send_signal(signal.SIGTERM)
    stack["workers"] = [
        (queue, _start_worker(wenv, queue)) for queue in ("high_priority", "background") for _ in range(2)
    ]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--compressed", action="store_true")
    parser.add_argument("--hour", action="store_true")
    parser.add_argument("--burst", action="store_true")
    parser.add_argument("--faults", action="store_true")
    parser.add_argument("--soak-segment-seconds", type=int, default=0)
    parser.add_argument("--keep-stack", action="store_true")
    args = parser.parse_args()
    os.environ["LINAS_OMNI_CERT_STAGING"] = "1"
    duration = max(30, args.soak_segment_seconds or (3600 if args.hour else 45))
    if args.hour:
        duration += 600 if args.burst else 0
        duration += 180
    assert_staging_cert_allowed(
        target_url=GATEWAY,
        tenant_id=TENANT,
        events_per_minute=1900 if not args.burst else 3800,
        duration_seconds=duration,
        estimated_openai_usd=0.0,
    )
    env = _prepare_env()
    _run(_compose("up", "-d", "--wait"))
    _wait_tcp("127.0.0.1", 55432)
    _wait_tcp("127.0.0.1", 56379)
    _create_schema(env)
    stack = _start_stack(env)
    inbound = GATEWAY + "inbound"
    try:
        _wait_tcp("127.0.0.1", 18080)
        phases = []
        if args.compressed or not (args.hour or args.soak_segment_seconds):
            phases.append(run_phase(name="warmup", seconds=8, per_minute=190, gateway=inbound, env=env, stack=stack))
            phases.append(
                run_phase(name="compressed_mix", seconds=20, per_minute=380, gateway=inbound, env=env, stack=stack)
            )
        if args.hour:
            phases.append(
                run_phase(name="hour_1900", seconds=3600, per_minute=1900, gateway=inbound, env=env, stack=stack)
            )
        if args.burst:
            phases.append(
                run_phase(name="burst_2x", seconds=600, per_minute=3800, gateway=inbound, env=env, stack=stack)
            )
        if args.soak_segment_seconds:
            phases.append(
                run_phase(
                    name="soak_segment",
                    seconds=int(args.soak_segment_seconds),
                    per_minute=1900,
                    gateway=inbound,
                    env=env,
                    stack=stack,
                )
            )
        if args.faults or args.compressed or args.hour:
            fault_rate = 1900 if args.hour else 190
            fault_s = 20 if args.hour else 8
            _queue, proc = stack["workers"][0]
            if proc.poll() is None:
                proc.send_signal(signal.SIGTERM)
            time.sleep(1)
            _respawn(stack, env)
            phases.append(
                run_phase(
                    name="after_worker_kill",
                    seconds=fault_s,
                    per_minute=fault_rate,
                    gateway=inbound,
                    env=env,
                    stack=stack,
                )
            )
            stack["gateway"].send_signal(signal.SIGTERM)
            time.sleep(1)
            _respawn(stack, env)
            _wait_tcp("127.0.0.1", 18080)
            phases.append(
                run_phase(
                    name="after_api_kill",
                    seconds=fault_s,
                    per_minute=fault_rate,
                    gateway=inbound,
                    env=env,
                    stack=stack,
                )
            )
            _run(_compose("restart", "redis"))
            _wait_tcp("127.0.0.1", 56379)
            time.sleep(1)
            _respawn(stack, env)
            phases.append(
                run_phase(
                    name="after_redis_restart",
                    seconds=fault_s,
                    per_minute=fault_rate,
                    gateway=inbound,
                    env=env,
                    stack=stack,
                )
            )
            subprocess.run(_compose("pause", "postgres"), check=False, cwd=str(ROOT))
            time.sleep(2)
            subprocess.run(_compose("unpause", "postgres"), check=False, cwd=str(ROOT))
            phases.append(
                run_phase(
                    name="after_db_interrupt",
                    seconds=fault_s,
                    per_minute=fault_rate,
                    gateway=inbound,
                    env=env,
                    stack=stack,
                )
            )
            _replace_workers(stack, env, fault="429")
            phases.append(
                run_phase(
                    name="provider_429",
                    seconds=max(8, fault_s // 2),
                    per_minute=fault_rate,
                    gateway=inbound,
                    env=env,
                    stack=stack,
                )
            )
            _replace_workers(stack, env, fault="5xx")
            phases.append(
                run_phase(
                    name="provider_5xx",
                    seconds=max(8, fault_s // 2),
                    per_minute=fault_rate,
                    gateway=inbound,
                    env=env,
                    stack=stack,
                )
            )
            _replace_workers(stack, env)
        report = {
            "ok": all(phase.get("passed") for phase in phases),
            "tenant_prefix": TEST_TENANT_PREFIX,
            "staging": "docker-compose.omnichannel-cert.yml",
            "simulated_ai": True,
            "phases": phases,
        }
        if args.hour:
            report_name = "live-hour"
        elif args.soak_segment_seconds:
            report_name = "live-soak-segment"
        else:
            report_name = "live-compressed"
        path = write_checkpoint(report_name, report)
        print(json.dumps({"report": str(path), **report}, indent=2, sort_keys=True)[:8000], flush=True)
        return 0 if report["ok"] else 1
    finally:
        _stop_procs(_stack_procs(stack))
        if not args.keep_stack:
            subprocess.run(_compose("down", "-v"), check=False, cwd=str(ROOT))


if __name__ == "__main__":
    raise SystemExit(main())
