#!/usr/bin/env python3
"""Scheduler process. It only enqueues work, and only the leader does that."""

from __future__ import annotations

import os
import sys
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    os.environ.setdefault("LINAS_FLAG_SCHEDULER_MODE", "pg")
    from services.platform.pg_jobs import PgDurableQueue
    from services.platform.scheduler_leader import try_acquire_leader
    from services.queues.models import QueueJob

    queue = PgDurableQueue()
    owner = uuid.uuid4().hex
    engine = queue._engine
    while True:
        if try_acquire_leader(engine, name="scheduler", owner=owner):
            queue.enqueue(
                QueueJob.new(
                    queue="maintenance",
                    job_type="scheduler_tick",
                    tenant_id="platform",
                    payload={"owner": owner},
                    idempotency_key=f"tick:{int(time.time()) // 60}",
                )
            )
        time.sleep(15)


if __name__ == "__main__":
    raise SystemExit(main())
