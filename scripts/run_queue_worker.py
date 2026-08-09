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
        choices=["high_priority", "interactive", "background", "expensive"],
    )
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    os.environ["LINAS_WORKER_QUEUE"] = args.queue
    from services.queues.worker_runtime import main as worker_main

    return worker_main()


if __name__ == "__main__":
    raise SystemExit(main())
