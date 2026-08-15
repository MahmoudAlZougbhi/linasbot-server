"""Readiness, HA, compliance, and OAuth completion reuse the closed-set evaluator."""

from __future__ import annotations

import json
import os
from pathlib import Path
from unittest import mock

import pytest
from fastapi.testclient import TestClient

from modules import dashboard_api_health
from services.meta_data_deletion import MetaDeletionResult
from services.meta_instagram_login_oauth import complete_instagram_login
from services.meta_oauth import MetaOAuthError
from services.meta_surface_secret_separation import (
    CONFIG_COLLISION_KEY,
    SIGNING_COLLISION,
    VERIFY_COLLISION,
    env_file_values,
    evaluate_meta_surface_secret_separation,
    evaluate_meta_surface_signing_separation,
)
from tests.meta_compliance_helpers import APP_A_ENV, APP_SECRET, _signed_request
from tests.test_meta_surface_secret_separation import (
    FB_CANON_SIGN,
    FB_CANON_VERIFY,
    FB_LEGACY_SIGN,
    FB_LEGACY_VERIFY,
    IG_SIGN,
    IG_VERIFY,
    SECRET_MARKERS,
    SHARED_VERIFY,
)

ROOT = Path(__file__).resolve().parents[1]
INSTAGRAM_APP_ID = "1035856539045307"
INSTAGRAM_APP_SECRET = "instagram-login-secret-for-tests"


def _assert_no_secret_leak(haystack: str) -> None:
    for marker in (*SECRET_MARKERS, APP_SECRET, INSTAGRAM_APP_SECRET):
        assert marker not in haystack


def _valid_instagram_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("META_APP_A_ID", "2963733803971681")
    monkeypatch.setenv("META_APP_A_SECRET", FB_CANON_SIGN)
    monkeypatch.setenv("META_APP_SECRET", FB_CANON_SIGN)
    monkeypatch.setenv("META_APP_A_WEBHOOK_VERIFY_TOKEN", FB_CANON_VERIFY)
    monkeypatch.setenv("META_WEBHOOK_VERIFY_TOKEN", FB_CANON_VERIFY)
    monkeypatch.setenv("META_APP_A_ADVANCED_ACCESS_APPROVED", "true")
    monkeypatch.setenv("META_INSTAGRAM_LOGIN_APP_ID", INSTAGRAM_APP_ID)
    monkeypatch.setenv("META_INSTAGRAM_LOGIN_APP_SECRET", IG_SIGN)
    monkeypatch.setenv("META_INSTAGRAM_LOGIN_WEBHOOK_VERIFY_TOKEN", IG_VERIFY)
    monkeypatch.setenv(
        "META_INSTAGRAM_LOGIN_REDIRECT_URI",
        "https://www.linasaibot.com/oauth/instagram/callback",
    )
    monkeypatch.setenv("META_INSTAGRAM_LOGIN_WEBHOOK_PATH", "/webhook/instagram-login")
    monkeypatch.setenv("PUBLIC_URL", "https://www.linasaibot.com")


@pytest.mark.asyncio
async def test_ready_fails_closed_when_second_facebook_signing_alias_collides(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("LINAS_SERVICE_ROLE", raising=False)
    monkeypatch.delenv("LINAS_MAINTENANCE_DRAIN_FILE", raising=False)
    _valid_instagram_env(monkeypatch)
    monkeypatch.setenv("META_APP_SECRET", IG_SIGN)
    response = await dashboard_api_health.ready()
    payload = json.loads(response.body)
    assert payload["checks"]["meta_surface_secret_separation"]["ok"] is False
    assert response.status_code == 503
    _assert_no_secret_leak(json.dumps(payload))


def test_ha_verifier_source_and_evaluator_reject_second_alias_collision(tmp_path: Path) -> None:
    source = (ROOT / "scripts" / "ha" / "verify_meta_release_ha.sh").read_text(encoding="utf-8")
    assert "operator_gate_allows_separation" in source
    assert "COLLISION_EXIT" in source
    env_path = tmp_path / ".env"
    env_path.write_text(
        "\n".join(
            [
                f"META_APP_A_SECRET={FB_CANON_SIGN}",
                f"META_APP_SECRET={IG_SIGN}",
                f"META_INSTAGRAM_LOGIN_APP_SECRET={IG_SIGN}",
                "META_REGISTRY_BACKEND=postgres",
                "META_HA_LB_READY_HEALTHCHECK_APPROVED=true",
                "META_HA_LB_DRAIN_SECONDS=60",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    result = evaluate_meta_surface_secret_separation(env_file_values(env_path))
    assert result.ok is False
    _assert_no_secret_leak(" ".join(result.collisions))


def test_compliance_fails_closed_when_legacy_facebook_alias_equals_instagram(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import modules.meta_compliance  # noqa: F401
    from modules.core import app

    for key, value in APP_A_ENV.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setenv("META_INSTAGRAM_LOGIN_APP_ID", INSTAGRAM_APP_ID)
    monkeypatch.setenv("META_INSTAGRAM_LOGIN_APP_SECRET", INSTAGRAM_APP_SECRET)
    monkeypatch.setenv("META_APP_SECRET", INSTAGRAM_APP_SECRET)
    client = TestClient(app)
    with mock.patch("modules.meta_compliance.delete_meta_social_user_data") as delete_mock:
        response = client.post(
            "/oauth/instagram/data-deletion",
            data={"signed_request": _signed_request(secret=INSTAGRAM_APP_SECRET)},
        )
    assert response.status_code == 503
    delete_mock.assert_not_called()
    _assert_no_secret_leak(response.text)


def _compliance_client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    import modules.meta_compliance  # noqa: F401
    from modules.core import app

    for key, value in APP_A_ENV.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setenv("META_APP_SECRET", APP_SECRET)
    monkeypatch.setenv("META_WEBHOOK_VERIFY_TOKEN", "verify-legacy-tests")
    monkeypatch.setenv("META_INSTAGRAM_LOGIN_APP_ID", INSTAGRAM_APP_ID)
    monkeypatch.setenv("META_INSTAGRAM_LOGIN_APP_SECRET", IG_SIGN)
    monkeypatch.setenv("META_INSTAGRAM_LOGIN_WEBHOOK_VERIFY_TOKEN", IG_VERIFY)
    return TestClient(app)


def test_signing_only_evaluator_ignores_verify_alias_disagreement() -> None:
    values = {
        "META_APP_A_SECRET": FB_CANON_SIGN,
        "META_APP_SECRET": FB_CANON_SIGN,
        "META_APP_A_WEBHOOK_VERIFY_TOKEN": FB_CANON_VERIFY,
        "META_WEBHOOK_VERIFY_TOKEN": FB_LEGACY_VERIFY,
        "META_INSTAGRAM_LOGIN_APP_SECRET": IG_SIGN,
        "META_INSTAGRAM_LOGIN_WEBHOOK_VERIFY_TOKEN": IG_VERIFY,
    }
    full = evaluate_meta_surface_secret_separation(values)
    signing = evaluate_meta_surface_signing_separation(values)
    assert full.ok is False
    assert signing.ok is True


def test_signing_only_evaluator_ignores_verify_cross_surface_collision() -> None:
    values = {
        "META_APP_A_SECRET": FB_CANON_SIGN,
        "META_APP_SECRET": FB_CANON_SIGN,
        "META_APP_A_WEBHOOK_VERIFY_TOKEN": SHARED_VERIFY,
        "META_WEBHOOK_VERIFY_TOKEN": SHARED_VERIFY,
        "META_INSTAGRAM_LOGIN_APP_SECRET": IG_SIGN,
        "META_INSTAGRAM_LOGIN_WEBHOOK_VERIFY_TOKEN": SHARED_VERIFY,
    }
    full = evaluate_meta_surface_secret_separation(values)
    signing = evaluate_meta_surface_signing_separation(values)
    assert full.ok is False
    assert signing.ok is True


def test_signing_only_evaluator_detects_app_b_signing_collision() -> None:
    values = {
        "META_APP_A_SECRET": FB_CANON_SIGN,
        "META_APP_SECRET": FB_CANON_SIGN,
        "META_APP_B_SECRET": IG_SIGN,
        "META_INSTAGRAM_LOGIN_APP_SECRET": IG_SIGN,
    }
    signing = evaluate_meta_surface_signing_separation(values)
    assert signing.ok is False
    assert signing.collisions == (SIGNING_COLLISION,)


@pytest.mark.asyncio
async def test_ready_still_fails_closed_on_verify_alias_disagreement(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("LINAS_SERVICE_ROLE", raising=False)
    monkeypatch.delenv("LINAS_MAINTENANCE_DRAIN_FILE", raising=False)
    _valid_instagram_env(monkeypatch)
    monkeypatch.setenv("META_WEBHOOK_VERIFY_TOKEN", FB_LEGACY_VERIFY)
    response = await dashboard_api_health.ready()
    payload = json.loads(response.body)
    assert payload["checks"]["meta_surface_secret_separation"]["ok"] is False
    assert response.status_code == 503
    _assert_no_secret_leak(json.dumps(payload))


def test_compliance_accepts_deletion_when_only_facebook_verify_aliases_disagree(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _compliance_client(monkeypatch)
    monkeypatch.setenv("META_APP_A_WEBHOOK_VERIFY_TOKEN", FB_CANON_VERIFY)
    monkeypatch.setenv("META_WEBHOOK_VERIFY_TOKEN", FB_LEGACY_VERIFY)
    with mock.patch(
        "modules.meta_compliance.delete_meta_social_user_data",
        return_value=MetaDeletionResult(
            confirmation_code="b" * 32,
            deleted_user_documents=1,
            deleted_nested_documents=0,
            deleted_index_documents=0,
        ),
    ) as delete_mock:
        response = client.post(
            "/oauth/meta/data-deletion",
            data={"signed_request": _signed_request()},
        )
    assert response.status_code == 200
    delete_mock.assert_called_once()
    _assert_no_secret_leak(response.text)


def test_compliance_accepts_deauthorization_when_verify_tokens_collide_across_surfaces(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _compliance_client(monkeypatch)
    monkeypatch.setenv("META_APP_A_WEBHOOK_VERIFY_TOKEN", SHARED_VERIFY)
    monkeypatch.setenv("META_WEBHOOK_VERIFY_TOKEN", SHARED_VERIFY)
    monkeypatch.setenv("META_INSTAGRAM_LOGIN_WEBHOOK_VERIFY_TOKEN", SHARED_VERIFY)
    registry = mock.Mock()
    with (
        mock.patch("modules.meta_compliance.get_meta_app_registry", return_value=registry),
        mock.patch("modules.meta_compliance.acquire_meta_deauthorization_subject_guard") as guard_mock,
    ):
        guard = guard_mock.return_value.__enter__.return_value
        response = client.post(
            "/oauth/meta/deauthorize",
            data={"signed_request": _signed_request()},
        )
    assert response.status_code == 200
    guard.record_deauthorization.assert_called_once()
    registry.revoke_authorization.assert_called_once()
    _assert_no_secret_leak(response.text)


def test_compliance_fails_closed_when_facebook_signing_aliases_disagree(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _compliance_client(monkeypatch)
    monkeypatch.setenv("META_APP_SECRET", FB_LEGACY_SIGN)
    with mock.patch("modules.meta_compliance.delete_meta_social_user_data") as delete_mock:
        response = client.post(
            "/oauth/meta/data-deletion",
            data={"signed_request": _signed_request()},
        )
    assert response.status_code == 503
    delete_mock.assert_not_called()
    _assert_no_secret_leak(response.text)


def test_compliance_fails_closed_when_app_b_signing_equals_instagram(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _compliance_client(monkeypatch)
    monkeypatch.setenv("META_INSTAGRAM_LOGIN_APP_SECRET", INSTAGRAM_APP_SECRET)
    monkeypatch.setenv("META_APP_B_SECRET", INSTAGRAM_APP_SECRET)
    with mock.patch("modules.meta_compliance.delete_meta_social_user_data") as delete_mock:
        response = client.post(
            "/oauth/instagram/data-deletion",
            data={"signed_request": _signed_request(secret=INSTAGRAM_APP_SECRET)},
        )
    assert response.status_code == 503
    delete_mock.assert_not_called()
    _assert_no_secret_leak(response.text)


@pytest.mark.asyncio
async def test_ready_fails_closed_when_app_b_verify_collides_with_instagram(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("LINAS_SERVICE_ROLE", raising=False)
    monkeypatch.delenv("LINAS_MAINTENANCE_DRAIN_FILE", raising=False)
    _valid_instagram_env(monkeypatch)
    monkeypatch.setenv("META_APP_B_WEBHOOK_VERIFY_TOKEN", IG_VERIFY)
    response = await dashboard_api_health.ready()
    payload = json.loads(response.body)
    separation = payload["checks"]["meta_surface_secret_separation"]
    assert separation["ok"] is False
    assert separation["collisions"] == [VERIFY_COLLISION]
    assert response.status_code == 503
    _assert_no_secret_leak(json.dumps(payload))
    assert os.getenv("META_APP_A_WEBHOOK_VERIFY_TOKEN") == FB_CANON_VERIFY
    assert os.getenv("META_WEBHOOK_VERIFY_TOKEN") == FB_CANON_VERIFY
    assert os.getenv("META_INSTAGRAM_LOGIN_WEBHOOK_VERIFY_TOKEN") == IG_VERIFY


@pytest.mark.asyncio
async def test_complete_instagram_login_rejects_before_secret_use(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _valid_instagram_env(monkeypatch)
    monkeypatch.setenv("META_APP_SECRET", IG_SIGN)
    with pytest.raises(MetaOAuthError, match=CONFIG_COLLISION_KEY) as raised:
        await complete_instagram_login(code="auth-code", state="state-token")
    _assert_no_secret_leak(str(raised.value))
