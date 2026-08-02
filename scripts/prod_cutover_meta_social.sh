#!/usr/bin/env bash
# Atomically replace the retired Meta app with the verified social app.
# All credentials stay in environment variables or root-owned mode-600 files.
set -euo pipefail

NEW_APP_ID="2963733803971681"
OLD_APP_ID="1784792718776344"
PAGE_ID="378696005334409"
INSTAGRAM_ID="17841413184256533"
GRAPH_VERSION="v24.0"
ENV_PATH="/opt/linasbot/.env"
MANAGER="/opt/linasbot/scripts/manage_meta_page_subscription.py"
APPLY="/opt/linasbot/scripts/prod_apply_meta_social_secrets.sh"
SNAPSHOT="/opt/linasbot/scripts/prod_snapshot_meta_social_rollback.sh"
RESTORE="/opt/linasbot/scripts/prod_restore_meta_social_rollback.sh"
VALIDATE="/opt/linasbot/scripts/validate_meta_social_token.py"

required_nonempty=(
  META_APP_ID
  META_APP_SECRET
  META_PAGE_ID
  META_PAGE_ACCESS_TOKEN
  META_INSTAGRAM_ACCOUNT_ID
  META_WEBHOOK_VERIFY_TOKEN
  META_GRAPH_API_VERSION
  META_ROLLBACK_ENCRYPTION_KEY
)
for key in "${required_nonempty[@]}"; do
  if [ -z "${!key:-}" ]; then
    echo "[meta-cutover] missing required environment variable: $key" >&2
    exit 1
  fi
done

test "$META_APP_ID" = "$NEW_APP_ID"
test "$META_PAGE_ID" = "$PAGE_ID"
test "$META_INSTAGRAM_ACCOUNT_ID" = "$INSTAGRAM_ID"
test "$META_GRAPH_API_VERSION" = "$GRAPH_VERSION"
test "${#META_APP_SECRET}" -ge 16
test "${#META_PAGE_ACCESS_TOKEN}" -ge 20
test "${#META_WEBHOOK_VERIFY_TOKEN}" -ge 32
test "${#META_ROLLBACK_ENCRYPTION_KEY}" -ge 32
test -f "$ENV_PATH"
test -f "$MANAGER"
test -f "$APPLY"
test -f "$SNAPSHOT"
test -f "$RESTORE"
test -f "$VALIDATE"

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

phase="preflight"
rollback_attempted="false"

rollback_on_error() {
  exit_code=$?
  trap - ERR
  set +e
  rollback_attempted="true"
  echo "[meta-cutover] failure_phase=$phase"
  echo "[meta-cutover] rollback_started=true"

  if [ "$phase" = "new_apply_started" ] || [ "$phase" = "new_applied" ] || \
    [ "$phase" = "new_subscribed" ] || [ "$phase" = "enabled" ]; then
    python3 "$MANAGER" unsubscribe --allow-absent
    new_unsubscribe_code=$?
    if [ "$new_unsubscribe_code" -ne 0 ]; then
      echo "[meta-cutover] rollback_new_unsubscribe_failed=true" >&2
      exit "$exit_code"
    fi
    META_ROLLBACK_ARCHIVE=LATEST ROLLBACK_ENABLE_MESSAGING=false bash "$RESTORE"
    restore_code=$?
    if [ "$restore_code" -ne 0 ]; then
      echo "[meta-cutover] rollback_restore_failed=true" >&2
      exit "$exit_code"
    fi
    python3 "$MANAGER" subscribe --allow-present
    old_subscribe_code=$?
    if [ "$old_subscribe_code" -ne 0 ]; then
      echo "[meta-cutover] rollback_old_subscribe_failed=true" >&2
      exit "$exit_code"
    fi
    META_ROLLBACK_ARCHIVE=LATEST ROLLBACK_ENABLE_MESSAGING=true bash "$RESTORE"
  elif [ "$phase" = "old_unsubscribed" ]; then
    python3 "$MANAGER" subscribe --allow-present
  fi

  if [ "$(current_app_id)" = "$OLD_APP_ID" ]; then
    echo "[meta-cutover] rollback_old_app_restored=true"
  else
    echo "[meta-cutover] rollback_old_app_restored=false" >&2
  fi
  echo "[meta-cutover] rollback_attempted=$rollback_attempted"
  exit "$exit_code"
}
trap rollback_on_error ERR

test "$(current_app_id)" = "$OLD_APP_ID"
echo "[meta-cutover] retired_app_active_before=true"

bash "$SNAPSHOT"
python3 "$VALIDATE"
python3 "$MANAGER" status --expect current-only
echo "[meta-cutover] candidate_and_rollback_ready=true"

python3 "$MANAGER" unsubscribe
phase="old_unsubscribed"
echo "[meta-cutover] retired_app_unsubscribed=true"

phase="new_apply_started"
APPLY_ENABLE_MESSAGING=false bash "$APPLY"
phase="new_applied"
test "$(current_app_id)" = "$NEW_APP_ID"
echo "[meta-cutover] new_credentials_applied=true"
echo "[meta-cutover] messaging_disabled_during_swap=true"

python3 "$MANAGER" status --expect empty
python3 "$MANAGER" subscribe
phase="new_subscribed"
echo "[meta-cutover] new_app_subscribed=true"

APPLY_ENABLE_MESSAGING=true bash "$APPLY"
phase="enabled"
python3 "$MANAGER" status --expect current-only

python3 - <<'PY'
import json
import urllib.request

for path in ("/api/health", "/api/ready"):
    with urllib.request.urlopen("https://www.linasaibot.com" + path, timeout=15) as response:
        payload = json.load(response)
        if response.status != 200 or payload.get("ok") is not True:
            raise SystemExit(f"[meta-cutover] health failure at {path}")
        print(f"[meta-cutover] {path}=ok")
PY

trap - ERR
echo "[meta-cutover] success=true"
echo "[meta-cutover] rollback_attempted=false"
