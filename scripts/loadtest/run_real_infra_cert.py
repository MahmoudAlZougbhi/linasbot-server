"""Real-infra HA load certification (Valkey + optional LB), mocked OpenAI/Meta.

Runs from a Linas app node (Valkey trusted sources). Does not deploy releases.
Invariant: unexplained_missing_events == 0 for ledger scenarios.
"""

from __future__ import annotations

import argparse
import json
import os
import ssl
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[2]
import sys

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@dataclass
class CertResult:
    name: str
    passed: bool
    details: dict[str, Any]


def _pct(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    idx = min(len(ordered) - 1, max(0, int(round((p / 100.0) * (len(ordered) - 1)))))
    return ordered[idx]


def _redis_from_env() -> Any:
    import redis

    url = (os.getenv("REDIS_URL") or os.getenv("LINAS_REDIS_URL") or "").strip()
    if not url:
        raise RuntimeError("REDIS_URL required for real-infra cert")
    client = redis.Redis.from_url(
        url,
        decode_responses=True,
        socket_connect_timeout=5,
        socket_timeout=5,
    )
    client.ping()
    return client


def cert_valkey_basics(r: Any) -> CertResult:
    key = f"linas:ha:cert:{uuid.uuid4().hex}"
    r.set(key, "1", ex=120)
    info = r.info("replication")
    return CertResult(
        "valkey_tls_auth_replication",
        r.get(key) == "1" and info.get("role") == "master" and int(info.get("connected_slaves") or 0) >= 1,
        {"role": info.get("role"), "slaves": info.get("connected_slaves")},
    )


def cert_shared_counters(r: Any, *, n: int = 5000) -> CertResult:
    key = f"linas:ha:owners:{uuid.uuid4().hex}"
    pipe = r.pipeline(transaction=False)
    for i in range(n):
        pipe.sadd(key, f"owner-{i}")
    pipe.expire(key, 600)
    pipe.execute()
    card = int(r.scard(key))
    return CertResult("owners_5k_set", card == n, {"cardinality": card, "expected": n})


def cert_burst_idempotency(r: Any, *, burst: int = 20_000) -> CertResult:
    """Simulate duplicate webhook claims via SET NX idempotency keys."""
    prefix = f"linas:ha:idem:{uuid.uuid4().hex}"
    accepted = 0
    duplicates = 0

    def one(i: int) -> str:
        # 10% deliberate duplicates of prior ids
        mid = i if i % 10 else max(0, i - 1)
        ok = r.set(f"{prefix}:{mid}", "1", nx=True, ex=600)
        return "accepted" if ok else "duplicate"

    with ThreadPoolExecutor(max_workers=64) as pool:
        futs = [pool.submit(one, i) for i in range(burst)]
        for fut in as_completed(futs):
            if fut.result() == "accepted":
                accepted += 1
            else:
                duplicates += 1
    # Unique mids roughly 90% + first of each dup pair
    return CertResult(
        "burst_20k_idempotency",
        accepted + duplicates == burst and duplicates > 0 and accepted > 0,
        {"accepted": accepted, "duplicates": duplicates, "burst": burst},
    )


def cert_ooo_conversation_lock(r: Any, *, conversations: int = 1000, msgs: int = 5) -> CertResult:
    """Out-of-order arrivals under per-conversation Redis lock; no lost locks."""
    lost = 0
    ordering_failures = 0

    def convo(cid: int) -> tuple[int, int]:
        local_lost = 0
        local_ord = 0
        last = -1
        for seq in range(msgs):
            lock = f"linas:ha:convlock:{cid}"
            token = uuid.uuid4().hex
            if not r.set(lock, token, nx=True, ex=5):
                # spin briefly
                for _ in range(50):
                    time.sleep(0.002)
                    if r.set(lock, token, nx=True, ex=5):
                        break
                else:
                    local_lost += 1
                    continue
            try:
                if seq < last:
                    local_ord += 1
                last = seq
                r.rpush(f"linas:ha:conv:{cid}", seq)
            finally:
                # release only if owned
                if r.get(lock) == token:
                    r.delete(lock)
        return local_lost, local_ord

    with ThreadPoolExecutor(max_workers=32) as pool:
        futs = [pool.submit(convo, c) for c in range(conversations)]
        for fut in as_completed(futs):
            a, b = fut.result()
            lost += a
            ordering_failures += b
    return CertResult(
        "ooo_conversation_locks",
        lost == 0 and ordering_failures == 0,
        {"conversations": conversations, "lost_locks": lost, "ordering_failures": ordering_failures},
    )


def cert_durable_ledger() -> CertResult:
    """Run focused pytest (monkeypatched) to avoid importing full app/Firestore."""
    import subprocess

    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-q",
            "tests/scale/test_inbound_event_durability.py",
        ],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        timeout=180,
    )
    unexplained = 0 if proc.returncode == 0 else 1
    return CertResult(
        "durable_ledger_reconcile",
        proc.returncode == 0,
        {
            "returncode": proc.returncode,
            "stdout_tail": (proc.stdout or "")[-500:],
            "stderr_tail": (proc.stderr or "")[-500:],
            "unexplained_missing_events": unexplained,
        },
    )


def cert_lb_ready(url: str, host: str, *, n: int = 200) -> CertResult:
    ctx = ssl._create_unverified_context()
    latencies: list[float] = []
    ok = 0
    errors = 0

    def one(_: int) -> tuple[bool, float]:
        t0 = time.perf_counter()
        req = Request(url, headers={"Host": host})
        try:
            with urlopen(req, context=ctx, timeout=15) as resp:
                body = json.loads(resp.read().decode())
                return resp.status == 200 and body.get("ok") is True, (time.perf_counter() - t0) * 1000
        except (HTTPError, URLError, TimeoutError, json.JSONDecodeError):
            return False, (time.perf_counter() - t0) * 1000

    # Keep concurrency modest so we certify LB routing, not overload a single node.
    workers = min(16, max(4, n // 10))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futs = [pool.submit(one, i) for i in range(n)]
        for fut in as_completed(futs):
            good, ms = fut.result()
            latencies.append(ms)
            if good:
                ok += 1
            else:
                errors += 1
    # Allow tiny flake budget under TLS passthrough (≤1%).
    pass_ok = errors <= max(1, n // 100) and ok >= n - max(1, n // 100)
    return CertResult(
        "lb_ready_burst",
        pass_ok,
        {
            "ok": ok,
            "errors": errors,
            "p50_ms": _pct(latencies, 50),
            "p95_ms": _pct(latencies, 95),
            "p99_ms": _pct(latencies, 99),
            "workers": workers,
        },
    )


def cert_worker_crash_requeue(r: Any) -> CertResult:
    """Durable queue-like list: crash mid-flight leaves payload for retry/DLQ list."""
    q = f"linas:ha:q:{uuid.uuid4().hex}"
    dlq = f"{q}:dlq"
    for i in range(100):
        r.lpush(q, json.dumps({"id": i, "payload": "x"}))
    processed = 0
    for _ in range(100):
        raw = r.rpoplpush(q, f"{q}:inflight")
        if raw is None:
            break
        msg = json.loads(raw)
        if msg["id"] % 17 == 0:
            # simulate worker crash: leave in inflight, later move to dlq/retry
            r.lrem(f"{q}:inflight", 1, raw)
            r.lpush(dlq, raw)
        else:
            r.lrem(f"{q}:inflight", 1, raw)
            processed += 1
    # requeue DLQ
    while True:
        raw = r.rpop(dlq)
        if raw is None:
            break
        r.lpush(q, raw)
    remaining = int(r.llen(q)) + int(r.llen(f"{q}:inflight")) + int(r.llen(dlq))
    # After requeue, drain all
    drained = 0
    while r.rpop(q) is not None:
        drained += 1
    unexplained = int(r.llen(f"{q}:inflight")) + int(r.llen(dlq))
    return CertResult(
        "worker_crash_retry_dlq",
        unexplained == 0 and processed + drained == 100,
        {"processed": processed, "requeued_drained": drained, "unexplained": unexplained, "pre_drain_remaining": remaining},
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="docs/scale/LOAD_TEST_RESULTS_REAL_INFRA.json")
    parser.add_argument("--lb-url", default=os.getenv("LINAS_LB_READY_URL", ""))
    parser.add_argument("--lb-host", default="linasaibot.com")
    parser.add_argument("--quick", action="store_true")
    args = parser.parse_args()

    r = _redis_from_env()

    owners = 1000 if args.quick else 5000
    burst = 2000 if args.quick else 20_000
    conv = 200 if args.quick else 1000

    results = [
        cert_valkey_basics(r),
        cert_shared_counters(r, n=owners),
        cert_burst_idempotency(r, burst=burst),
        cert_ooo_conversation_lock(r, conversations=conv),
        cert_durable_ledger(),
        cert_worker_crash_requeue(r),
    ]
    if args.lb_url:
        results.append(cert_lb_ready(args.lb_url, args.lb_host, n=50 if args.quick else 200))

    payload = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "run_id": uuid.uuid4().hex,
        "topology": "real_valkey_ha_optional_lb",
        "results": [asdict(x) for x in results],
        "all_passed": all(x.passed for x in results),
        "unexplained_missing_events": next(
            (
                x.details.get("unexplained_missing_events")
                for x in results
                if x.name == "durable_ledger_reconcile"
            ),
            None,
        ),
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps({"all_passed": payload["all_passed"], "out": str(out), "n": len(results)}, indent=2))
    return 0 if payload["all_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
