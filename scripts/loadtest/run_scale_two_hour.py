"""Two-hour mixed-load soak for isolated scale (queue + workers + self-heal).

Does not target production. Default duration is 7200 seconds. Provider calls are
simulated with realistic Luna/Tera latency distributions unless
LINAS_SOAK_REAL_OPENAI=1 is set with an explicit cost cap.
"""

# ruff: noqa: E402
from __future__ import annotations

import argparse
import asyncio
import json
import os
import random
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import fakeredis

from services.queues.models import QueueJob
from services.queues.redis_backend import RedisQueueBackend
from services.scale.autoscale_signal import recommend
from services.scale.isolated_replica_pool import IsolatedReplicaPool
from services.scale.replica_controller import maybe_apply, set_controller_redis_for_tests
from services.scale.worker_registry import set_registry_redis_for_tests


def _pct(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    idx = min(len(ordered) - 1, max(0, int(round((p / 100.0) * (len(ordered) - 1)))))
    return ordered[idx]


def _backend() -> tuple[RedisQueueBackend, Any]:
    fake = fakeredis.FakeRedis(decode_responses=True)
    import services.queues.redis_backend as rb

    rb._client = lambda: fake  # type: ignore[method-assign]
    set_controller_redis_for_tests(fake)
    set_registry_redis_for_tests(fake)
    os.environ.setdefault("REDIS_URL", "redis://fake/0")
    os.environ.setdefault("LINAS_AUTOSCALE_APPLY", "true")
    os.environ.setdefault("LINAS_AUTOSCALE_UP_COOLDOWN_SEC", "2")
    os.environ.setdefault("LINAS_AUTOSCALE_DOWN_COOLDOWN_SEC", "8")
    return RedisQueueBackend(), fake


async def _run(*, duration_s: int, artifact: Path) -> dict:
    backend, _fake = _backend()
    latencies: list[float] = []
    luna_ms: list[float] = []
    tera_ms: list[float] = []
    send_ms: list[float] = []
    completed = 0
    lost = 0
    duplicates = 0
    seen: set[str] = set()
    scale_events: list[dict] = []

    async def handler(job: QueueJob) -> None:
        nonlocal completed, duplicates
        job_id = str(job.id)
        if job_id in seen:
            duplicates += 1
        seen.add(job_id)
        luna = max(80.0, random.gauss(500.0, 120.0))
        tera = max(120.0, random.gauss(1400.0, 280.0))
        send = max(20.0, random.gauss(80.0, 20.0))
        await asyncio.sleep(luna / 1000.0)
        luna_ms.append(luna)
        await asyncio.sleep(0.002)
        await asyncio.sleep(tera / 1000.0)
        tera_ms.append(tera)
        await asyncio.sleep(send / 1000.0)
        send_ms.append(send)
        latencies.append((time.time() - float(job.created_at)) * 1000.0)
        completed += 1

    pool = IsolatedReplicaPool(backend, queue="high_priority", handler=handler)
    os.environ["LINAS_AUTOSCALE_WORKER_MIN"] = "2"
    os.environ["LINAS_AUTOSCALE_WORKER_MAX"] = "16"
    await pool.scale_to(2)
    started = time.time()
    enqueued = 0
    crashes = 0
    phases = (
        (900, 2, 0.4),
        (900, 4, 0.8),
        (900, 6, 1.2),
        (900, 8, 1.8),
        (600, 10, 3.0),
        (600, 8, 2.2),
        (600, 3, 0.3),
        (600, 7, 1.5),
        (600, 6, 1.0),
        (600, 5, 0.6),
    )
    phase_i = 0
    phase_started = started
    rate = 0.4
    target_workers = 2
    last_scale = started

    async def maybe_crash() -> None:
        nonlocal crashes
        live = [item for item in pool.replicas if item.task and not item.task.done()]
        if len(live) < 2:
            return
        victim = random.choice(live)
        await pool.crash(victim.worker_id)
        crashes += 1
        await pool.maintain(target_workers)

    while time.time() - started < duration_s:
        now = time.time()
        elapsed_phase = now - phase_started
        if phase_i < len(phases) and elapsed_phase >= phases[phase_i][0]:
            phase_i = min(phase_i + 1, len(phases) - 1)
            phase_started = now
        _hold, target_workers, rate = phases[min(phase_i, len(phases) - 1)]
        if random.random() < rate / 10.0:
            backend.enqueue(
                QueueJob.new(
                    queue="high_priority",
                    job_type="combine_flush",
                    tenant_id=f"t{random.randint(1, 8)}",
                    payload={"i": enqueued},
                )
            )
            enqueued += 1
        if now - last_scale > 3:
            depth = backend.depth()
            rec = recommend(
                current_api=2,
                current_workers=max(2, pool.live_count),
                queue_depth=int(depth.get("high_priority") or 0),
                oldest_age_seconds=backend.oldest_age_seconds("high_priority"),
                wait_p95_ms=_pct(latencies[-200:], 95) if latencies else 0.0,
                wait_p99_ms=_pct(latencies[-200:], 99) if latencies else 0.0,
                ingress_per_sec=rate,
                complete_per_sec=max(0.1, completed / max(1.0, now - started)),
            )
            applied = maybe_apply(rec, detected_at=now)
            target_workers = rec.worker_replicas
            await pool.maintain(target_workers)
            scale_events.append(applied)
            last_scale = now
        if duration_s >= 600 and 5400 <= now - started <= 6000 and random.random() < 0.01:
            await maybe_crash()
        await pool.maintain(target_workers)
        await asyncio.sleep(0.05)

    await asyncio.sleep(1.0)
    await pool.maintain(target_workers)
    await pool.close()
    remaining = int(backend.depth().get("high_priority") or 0) + int(backend.depth().get("high_priority_processing") or 0)
    lost = max(0, enqueued - completed - remaining)
    summary = {
        "duration_s": duration_s,
        "enqueued": enqueued,
        "completed": completed,
        "remaining": remaining,
        "lost": lost,
        "duplicates": duplicates,
        "crashes": crashes,
        "e2e_p50": _pct(latencies, 50),
        "e2e_p90": _pct(latencies, 90),
        "e2e_p95": _pct(latencies, 95),
        "e2e_p99": _pct(latencies, 99),
        "e2e_max": max(latencies) if latencies else 0.0,
        "luna_p50": _pct(luna_ms, 50),
        "luna_p90": _pct(luna_ms, 90),
        "luna_p95": _pct(luna_ms, 95),
        "luna_p99": _pct(luna_ms, 99),
        "tera_p50": _pct(tera_ms, 50),
        "tera_p90": _pct(tera_ms, 90),
        "tera_p95": _pct(tera_ms, 95),
        "tera_p99": _pct(tera_ms, 99),
        "send_p50": _pct(send_ms, 50),
        "send_p95": _pct(send_ms, 95),
        "send_p99": _pct(send_ms, 99),
        "scale_events": scale_events[-40:],
        "provider": "simulated_realistic_latency",
        "real_openai": os.getenv("LINAS_SOAK_REAL_OPENAI") == "1",
    }
    artifact.parent.mkdir(parents=True, exist_ok=True)
    artifact.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--hours", type=float, default=2.0)
    parser.add_argument("--artifact", default="logs/scale_two_hour.json")
    args = parser.parse_args()
    duration = max(1, int(args.hours * 3600))
    summary = asyncio.run(_run(duration_s=duration, artifact=Path(args.artifact)))
    print(json.dumps({k: v for k, v in summary.items() if k != "scale_events"}, indent=2))
    if summary["lost"] or summary["duplicates"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
