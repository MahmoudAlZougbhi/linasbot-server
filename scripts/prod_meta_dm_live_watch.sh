#!/usr/bin/env bash
# Watch recent Meta DM traffic for controlled live verification (redacted).
# Does not send messages. Use after a human sends the inbound test DMs.
set -euo pipefail
SINCE="${1:-15 minutes ago}"
echo "[meta-dm-watch] since=$SINCE deployed_sha=$(git -C /opt/linasbot rev-parse HEAD 2>/dev/null || echo unknown)"

journalctl -u linasbot --since "$SINCE" --no-pager -o cat 2>/dev/null | python3 - <<'PY'
from __future__ import annotations

import re
import sys
from collections import Counter

lines = sys.stdin.read().splitlines()
patterns = {
    "webhook_authenticated": r"\[meta-social\] webhook_authenticated",
    "event_processing_started": r"\[meta-social\] event_processing_started",
    "event_processing_completed": r"\[meta-social\] event_processing_completed",
    "event_processing_failed": r"\[meta-social\] event_processing_failed",
    "cm_runtime_pipeline": r"handler_path[=:]['\"]?cm_runtime_pipeline|handled_by[=:]['\"]?cm_runtime_pipeline",
    "content_version": r"content_version_id[=:]['\"]?(v_[a-f0-9]+)",
    "meta_send_4xx": r"Meta Send API returned HTTP 4\d\d",
    "meta_send_5xx": r"Meta Send API returned HTTP 5\d\d",
    "instagram_object": r"object=instagram",
    "page_object": r"object=page",
}
counts = Counter()
versions = Counter()
for line in lines:
    for name, pat in patterns.items():
        for match in re.finditer(pat, line, re.IGNORECASE):
            counts[name] += 1
            if name == "content_version" and match.lastindex:
                versions[match.group(1)] += 1

print("{")
print(f'  "journal_lines": {len(lines)},')
for name in sorted(patterns):
    print(f'  "{name}": {counts[name]},')
print(f'  "content_version_ids": {dict(versions)}')
print("}")
print("[meta-dm-watch] COMPLETE_OK")
PY
