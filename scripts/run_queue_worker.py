#!/usr/bin/env python3
"""Run a durable Linas AI queue worker.

Usage:
  LINAS_WORKER_QUEUE=high_priority REDIS_URL=redis://... python scripts/run_queue_worker.py
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--queue",
        required=True,
        choices=[
            "high_priority",
            "interactive",
            "background",
            "expensive",
            "ai_reply",
            "embeddings",
            "outbound_send",
            "webhook_process",
            "owner_copilot",
            "maintenance",
        ],
    )
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    os.environ["LINAS_WORKER_QUEUE"] = args.queue
    from utils.host_timezone import log_if_host_timezone_is_not_utc

    log_if_host_timezone_is_not_utc()
    from services.platform.feature_flags import flag_value

    if flag_value("queue_backend") == "pg":
        from services.platform.pg_worker import serve

        serve(args.queue)
        return 0
    from services.queues.worker_runtime import main as worker_main

    return worker_main()


if __name__ == "__main__":
    raise SystemExit(main())
