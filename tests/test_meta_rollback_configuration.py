"""Static safety contracts for encrypted Meta credential rollback."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_snapshot_is_encrypted_and_allowlisted_to_retired_app() -> None:
    source = (ROOT / "scripts" / "prod_snapshot_meta_social_rollback.sh").read_text(encoding="utf-8")
    assert 'OLD_APP_ID="1784792718776344"' in source
    assert "-aes-256-cbc" in source
    assert "-pbkdf2" in source
    assert 'chmod 600 "$archive_path"' in source


def test_restore_never_reactivates_compromised_verify_token() -> None:
    source = (ROOT / "scripts" / "prod_restore_meta_social_rollback.sh").read_text(encoding="utf-8")
    assert "META_WEBHOOK_VERIFY_TOKEN" in source
    assert "updates.update(" in source
    assert '"META_WEBHOOK_VERIFY_TOKEN": rotated_verify_token' in source
    assert '"META_SOCIAL_ROLLBACK_ACTIVE": "true"' in source
    assert "compromised_verify_token_restored=false" in source


def test_new_app_apply_disables_rollback_mode_and_rejects_retired_app() -> None:
    source = (ROOT / "scripts" / "prod_apply_meta_social_secrets.sh").read_text(encoding="utf-8")
    assert 'META_APP_ID" = "1784792718776344' in source
    assert 'updates["META_SOCIAL_ROLLBACK_ACTIVE"] = "false"' in source
    assert 'updates["META_SOCIAL_NEW_APP_REQUIRED"] = "true"' in source


def test_new_app_apply_proves_signed_whatsapp_is_handoff_only() -> None:
    source = (ROOT / "scripts" / "prod_apply_meta_social_secrets.sh").read_text(encoding="utf-8")
    assert "local_whatsapp_unsigned_http" in source
    assert "local_whatsapp_signed_http" in source
    assert "hmac.new(secret, body, hashlib.sha256)" in source
    assert 'signed[1].get("reason") != "whatsapp_inbound_ai_disabled"' in source
    assert 'signed[1].get("accepted") != 0' in source


def test_new_app_apply_uses_candidate_environment_and_cutover_lock() -> None:
    source = (ROOT / ".github" / "workflows" / "meta-social-secrets-apply.yml").read_text(encoding="utf-8")
    assert "environment: meta-social-cutover" in source
    assert "group: meta-social-cutover" in source


def test_atomic_cutover_is_environment_scoped_and_has_automatic_rollback() -> None:
    workflow = (ROOT / ".github" / "workflows" / "meta-social-atomic-cutover.yml").read_text(encoding="utf-8")
    script = (ROOT / "scripts" / "prod_cutover_meta_social.sh").read_text(encoding="utf-8")
    assert "environment: meta-social-cutover" in workflow
    assert "group: meta-social-cutover" in workflow
    assert "CUTOVER_VERIFIED_META_APP" in workflow
    assert "trap rollback_on_error ERR" in script
    assert 'python3 "$MANAGER" unsubscribe' in script
    assert 'python3 "$MANAGER" subscribe' in script
    assert "APPLY_ENABLE_MESSAGING=false" in script
    assert "APPLY_ENABLE_MESSAGING=true" in script
    assert script.index('phase="new_apply_started"') < script.index("APPLY_ENABLE_MESSAGING=false")


def test_manual_rollback_unsubscribes_new_before_restoring_old_subscription() -> None:
    script = (ROOT / "scripts" / "prod_rollback_meta_social.sh").read_text(encoding="utf-8")
    workflow = (ROOT / ".github" / "workflows" / "meta-social-rollback-restore.yml").read_text(encoding="utf-8")
    unsubscribe_at = script.index('python3 "$MANAGER" unsubscribe')
    restore_at = script.index('ROLLBACK_ENABLE_MESSAGING=false bash "$RESTORE"')
    subscribe_at = script.index('python3 "$MANAGER" subscribe', restore_at)
    assert unsubscribe_at < restore_at < subscribe_at
    assert "prod_rollback_meta_social.sh" in workflow
    assert "group: meta-social-cutover" in workflow
