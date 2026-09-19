#!/usr/bin/env bash
# Retired: cutover precheck depended on museum embeddings pin.
# Keep this path for HA cat-file checks. Do not flip production flags from this script.
set -euo pipefail

# shellcheck source=scripts/ha/require_production_mutation_guard.sh
source /opt/linasbot/scripts/ha/require_production_mutation_guard.sh
linas_require_production_mutation_guard "scripts/prod_cm_cutover.sh"

echo "[cm-cutover] retired after residual dead-legacy scrub; embedding museum removed"
exit 2
