#!/usr/bin/env bash
# Safely unsubscribe the verified app, restore the encrypted retired-app
# configuration, and subscribe the retired app without a dual-active window.
set -euo pipefail

NEW_APP_ID="2963733803971681"
OLD_APP_ID="1784792718776344"
ENV_PATH="/opt/linasbot/.env"
MANAGER="/opt/linasbot/scripts/manage_meta_page_subscription.py"
RESTORE="/opt/linasbot/scripts/prod_restore_meta_social_rollback.sh"
RETIRED_CONFIRM="CONFIRM_RETIRED_META_APP_SUBSCRIPTION"

manage_new() {
  python3 "$MANAGER" "$@" --expected-app-id "$NEW_APP_ID"
}

manage_old() {
  META_RETIRED_APP_SUBSCRIPTION_CONFIRM="$RETIRED_CONFIRM" \
    python3 "$MANAGER" "$@" --expected-app-id "$OLD_APP_ID"
}

test -n "${META_ROLLBACK_ENCRYPTION_KEY:-}"
test "${#META_ROLLBACK_ENCRYPTION_KEY}" -ge 32
test -n "${META_WEBHOOK_VERIFY_TOKEN:-}"
test "${#META_WEBHOOK_VERIFY_TOKEN}" -ge 32
test -f "$ENV_PATH"
test -f "$MANAGER"
test -f "$RESTORE"

current_app_id() {
  python3 - "$ENV_PATH" <<'PY'
import sys
from pathlib import Path

for line in Path(sys.argv[1]).read_text(encoding="utf-8").splitlines():
    if line.startswith("META_APP_ID="):
        print(line.split("=", 1)[1].strip())
        break
PY
}

recover_old() {
  trap - ERR
  set +e
  if [ "$(current_app_id)" = "$NEW_APP_ID" ]; then
    manage_new unsubscribe --allow-absent
    META_ROLLBACK_ARCHIVE="${META_ROLLBACK_ARCHIVE:-LATEST}" \
      ROLLBACK_ENABLE_MESSAGING=false bash "$RESTORE"
  fi
  if [ "$(current_app_id)" = "$OLD_APP_ID" ]; then
    manage_old subscribe --allow-present
    META_ROLLBACK_ARCHIVE="${META_ROLLBACK_ARCHIVE:-LATEST}" \
      ROLLBACK_ENABLE_MESSAGING=true bash "$RESTORE"
  fi
}
trap recover_old ERR

test "$(current_app_id)" = "$NEW_APP_ID"
manage_new status --expect current-only
manage_new unsubscribe
echo "[meta-rollback] verified_app_unsubscribed=true"

META_ROLLBACK_ARCHIVE="${META_ROLLBACK_ARCHIVE:-LATEST}" \
  ROLLBACK_ENABLE_MESSAGING=false bash "$RESTORE"
test "$(current_app_id)" = "$OLD_APP_ID"
manage_old status --expect empty
manage_old subscribe

META_ROLLBACK_ARCHIVE="${META_ROLLBACK_ARCHIVE:-LATEST}" \
  ROLLBACK_ENABLE_MESSAGING=true bash "$RESTORE"
manage_old status --expect current-only

trap - ERR
echo "[meta-rollback] retired_app_restored=true"
echo "[meta-rollback] dual_subscription_window=false"
echo "[meta-rollback] SUCCESS"
