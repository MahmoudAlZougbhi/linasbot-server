#!/usr/bin/env bash
# Retired: production content-migration museum (prod_migration/redistribution) is gone.
# Keep this path for HA cat-file checks. Do not run against production.
set -euo pipefail

# shellcheck source=scripts/ha/require_production_mutation_guard.sh
source /opt/linasbot/scripts/ha/require_production_mutation_guard.sh
linas_require_production_mutation_guard "scripts/prod_cm_migrate_and_validate.sh"

echo "[cm-migrate] retired after residual dead-legacy scrub; use AI Setup Save+Publish"
exit 2
