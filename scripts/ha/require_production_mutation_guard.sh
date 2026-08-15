#!/usr/bin/env bash
# Source this file and call linas_require_production_mutation_guard with the
# repository-relative entrypoint before any production write or restart.

linas_require_production_mutation_guard() {
  local expected_script=""
  if [ -z "${EXPECTED_RELEASE_SHA:-}" ] || [ "$#" -lt 1 ]; then
    echo "[prod-mutation] guarded release context is incomplete" >&2
    return 1
  fi
  local python_bin=/opt/linasbot/venv/bin/python
  local guard=/opt/linasbot/scripts/ha/production_mutation_guard.py
  test -x "$python_bin"
  test -f "$guard"
  if [ "${LINAS_PRODUCTION_MUTATION_GUARD_ACTIVE:-}" = "true" ]; then
    for expected_script in "$@"; do
      if [ "${LINAS_PRODUCTION_MUTATION_SCRIPT:-}" = "$expected_script" ]; then
        "$python_bin" "$guard" verify-context \
          --expected-sha "$EXPECTED_RELEASE_SHA" \
          --script "$expected_script"
        return
      fi
    done
  elif [ "${LINAS_DEPLOY_MUTATION_GUARD_ACTIVE:-}" = "true" ]; then
    test -n "${LINAS_DEPLOY_MUTATION_TX_DIR:-}"
    for expected_script in "$@"; do
      if [ "${LINAS_DEPLOY_MUTATION_SCRIPT:-}" = "$expected_script" ]; then
        "$python_bin" "$guard" verify-deploy-context \
          --expected-sha "$EXPECTED_RELEASE_SHA" \
          --script "$expected_script" \
          --tx-dir "$LINAS_DEPLOY_MUTATION_TX_DIR"
        return
      fi
    done
  else
    echo "[prod-mutation] guarded runner or HA deploy transaction is required" >&2
    return 1
  fi
  echo "[prod-mutation] guarded runner is bound to a different entrypoint" >&2
  return 1
}
