#!/usr/bin/env bash
# Upsert CM production flags into /opt/linasbot .env files and restart linasbot.
# Never prints secret values. Requires explicit MODE/PUBLISH args from the workflow.
set -euo pipefail

# shellcheck source=scripts/ha/require_production_mutation_guard.sh
source /opt/linasbot/scripts/ha/require_production_mutation_guard.sh
linas_require_production_mutation_guard \
  "scripts/prod_cm_apply_flags.sh" \
  "scripts/prod_cm_cutover.sh" \
  "scripts/prod_cm_rollback.sh"

MODE="${CM_RUNTIME_MODE_VALUE:-}"
PUBLISH="${CM_PUBLISH_ENABLED_VALUE:-}"
EMBED_PROVIDER="${CM_EMBEDDING_PROVIDER_VALUE:-openai}"
EMBED_MODEL="${CM_EMBEDDING_MODEL_VALUE:-text-embedding-3-small}"
FAQ_CANONICAL="${CM_FAQ_CANONICAL_VALUE:-}"

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
if [ -n "$FAQ_CANONICAL" ]; then
  case "$FAQ_CANONICAL" in
    true|false) ;;
    *) echo "[cm-flags] invalid CM_FAQ_CANONICAL_VALUE=$FAQ_CANONICAL" >&2; exit 1 ;;
  esac
fi
if [ "$MODE" = "published" ] && [ "$EMBED_PROVIDER" = "hash" ]; then
  echo "[cm-flags] refusing hash embeddings with published mode" >&2
  exit 1
fi

export CM_RUNTIME_MODE_VALUE="$MODE"
export CM_PUBLISH_ENABLED_VALUE="$PUBLISH"
export CM_EMBEDDING_PROVIDER_VALUE="$EMBED_PROVIDER"
export CM_EMBEDDING_MODEL_VALUE="$EMBED_MODEL"
export CM_FAQ_CANONICAL_VALUE="$FAQ_CANONICAL"

PYTHONPATH=/opt/linasbot /opt/linasbot/venv/bin/python - <<'PY'
import os

from scripts.ha.production_env_cas import atomic_update_canonical_env

updates = {
    "CM_RUNTIME_MODE": os.environ["CM_RUNTIME_MODE_VALUE"],
    "CM_PUBLISH_ENABLED": os.environ["CM_PUBLISH_ENABLED_VALUE"],
    "CM_EMBEDDING_PROVIDER": os.environ["CM_EMBEDDING_PROVIDER_VALUE"],
    "CM_EMBEDDING_MODEL": os.environ["CM_EMBEDDING_MODEL_VALUE"],
}
faq = (os.environ.get("CM_FAQ_CANONICAL_VALUE") or "").strip()
if faq:
    updates["CM_FAQ_CANONICAL"] = faq

atomic_update_canonical_env(updates)
print(f"[cm-flags] canonical_env_updated=true keys={sorted(updates)}")
PY

systemctl restart linasbot
sleep 2
systemctl is-active linasbot
echo "[cm-flags] runtime_mode=$MODE publish_enabled=$PUBLISH embedding_provider=$EMBED_PROVIDER faq_canonical=${FAQ_CANONICAL:-unchanged}"
echo "[cm-flags] COMPLETE_OK"
