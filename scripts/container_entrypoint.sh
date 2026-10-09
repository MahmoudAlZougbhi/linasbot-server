#!/bin/sh
set -eu
case "${1:-api}" in
  api)
    exec python main.py
    ;;
  worker)
    shift
    exec python scripts/run_queue_worker.py "$@"
    ;;
  scheduler)
    exec python scripts/run_scheduler.py
    ;;
  *)
    exec "$@"
    ;;
esac
