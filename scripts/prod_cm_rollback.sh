#!/usr/bin/env bash
# Controlled CM rollback: restore CM_RUNTIME_MODE=legacy (optionally disable publish).
# Does not delete published versions; restores safe customer path immediately.
set -euo pipefail

# shellcheck source=scripts/ha/require_production_mutation_guard.sh
source /opt/linasbot/scripts/ha/require_production_mutation_guard.sh
linas_require_production_mutation_guard "scripts/prod_cm_rollback.sh"

export CM_RUNTIME_MODE_VALUE=legacy
export CM_PUBLISH_ENABLED_VALUE="${CM_PUBLISH_ENABLED_VALUE:-false}"
export CM_EMBEDDING_PROVIDER_VALUE="${CM_EMBEDDING_PROVIDER_VALUE:-openai}"
export CM_EMBEDDING_MODEL_VALUE="${CM_EMBEDDING_MODEL_VALUE:-text-embedding-3-small}"
bash /opt/linasbot/scripts/prod_cm_apply_flags.sh
sleep 2
curl -fsS http://127.0.0.1:8003/api/ready >/tmp/cm_rollback_ready.json || curl -fsS http://127.0.0.1:8000/api/ready >/tmp/cm_rollback_ready.json || true
echo "[cm-rollback] COMPLETE_OK mode=legacy publish=${CM_PUBLISH_ENABLED_VALUE}"
