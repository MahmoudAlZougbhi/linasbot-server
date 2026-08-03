#!/usr/bin/env bash
# Upsert CM production flags into /opt/linasbot .env files and restart linasbot.
# Never prints secret values. Requires explicit MODE/PUBLISH args from the workflow.
set -euo pipefail

MODE="${CM_RUNTIME_MODE_VALUE:-}"
PUBLISH="${CM_PUBLISH_ENABLED_VALUE:-}"
EMBED_PROVIDER="${CM_EMBEDDING_PROVIDER_VALUE:-openai}"
EMBED_MODEL="${CM_EMBEDDING_MODEL_VALUE:-text-embedding-3-small}"

if [ -z "$MODE" ] || [ -z "$PUBLISH" ]; then
  echo "[cm-flags] missing CM_RUNTIME_MODE_VALUE or CM_PUBLISH_ENABLED_VALUE" >&2
  exit 1
fi
case "$MODE" in
  legacy|published) ;;
  *) echo "[cm-flags] invalid mode=$MODE" >&2; exit 1 ;;
esac
case "$PUBLISH" in
  true|false) ;;
  *) echo "[cm-flags] invalid publish=$PUBLISH" >&2; exit 1 ;;
esac
if [ "$MODE" = "published" ] && [ "$EMBED_PROVIDER" = "hash" ]; then
  echo "[cm-flags] refusing hash embeddings with published mode" >&2
  exit 1
fi

export CM_RUNTIME_MODE_VALUE="$MODE"
export CM_PUBLISH_ENABLED_VALUE="$PUBLISH"
export CM_EMBEDDING_PROVIDER_VALUE="$EMBED_PROVIDER"
export CM_EMBEDDING_MODEL_VALUE="$EMBED_MODEL"

python3 - <<'PY'
import os
from pathlib import Path

updates = {
    "CM_RUNTIME_MODE": os.environ["CM_RUNTIME_MODE_VALUE"],
    "CM_PUBLISH_ENABLED": os.environ["CM_PUBLISH_ENABLED_VALUE"],
    "CM_EMBEDDING_PROVIDER": os.environ["CM_EMBEDDING_PROVIDER_VALUE"],
    "CM_EMBEDDING_MODEL": os.environ["CM_EMBEDDING_MODEL_VALUE"],
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
    print(f"[cm-flags] upserted path={path} keys={sorted(updates)}")

for candidate in (Path("/opt/linasbot/.env"), Path("/opt/linasbot/linaslaserbot-2.7.22/.env")):
    if candidate.parent.exists():
        upsert(candidate, updates)
PY

systemctl restart linasbot
sleep 2
systemctl is-active linasbot
echo "[cm-flags] runtime_mode=$MODE publish_enabled=$PUBLISH embedding_provider=$EMBED_PROVIDER"
echo "[cm-flags] COMPLETE_OK"
