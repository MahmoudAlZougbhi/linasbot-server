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


def _start_procs(env: dict[str, str]) -> list[subprocess.Popen]:
    procs: list[subprocess.Popen] = []
    gateway = env.copy()
    gateway["LINAS_OMNI_CERT_BIND"] = "127.0.0.1"
    gateway["LINAS_OMNI_CERT_PORT"] = "18080"
    procs.append(
        subprocess.Popen(
            [sys.executable, "scripts/loadtest/omnichannel_cert_gateway.py"],
            cwd=str(ROOT),
            env=gateway,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    )
    for queue in ("high_priority", "background"):
        procs.append(_start_worker(env, queue))
    return procs


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


def run_phase(*, name: str, seconds: int, per_minute: int, gateway: str, env: dict[str, str]) -> dict:
    latencies: list[float] = []
    accepted = 0
    duplicates = 0
    errors = 0
    seq = 0
    deadline = time.time() + seconds
    interval = 60.0 / max(1, per_minute)
    before = _ledger_counts(env)
    while time.time() < deadline:
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
        sleep_for = interval - (ms / 1000.0)
        if sleep_for > 0:
            time.sleep(min(sleep_for, interval))
    counts = _ledger_counts(env)
    inbound_delta = max(0, counts["inbound"] - before["inbound"])
    lost = max(0, accepted - inbound_delta)
    abort = should_abort(lost=lost, errors=errors, accepted=max(1, accepted + duplicates))
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
    assert_staging_cert_allowed(
        target_url=GATEWAY,
        tenant_id=TENANT,
        events_per_minute=1900 if not args.burst else 3800,
        duration_seconds=max(30, args.soak_segment_seconds or (3600 if args.hour else 45)),
        estimated_openai_usd=0.0,
    )
    env = _prepare_env()
    _run(_compose("up", "-d", "--wait"))
    _wait_tcp("127.0.0.1", 55432)
    _wait_tcp("127.0.0.1", 56379)
    _create_schema(env)
    procs = _start_procs(env)
    try:
        _wait_tcp("127.0.0.1", 18080)
        phases = []
        if args.compressed or not (args.hour or args.soak_segment_seconds):
            phases.append(run_phase(name="warmup", seconds=8, per_minute=190, gateway=GATEWAY + "inbound", env=env))
            phases.append(run_phase(name="compressed_mix", seconds=20, per_minute=380, gateway=GATEWAY + "inbound", env=env))
        if args.hour:
            phases.append(run_phase(name="hour_1900", seconds=3600, per_minute=1900, gateway=GATEWAY + "inbound", env=env))
        if args.burst:
            phases.append(run_phase(name="burst_2x", seconds=600, per_minute=3800, gateway=GATEWAY + "inbound", env=env))
        if args.soak_segment_seconds:
            phases.append(
                run_phase(
                    name="soak_segment",
                    seconds=int(args.soak_segment_seconds),
                    per_minute=1900,
                    gateway=GATEWAY + "inbound",
                    env=env,
                )
            )
        if args.faults or args.compressed:
            workers = [proc for proc in procs[1:]]
            if workers:
                workers[0].send_signal(signal.SIGTERM)
                time.sleep(2)
                procs.append(_start_worker(env, "high_priority"))
            phases.append(run_phase(name="after_worker_kill", seconds=8, per_minute=190, gateway=GATEWAY + "inbound", env=env))
            gateway_proc = procs[0]
            gateway_proc.send_signal(signal.SIGTERM)
            time.sleep(1)
            genv = env.copy()
            genv["LINAS_OMNI_CERT_BIND"] = "127.0.0.1"
            genv["LINAS_OMNI_CERT_PORT"] = "18080"
            procs.append(
                subprocess.Popen(
                    [sys.executable, "scripts/loadtest/omnichannel_cert_gateway.py"],
                    cwd=str(ROOT),
                    env=genv,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            )
            _wait_tcp("127.0.0.1", 18080)
            phases.append(run_phase(name="after_api_kill", seconds=8, per_minute=190, gateway=GATEWAY + "inbound", env=env))
            _run(_compose("restart", "redis"))
            _wait_tcp("127.0.0.1", 56379)
            for queue in ("high_priority", "background"):
                procs.append(_start_worker(env, queue))
            phases.append(run_phase(name="after_redis_restart", seconds=8, per_minute=190, gateway=GATEWAY + "inbound", env=env))
            subprocess.run(_compose("pause", "postgres"), check=False, cwd=str(ROOT))
            time.sleep(3)
            subprocess.run(_compose("unpause", "postgres"), check=False, cwd=str(ROOT))
            phases.append(run_phase(name="after_db_interrupt", seconds=8, per_minute=190, gateway=GATEWAY + "inbound", env=env))
        report = {
            "ok": all(phase.get("passed") for phase in phases),
            "tenant_prefix": TEST_TENANT_PREFIX,
            "staging": "docker-compose.omnichannel-cert.yml",
            "simulated_ai": True,
            "phases": phases,
        }
        path = write_checkpoint("live-compressed" if args.compressed or not args.hour else "live-hour", report)
        print(json.dumps({"report": str(path), **report}, indent=2, sort_keys=True)[:8000])
        return 0 if report["ok"] else 1
    finally:
        _stop_procs(procs)
        if not args.keep_stack:
            subprocess.run(_compose("down", "-v"), check=False, cwd=str(ROOT))


if __name__ == "__main__":
    raise SystemExit(main())
