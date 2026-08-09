#!/usr/bin/env bash
# Upsert CM_DISABLE_LINAS_LEGACY_BRIDGE and restart linasbot.
# Never prints secret values. Usage: prod_cm_set_linas_bridge_flag.sh true|false
set -euo pipefail

VALUE="${1:-}"
if [ "$VALUE" != "true" ] && [ "$VALUE" != "false" ]; then
  echo "[cm-bridge-flag] usage: $0 true|false" >&2
  exit 1
fi

export CM_DISABLE_LINAS_LEGACY_BRIDGE_VALUE="$VALUE"

python3 - <<'PY'
import os
from pathlib import Path

updates = {
    "CM_DISABLE_LINAS_LEGACY_BRIDGE": os.environ["CM_DISABLE_LINAS_LEGACY_BRIDGE_VALUE"],
}

def upsert(path: Path, updates: dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    found: set[str] = set()
    out: list[str] = []
    for line in lines:
        if "=" in line and not line.lstrip().startswith("#"):
            key = line.split("=", 1)[0].strip()
            if key in updates:
                out.append(f"{key}={updates[key]}")
                found.add(key)
                continue
        out.append(line)
    for key, value in updates.items():
        if key not in found:
            out.append(f"{key}={value}")
    path.write_text("\n".join(out).rstrip() + "\n", encoding="utf-8")
    os.chmod(path, 0o600)
    print(f"[cm-bridge-flag] upserted path={path} keys={sorted(updates)}")

for candidate in (Path("/opt/linasbot/.env"), Path("/opt/linasbot/linaslaserbot-2.7.22/.env")):
    if candidate.parent.exists():
        upsert(candidate, updates)
PY

systemctl restart linasbot
sleep 2
systemctl is-active linasbot
echo "[cm-bridge-flag] CM_DISABLE_LINAS_LEGACY_BRIDGE=$VALUE"
echo "[cm-bridge-flag] COMPLETE_OK"
