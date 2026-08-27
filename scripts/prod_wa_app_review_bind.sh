#!/usr/bin/env bash
# Dry-run or bind the one reviewed Meta test number from the canonical runtime.
set -euo pipefail

# shellcheck source=scripts/ha/require_production_mutation_guard.sh
source /opt/linasbot/scripts/ha/require_production_mutation_guard.sh
linas_require_production_mutation_guard "scripts/prod_wa_app_review_bind.sh"

if [ "$#" -ne 1 ] || { [ "$1" != dry-run ] && [ "$1" != bind ]; }; then
  echo "[wa-app-review-bind] BLOCKED: mode must be dry-run or bind" >&2
  exit 2
fi
MODE="$1"

bash /opt/linasbot/scripts/ha/verify_meta_release_ha.sh "$EXPECTED_RELEASE_SHA"
cd /opt/linasbot
/opt/linasbot/venv/bin/python -I - "$MODE" <<'PY'
from __future__ import annotations

import asyncio
import hmac
import os
import sys
from typing import Any

sys.path.insert(0, "/opt/linasbot")

from db.session import whatsapp_session
from services.whatsapp_cloud.app_review_bind import (
    WEBHOOK_FIELDS,
    AppReviewBindError,
    bind_app_review_test_number,
    status_app_review_bind,
)
from services.whatsapp_cloud.config import WHATSAPP_REQUIRED_SCOPES, get_whatsapp_cloud_flags
from services.whatsapp_cloud.repository import ACTIVE_LIFECYCLES, WhatsAppCloudRepository

TENANT_ID = "linas"
WABA_ID = "1409769574350248"
PHONE_NUMBER_ID = "1322897994230591"
EXPECTED_APP_ID = "2963733803971681"
EXPECTED_LAST4 = "4285"
EXPECTED_WABA_MASK = "140…248"
EXPECTED_PHONE_MASK = "132…591"
IDEMPOTENCY_KEY = "meta-review-20260826-1409769574350248-1322897994230591"
BIND_ATTEMPTED = False
BIND_RETURNED = False


def fail(code: str) -> None:
    raise RuntimeError(code)


def static_preflight() -> str:
    mode = sys.argv[1]
    if mode not in {"dry-run", "bind"}:
        fail("mode_invalid")
    flags = get_whatsapp_cloud_flags()
    if flags.public_availability:
        fail("public_availability_must_remain_false")
    if not all(
        (
            flags.connection_ui_enabled,
            flags.webhook_side_effects_enabled,
            flags.outbound_sends_enabled,
            flags.ai_replies_enabled,
        )
    ):
        fail("recording_runtime_flags_not_enabled")
    if flags.history_sync_enabled:
        fail("history_sync_must_remain_false")
    if not flags.require_pilot_entitlement:
        fail("pilot_entitlement_gate_must_remain_enabled")
    app_id = str(os.getenv("META_APP_A_ID") or os.getenv("META_APP_ID") or "").strip()
    if app_id != EXPECTED_APP_ID:
        fail("meta_app_id_mismatch")
    allowed = {
        value.strip()
        for value in str(os.getenv("META_WHATSAPP_APP_REVIEW_ALLOWED_WABA_IDS") or "").split(",")
        if value.strip()
    }
    if allowed != {WABA_ID}:
        fail("waba_allowlist_mismatch")
    token = str(os.getenv("META_WHATSAPP_APP_REVIEW_BIND_TOKEN") or "").strip()
    if len(token) < 20:
        fail("bind_token_missing")
    if str(os.getenv("LINAS_WHATSAPP_ALLOW_SQLITE") or "").strip().lower() == "true":
        fail("sqlite_forbidden")
    return token


def assert_dry_run(payload: dict[str, Any], token: str) -> None:
    detail = payload.get("detail") if isinstance(payload.get("detail"), dict) else {}
    if not payload.get("success") or payload.get("action") != "dry_run" or payload.get("dry_run") is not True:
        fail("dry_run_failed")
    if payload.get("tenant_id") != TENANT_ID or payload.get("display_phone_last4") != EXPECTED_LAST4:
        fail("dry_run_asset_mismatch")
    if payload.get("waba_id_masked") != EXPECTED_WABA_MASK:
        fail("dry_run_waba_mismatch")
    if payload.get("phone_number_id_masked") != EXPECTED_PHONE_MASK:
        fail("dry_run_phone_mismatch")
    if payload.get("public_availability") is not False or detail.get("public_availability") is not False:
        fail("dry_run_public_availability_changed")
    if str(detail.get("token_app_id") or "") != EXPECTED_APP_ID:
        fail("dry_run_token_app_mismatch")
    collision = detail.get("collision")
    if collision is not None and not (
        isinstance(collision, dict)
        and collision.get("same_tenant") is True
        and collision.get("is_app_review") is True
    ):
        fail("dry_run_collision")
    if int(detail.get("scopes_count") or 0) < 2 or detail.get("subscribe_webhooks") is not True:
        fail("dry_run_scope_or_webhook_mismatch")
    planned_action = str(detail.get("planned_action") or "")
    with whatsapp_session() as session:
        repo = WhatsAppCloudRepository(session)
        existing = repo.find_active_by_phone_number_id(PHONE_NUMBER_ID)
        if collision is None:
            if existing is not None:
                fail("dry_run_collision_state_mismatch")
            if planned_action != "bind":
                fail("dry_run_planned_action_mismatch")
            return
        if existing is None or existing.id != str(collision.get("connection_id") or ""):
            fail("dry_run_collision_row_mismatch")
        if (
            existing.tenant_id != TENANT_ID
            or existing.waba_id != WABA_ID
            or existing.phone_number_id != PHONE_NUMBER_ID
            or existing.connection_source != "meta_app_review_test"
            or existing.lifecycle_status not in ACTIVE_LIFECYCLES
        ):
            fail("dry_run_existing_asset_mismatch")
        if existing.lifecycle_status == "connected":
            credential_matches = hmac.compare_digest(repo.load_access_token(existing), token)
            expected_action = "bind_idempotent" if credential_matches else "credential_rotate"
            if planned_action != expected_action:
                fail("dry_run_existing_credential_mismatch")
        elif planned_action != "rebind_incomplete":
            fail("dry_run_planned_action_mismatch")


def assert_bound(payload: dict[str, Any], token: str) -> None:
    if not payload.get("success") or payload.get("action") not in {
        "bind",
        "bind_idempotent",
        "credential_rotated",
    }:
        fail("bind_failed")
    if payload.get("lifecycle_status") != "connected" or payload.get("display_phone_last4") != EXPECTED_LAST4:
        fail("bind_connection_mismatch")
    if payload.get("public_availability") is not False:
        fail("bind_public_availability_changed")
    connection_id = str(payload.get("connection_id") or "")
    if not connection_id:
        fail("bind_connection_id_missing")
    if payload.get("waba_id_masked") != EXPECTED_WABA_MASK:
        fail("bind_waba_mismatch")
    if payload.get("phone_number_id_masked") != EXPECTED_PHONE_MASK:
        fail("bind_phone_mismatch")

    status = status_app_review_bind(tenant_id=TENANT_ID)
    if status.get("active_count") != 1 or status.get("connection_source") != "meta_app_review_test":
        fail("bind_status_count_or_source_mismatch")
    if status.get("public_availability") is not False:
        fail("bind_status_public_availability_changed")
    public_connection = status.get("connection") if isinstance(status.get("connection"), dict) else {}
    if public_connection.get("lifecycle_status") != "connected":
        fail("bind_status_not_connected")
    if public_connection.get("connection_id") != connection_id:
        fail("bind_status_connection_id_mismatch")
    if public_connection.get("display_phone_last4") != EXPECTED_LAST4:
        fail("bind_status_phone_mismatch")
    if public_connection.get("ai_default_enabled") is not True:
        fail("bind_ai_not_enabled")
    if public_connection.get("webhook_subscription_status") != "ready":
        fail("bind_status_webhook_not_ready")
    if public_connection.get("health_status") != "healthy":
        fail("bind_status_not_healthy")
    if public_connection.get("history_sync_status") != "skipped":
        fail("bind_status_history_sync_mismatch")

    with whatsapp_session() as session:
        repo = WhatsAppCloudRepository(session)
        active = [
            row
            for row in repo.list_tenant_connections(TENANT_ID, include_revoked=False)
            if row.lifecycle_status in ACTIVE_LIFECYCLES and row.connection_source == "meta_app_review_test"
        ]
        if len(active) != 1:
            fail("bind_raw_active_count_mismatch")
        connection = active[0]
        resolved = repo.find_active_by_phone_number_id(PHONE_NUMBER_ID)
        if connection.id != connection_id or resolved is None or resolved.id != connection_id:
            fail("bind_raw_connection_id_mismatch")
        if connection.tenant_id != TENANT_ID or connection.waba_id != WABA_ID:
            fail("bind_raw_owner_mismatch")
        if connection.phone_number_id != PHONE_NUMBER_ID or connection.lifecycle_status != "connected":
            fail("bind_raw_phone_or_lifecycle_mismatch")
        if connection.meta_app_id != EXPECTED_APP_ID or connection.connection_source != "meta_app_review_test":
            fail("bind_raw_app_or_source_mismatch")
        if connection.webhook_subscription_status != "ready":
            fail("bind_raw_webhook_not_ready")
        if set(connection.webhook_subscribed_fields or []) != set(WEBHOOK_FIELDS):
            fail("bind_raw_webhook_fields_mismatch")
        if connection.webhook_last_success_at is None or connection.health_status != "healthy":
            fail("bind_raw_health_mismatch")
        if connection.history_sync_status != "skipped":
            fail("bind_raw_history_sync_mismatch")
        if not WHATSAPP_REQUIRED_SCOPES.issubset(set(connection.granted_scopes or [])):
            fail("bind_raw_scopes_mismatch")
        if connection.ai_default_enabled is not True or connection.display_phone_last4 != EXPECTED_LAST4:
            fail("bind_raw_ai_or_display_mismatch")
        if not hmac.compare_digest(repo.load_access_token(connection), token):
            fail("bind_credential_mismatch")
        if repo.get_active_pilot(TENANT_ID) is None:
            fail("bind_pilot_missing")


async def run() -> None:
    global BIND_ATTEMPTED, BIND_RETURNED

    token = static_preflight()
    dry_result = await bind_app_review_test_number(
        tenant_id=TENANT_ID,
        waba_id=WABA_ID,
        phone_number_id=PHONE_NUMBER_ID,
        access_token=None,
        actor_user_id="github-actions:wa-app-review-bind",
        idempotency_key=IDEMPOTENCY_KEY,
        dry_run=True,
    )
    assert_dry_run(dry_result.public_dict(), token)
    print(
        "[wa-app-review-bind] DRY_RUN_OK tenant=linas last4=4285 "
        "scopes_ok=true public_availability=false"
    )
    if sys.argv[1] == "dry-run":
        return

    BIND_ATTEMPTED = True
    bound = await bind_app_review_test_number(
        tenant_id=TENANT_ID,
        waba_id=WABA_ID,
        phone_number_id=PHONE_NUMBER_ID,
        access_token=None,
        actor_user_id="github-actions:wa-app-review-bind",
        idempotency_key=IDEMPOTENCY_KEY,
        dry_run=False,
    )
    BIND_RETURNED = True
    public = bound.public_dict()
    assert_bound(public, token)
    print(
        f"[wa-app-review-bind] BIND_COMPLETE_OK action={public['action']} tenant=linas "
        "last4=4285 lifecycle=connected ai_default_enabled=true public_availability=false"
    )


try:
    asyncio.run(run())
except AppReviewBindError as exc:
    if BIND_RETURNED:
        print("[wa-app-review-bind] BIND_COMMITTED_POSTCHECK_FAILED", file=sys.stderr)
    elif BIND_ATTEMPTED:
        print("[wa-app-review-bind] BIND_OUTCOME_UNCERTAIN stage=bind_attempt", file=sys.stderr)
    print(f"[wa-app-review-bind] FAIL code={exc.code}", file=sys.stderr)
    raise SystemExit(1) from None
except Exception as exc:
    if BIND_RETURNED:
        print("[wa-app-review-bind] BIND_COMMITTED_POSTCHECK_FAILED", file=sys.stderr)
    elif BIND_ATTEMPTED:
        print("[wa-app-review-bind] BIND_OUTCOME_UNCERTAIN stage=bind_attempt", file=sys.stderr)
    print(f"[wa-app-review-bind] FAIL type={type(exc).__name__}", file=sys.stderr)
    raise SystemExit(1) from None
PY
if ! bash /opt/linasbot/scripts/ha/verify_meta_release_ha.sh "$EXPECTED_RELEASE_SHA"; then
  if [ "$MODE" = bind ]; then
    echo "[wa-app-review-bind] BIND_OUTCOME_UNCERTAIN stage=final_ha_verify" >&2
  fi
  exit 1
fi
echo "[wa-app-review-bind] COMPLETE_OK mode=$MODE"
