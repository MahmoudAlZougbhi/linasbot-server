#!/usr/bin/env bash
# Retired HA wrapper: museum OpenAI embedding pin is gone.
# Live publish remains via AI Setup Save+Publish (Voyage index on publish).
# Keep this path for HA cat-file checks. Do not run against production from this script.
set -euo pipefail

# shellcheck source=scripts/ha/require_production_mutation_guard.sh
source /opt/linasbot/scripts/ha/require_production_mutation_guard.sh
linas_require_production_mutation_guard "scripts/prod_cm_publish.sh"

echo "[cm-publish] retired HA embedding-pin wrapper; publish from AI Setup (Luna/Voyage)"
exit 2
