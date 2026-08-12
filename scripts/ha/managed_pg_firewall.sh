#!/usr/bin/env bash
# Set Managed Postgres trusted sources to Linas droplets + tag only (doctl).
# Default dry-run; pass --apply to mutate firewall rules.
# NEVER opens SportBook/BOC resources — only configured droplet IDs + tag.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=/dev/null
source "${SCRIPT_DIR}/_managed_pg_common.sh"

usage() {
  cat <<EOF
usage: $0 [--apply]

Configure firewall for Managed Postgres cluster:
  id=${MG_PG_CLUSTER_ID}
  name=${MG_PG_CLUSTER_NAME}
  droplets=${MG_PG_DROPLET_IDS}
  tag=${MG_PG_FIREWALL_TAG}

Default is dry-run. Pass --apply to call doctl databases firewalls replace.
EOF
}

APPLY=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --apply) APPLY=1 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "unknown arg: $1" >&2; usage; exit 2 ;;
  esac
  shift
done

if ! command -v doctl >/dev/null 2>&1; then
  echo "[managed-pg-fw] doctl not found" >&2
  exit 1
fi

RULES=()
IFS=',' read -r -a DROPLETS <<<"${MG_PG_DROPLET_IDS}"
for id in "${DROPLETS[@]}"; do
  id="${id// /}"
  [[ -n "$id" ]] || continue
  RULES+=("droplet:${id}")
done
RULES+=("tag:${MG_PG_FIREWALL_TAG}")

RULES_CSV=$(IFS=,; echo "${RULES[*]}")
echo "[managed-pg-fw] cluster=${MG_PG_CLUSTER_NAME} (${MG_PG_CLUSTER_ID})"
echo "[managed-pg-fw] desired_rules=${RULES_CSV}"

echo "[managed-pg-fw] current firewall rules:"
if doctl databases firewalls list "${MG_PG_CLUSTER_ID}" -o json 2>/dev/null | python3 - <<'PY'
import json, sys
try:
    data = json.load(sys.stdin)
except Exception:
    print("(unable to parse current rules)")
    raise SystemExit(0)
for row in data if isinstance(data, list) else data.get("rules", []):
    t = row.get("type") or row.get("Type") or "?"
    v = row.get("value") or row.get("Value") or "?"
    print(f"  - {t}:{v}")
PY
then
  :
else
  echo "  (list failed — cluster may be offline or id wrong)"
fi

# doctl expects repeated --rule flags (not --rules CSV on all CLI versions).
DOCTL_RULE_ARGS=()
for r in "${RULES[@]}"; do
  DOCTL_RULE_ARGS+=(--rule "$r")
done

if [[ "$APPLY" -ne 1 ]]; then
  echo "[managed-pg-fw] DRY-RUN: would run:"
  echo "  doctl databases firewalls replace ${MG_PG_CLUSTER_ID} ${DOCTL_RULE_ARGS[*]}"
  exit 0
fi

echo "[managed-pg-fw] applying firewall replace..."
doctl databases firewalls replace "${MG_PG_CLUSTER_ID}" "${DOCTL_RULE_ARGS[@]}"

echo "[managed-pg-fw] post-apply rules:"
doctl databases firewalls list "${MG_PG_CLUSTER_ID}" -o json | python3 - <<'PY'
import json, sys
data = json.load(sys.stdin)
for row in data if isinstance(data, list) else data.get("rules", []):
    t = row.get("type") or row.get("Type") or "?"
    v = row.get("value") or row.get("Value") or "?"
    print(f"  - {t}:{v}")
PY
echo "[managed-pg-fw] DONE"
