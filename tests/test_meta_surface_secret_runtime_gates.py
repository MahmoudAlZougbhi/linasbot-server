"""Readiness, HA, compliance, and OAuth completion reuse the closed-set evaluator."""

from __future__ import annotations

import json
from pathlib import Path
from unittest import mock

import pytest
from fastapi.testclient import TestClient

from modules import dashboard_api_health
from services.meta_instagram_login_oauth import complete_instagram_login
from services.meta_oauth import MetaOAuthError
from services.meta_surface_secret_separation import (
    CONFIG_COLLISION_KEY,
    env_file_values,
    evaluate_meta_surface_secret_separation,
)
from tests.meta_compliance_helpers import APP_A_ENV, APP_SECRET, _signed_request
from tests.test_meta_surface_secret_separation import (
    FB_CANON_SIGN,
    FB_CANON_VERIFY,
    IG_SIGN,
    IG_VERIFY,
    SECRET_MARKERS,
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
    assert "evaluate_meta_surface_secret_separation" in source
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


@pytest.mark.asyncio
async def test_complete_instagram_login_rejects_before_secret_use(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _valid_instagram_env(monkeypatch)
    monkeypatch.setenv("META_APP_SECRET", IG_SIGN)
    with pytest.raises(MetaOAuthError, match=CONFIG_COLLISION_KEY) as raised:
        await complete_instagram_login(code="auth-code", state="state-token")
    _assert_no_secret_leak(str(raised.value))
