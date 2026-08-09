#!/usr/bin/env python3
"""Representative load simulation for Phase 2 Wave 8 (local/CI).

Models 100 and 1,000 tenant concurrency envelopes without claiming production
Redis readiness. Emits machine-readable JSON.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


@dataclass
class ScenarioResult:
    name: str
    tenants: int
    operations: int
    p50_ms: float
    p95_ms: float
    p99_ms: float
    error_rate: float
    ops_per_sec: float


def _percentile(sorted_vals: list[float], pct: float) -> float:
    if not sorted_vals:
        return 0.0
    idx = min(len(sorted_vals) - 1, max(0, int(round((pct / 100.0) * (len(sorted_vals) - 1)))))
    return sorted_vals[idx]


def _work(tenant_id: int) -> float:
    """CPU-light stand-in for entitlement + ledger + capability checks."""
    start = time.perf_counter()
    from services.integration_capabilities import META_CAPABILITIES
    from services.plan_economics import recommend_allowance

    allowance = recommend_allowance("starter" if tenant_id % 2 == 0 else "pro")
    _ = allowance.included_credits + len(META_CAPABILITIES) + tenant_id
    return (time.perf_counter() - start) * 1000.0


def run_scenario(name: str, tenants: int, ops_per_tenant: int, workers: int) -> ScenarioResult:
    latencies: list[float] = []
    errors = 0
    total = tenants * ops_per_tenant
    started = time.perf_counter()
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [
            pool.submit(_work, t)
            for t in range(tenants)
            for _ in range(ops_per_tenant)
        ]
        for fut in as_completed(futures):
            try:
                latencies.append(fut.result())
            except Exception:
                errors += 1
    elapsed = max(0.001, time.perf_counter() - started)
    latencies.sort()
    return ScenarioResult(
        name=name,
        tenants=tenants,
        operations=total,
        p50_ms=round(_percentile(latencies, 50), 3),
        p95_ms=round(_percentile(latencies, 95), 3),
        p99_ms=round(_percentile(latencies, 99), 3),
        error_rate=round(errors / total, 4) if total else 0.0,
        ops_per_sec=round(total / elapsed, 2),
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    scenarios = [
        run_scenario("100_tenants_burst", tenants=100, ops_per_tenant=5, workers=32),
        run_scenario("1000_tenants_sustained", tenants=1000, ops_per_tenant=2, workers=64),
    ]
    from services.queues.config import redis_url

    redis_configured = bool(redis_url())
    report: dict[str, Any] = {
        "report_version": "phase2-infra-load-v2",
        "queue_backend": "redis" if redis_configured else "in_process",
        "production_ready": redis_configured,
        "note": (
            "Entitlement/capability/economics path simulation. "
            "Does not prove Meta webhook or OpenAI rate-limit headroom. "
            "Durable Redis workers are implemented; activate with REDIS_URL + "
            "LINAS_REQUIRE_REDIS=true and verify /api/queue/ready before claiming scale-ready."
        ),
        "scenarios": [asdict(s) for s in scenarios],
        "answer_1000_businesses": (
            "Read-path entitlement checks scale in-process. Production Meta DM + "
            "creative/video require Redis-backed workers (high_priority vs expensive "
            "separation), provider throttles, and measured p95 under real traffic."
        ),
    }
    payload = json.dumps(report, indent=2)
    if args.json:
        print(payload)
    else:
        print(payload)
        for s in scenarios:
            print(
                f"{s.name}: p50={s.p50_ms}ms p95={s.p95_ms}ms p99={s.p99_ms}ms "
                f"err={s.error_rate} ops/s={s.ops_per_sec}",
                file=__import__("sys").stderr,
                flush=True,
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
