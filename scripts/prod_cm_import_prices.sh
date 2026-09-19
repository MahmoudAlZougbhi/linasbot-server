#!/usr/bin/env bash
# Retired: staged price-file migration museum is gone.
# Keep this path for HA cat-file checks. Do not run against production.
set -euo pipefail

# shellcheck source=scripts/ha/require_production_mutation_guard.sh
source /opt/linasbot/scripts/ha/require_production_mutation_guard.sh
linas_require_production_mutation_guard \
  "scripts/prod_cm_import_prices.sh" \
  "scripts/prod_cm_repair_linas_prices_publish.sh"

echo "[cm-price-import] retired after residual dead-legacy scrub; edit Prices in AI Setup"
exit 2
