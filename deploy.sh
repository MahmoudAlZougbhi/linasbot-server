#!/bin/bash
# The standalone production deploy path is intentionally retired.
# Production releases require the protected, exact-artifact, two-node workflow.

set -euo pipefail

printf '%s\n' \
  'Standalone deploy.sh is disabled.' \
  'Use the manual protected .github/workflows/deploy.yml transaction.' >&2
exit 2
