"""Stage timers for Luna (retrieval) then Tera (answer). Does not change models."""

from __future__ import annotations

import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager


@asynccontextmanager
async def time_stage(name: str) -> AsyncIterator[dict[str, float]]:
    """Record one named AI stage to the shared histogram and optional trace."""
    from services.scale.latency_histogram import observe
    from services.scale.trace_context import get_trace_id
    from services.scale.trace_span import mark

    started = time.perf_counter()
    tid = get_trace_id()
    stage_start = f"ai_{name}_started"
    stage_end = f"ai_{name}_finished"
    if tid:
        mark(tid, stage_start)
    try:
        from services.scale.job_progress import mark_stage

        mark_stage(f"{name}_started")
    except Exception:
        pass
    payload: dict[str, float] = {}
    try:
        yield payload
    finally:
        elapsed_ms = max(0.0, (time.perf_counter() - started) * 1000.0)
        payload["ms"] = elapsed_ms
        observe(f"ai_{name}_ms", elapsed_ms)
        if tid:
            mark(tid, stage_end)
        try:
            from services.scale.job_progress import mark_stage

            mark_stage(f"{name}_completed")
        except Exception:
            pass


def record_gap_ms(from_stage: str, to_stage: str, gap_ms: float) -> None:
    from services.scale.latency_histogram import observe

    observe(f"ai_{from_stage}_{to_stage}_gap_ms", max(0.0, float(gap_ms)))
