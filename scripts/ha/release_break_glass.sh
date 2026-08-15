#!/bin/bash
# Deliberately non-operational marker for the production release break-glass path.
# A repository checkout must never be sufficient to obtain single-node deploy authority.

set -euo pipefail

printf '%s\n' \
  'BLOCKED: product code contains no single-node production release bypass.' \
  'Break-glass access is disabled by default and must be granted live, out of band, with both nodes drained.' \
  'See docs/release/TWO_NODE_RELEASE_POLICY.md.' >&2
exit 2
