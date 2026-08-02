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
