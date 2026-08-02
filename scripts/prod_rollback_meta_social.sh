#!/usr/bin/env bash
# Safely unsubscribe the verified app, restore the encrypted retired-app
# configuration, and subscribe the retired app without a dual-active window.
set -euo pipefail

NEW_APP_ID="2963733803971681"
OLD_APP_ID="1784792718776344"
ENV_PATH="/opt/linasbot/.env"
MANAGER="/opt/linasbot/scripts/manage_meta_page_subscription.py"
RESTORE="/opt/linasbot/scripts/prod_restore_meta_social_rollback.sh"

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
    python3 "$MANAGER" unsubscribe --allow-absent
    META_ROLLBACK_ARCHIVE="${META_ROLLBACK_ARCHIVE:-LATEST}" \
      ROLLBACK_ENABLE_MESSAGING=false bash "$RESTORE"
  fi
  if [ "$(current_app_id)" = "$OLD_APP_ID" ]; then
    python3 "$MANAGER" subscribe --allow-present
    META_ROLLBACK_ARCHIVE="${META_ROLLBACK_ARCHIVE:-LATEST}" \
      ROLLBACK_ENABLE_MESSAGING=true bash "$RESTORE"
  fi
}
trap recover_old ERR

test "$(current_app_id)" = "$NEW_APP_ID"
python3 "$MANAGER" status --expect current-only
python3 "$MANAGER" unsubscribe
echo "[meta-rollback] verified_app_unsubscribed=true"

META_ROLLBACK_ARCHIVE="${META_ROLLBACK_ARCHIVE:-LATEST}" \
  ROLLBACK_ENABLE_MESSAGING=false bash "$RESTORE"
test "$(current_app_id)" = "$OLD_APP_ID"
python3 "$MANAGER" status --expect empty
python3 "$MANAGER" subscribe

META_ROLLBACK_ARCHIVE="${META_ROLLBACK_ARCHIVE:-LATEST}" \
  ROLLBACK_ENABLE_MESSAGING=true bash "$RESTORE"
python3 "$MANAGER" status --expect current-only

trap - ERR
echo "[meta-rollback] retired_app_restored=true"
echo "[meta-rollback] dual_subscription_window=false"
echo "[meta-rollback] SUCCESS"
