"""Omnichannel synthetic certification (mocked providers). Never hits live Meta/TikTok/WA.

CI smoke: --ci-smoke (compressed mix, seconds).
Staging full: --full (60m baseline + 10m 2x burst) and --soak-24h after functional pass.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.omnichannel.classify import classify_http_delivery  # noqa: E402
from services.omnichannel.contract import NormalizedInbound  # noqa: E402
from services.omnichannel.queues import logical_for_channel, physical_queue_for  # noqa: E402
from services.omnichannel.store import persist_inbound, persist_outbound  # noqa: E402

MIX = (
    ("instagram", "comment", 200),
    ("tiktok", "comment", 200),
    ("instagram", "dm", 300),
    ("facebook", "dm", 300),
    ("tiktok", "dm", 300),
    ("whatsapp", "dm", 600),
)


def _pct(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    idx = min(len(ordered) - 1, max(0, int(round((p / 100.0) * (len(ordered) - 1)))))
    return ordered[idx]


def _build_events(scale: float, minutes: float) -> list[NormalizedInbound]:
    events: list[NormalizedInbound] = []
    for channel, surface, per_min in MIX:
        count = max(1, int(per_min * minutes * scale))
        for i in range(count):
            pid = f"{channel}-{surface}-{i}"
            events.append(
                NormalizedInbound(
                    provider_event_id=pid,
                    tenant_id="linas" if i % 17 else f"t{i % 5}",
                    account_id=f"acct-{i % 11}",
                    channel=channel,  # type: ignore[arg-type]
                    surface=surface,  # type: ignore[arg-type]
                    conversation_key=f"linas:{channel}:{i % 40}",
                    provider_timestamp=time.time(),
                    payload_hash=pid,
                    payload={"text": "hi", "i": i},
                )
            )
    return events


def run_cert(*, minutes: float, burst_scale: float, duplicate_ratio: float) -> dict[str, Any]:
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from db.models.base import Base
    from db.models.omnichannel import OmnichannelInboundEvent, OmnichannelOutboundOutbox

    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine, tables=[OmnichannelInboundEvent.__table__, OmnichannelOutboundOutbox.__table__])
    session = sessionmaker(bind=engine, future=True)()
    events = _build_events(scale=1.0, minutes=minutes)
    burst = _build_events(scale=burst_scale, minutes=max(0.1, minutes / 6.0))
    latencies: list[float] = []
    accepted = 0
    duplicates = 0
    start = time.perf_counter()
    for event in events + burst:
        t0 = time.perf_counter()
        _row, created = persist_inbound(session, event)
        if created:
            persist_outbound(
                session,
                tenant_id=event.tenant_id,
                channel=event.channel,
                surface=event.surface,
                account_id=event.account_id,
                conversation_key=event.conversation_key,
                inbound_event_id=_row.id,
                canonical_body="canonical",
                idempotency_key=f"omni:{_row.id}:v1",
            )
            accepted += 1
        else:
            duplicates += 1
        latencies.append((time.perf_counter() - t0) * 1000.0)
    extra_dups = int(len(events) * duplicate_ratio)
    for event in events[:extra_dups]:
        _row, created = persist_inbound(session, event)
        duplicates += 0 if created else 1
    session.commit()
    inbound_count = session.query(OmnichannelInboundEvent).count()
    outbox_count = session.query(OmnichannelOutboundOutbox).count()
    throttled = classify_http_delivery(http_status=429, provider_code="613")
    queues = Counter(physical_queue_for(logical_for_channel(channel=e.channel, surface=e.surface)) for e in events)
    duration = time.perf_counter() - start
    lost = max(0, accepted - inbound_count)
    passed = lost == 0 and inbound_count == accepted and outbox_count == accepted and throttled.retryable
    return {
        "accepted": accepted,
        "duplicates": duplicates,
        "inbound_rows": inbound_count,
        "outbox_rows": outbox_count,
        "lost": lost,
        "p95_persist_ms": _pct(latencies, 95),
        "p99_persist_ms": _pct(latencies, 99),
        "duration_seconds": duration,
        "queue_mix": dict(queues),
        "throttle_retryable": throttled.retryable,
        "passed": passed,
        "notes": "mocked providers; 24h soak and live quotas are staging-only",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ci-smoke", action="store_true")
    parser.add_argument("--full", action="store_true")
    parser.add_argument("--soak-24h", action="store_true")
    args = parser.parse_args()
    if args.soak_24h:
        print(json.dumps({"ok": False, "reason": "soak_24h_requires_isolated_staging"}))
        return 2
    minutes = 60.0 if args.full else 0.05
    result = run_cert(minutes=minutes, burst_scale=2.0, duplicate_ratio=0.1)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result.get("passed") else 1


if __name__ == "__main__":
    raise SystemExit(main())
