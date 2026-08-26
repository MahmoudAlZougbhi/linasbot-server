"""Run checkpointed soak segments against the isolated cert stack.

Does not target production. Requires LINAS_OMNI_CERT_STAGING=1.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--segments", type=int, default=24)
    parser.add_argument("--segment-seconds", type=int, default=3600)
    parser.add_argument("--start-at", type=int, default=0)
    args = parser.parse_args()
    os.environ["LINAS_OMNI_CERT_STAGING"] = "1"
    py = sys.executable
    summary: list[dict] = []
    for index in range(int(args.start_at), int(args.segments)):
        cmd = [
            py,
            "scripts/loadtest/omnichannel_live_cert.py",
            "--soak-segment-seconds",
            str(int(args.segment_seconds)),
            "--keep-stack",
        ]
        result = subprocess.run(cmd, cwd=str(ROOT), env=os.environ.copy())
        row = {"segment": index, "exit_code": result.returncode}
        summary.append(row)
        out = ROOT / "artifacts/omnichannel-cert/live-soak-segment.json"
        if out.exists():
            dest = ROOT / f"artifacts/omnichannel-cert/soak-segment-{index:02d}.json"
            dest.write_text(out.read_text(encoding="utf-8"), encoding="utf-8")
        if result.returncode != 0:
            break
    path = ROOT / "artifacts/omnichannel-cert/soak-summary.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"ok": all(r["exit_code"] == 0 for r in summary), "segments": summary}, indent=2) + "\n")
    print(path)
    return 0 if summary and all(r["exit_code"] == 0 for r in summary) else 1


if __name__ == "__main__":
    raise SystemExit(main())
