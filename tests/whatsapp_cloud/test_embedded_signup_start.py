"""Embedded Signup start validation — fail closed before attempt creation."""

from __future__ import annotations

import os

import pytest

os.environ["LINAS_WHATSAPP_ALLOW_SQLITE"] = "true"
os.environ["META_CREDENTIAL_ENCRYPTION_KEY"] = "x" * 32
os.environ["META_APP_A_ID"] = "2963733803971681"
os.environ["META_APP_A_SECRET"] = "test-app-a-secret"
os.environ["META_APP_A_WEBHOOK_VERIFY_TOKEN"] = "test-verify-token"
os.environ["META_WHATSAPP_EMBEDDED_SIGNUP_CONFIG_ID"] = "es-config-test"
os.environ["WHATSAPP_CLOUD_CONNECTION_UI_ENABLED"] = "true"
os.environ["WHATSAPP_CLOUD_PUBLIC_AVAILABILITY"] = "true"
os.environ["PUBLIC_URL"] = "https://example.test"

from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from db.models import Base  # noqa: E402
from db.session import reset_engine_for_tests  # noqa: E402
from services.whatsapp_cloud.embedded_signup import (  # noqa: E402
    WhatsAppSignupError,
    start_embedded_signup,
)
from services.whatsapp_cloud.repository import WhatsAppCloudRepository  # noqa: E402


@pytest.fixture()
def wa_db(tmp_path, monkeypatch):
    url = f"sqlite:///{tmp_path / 'wa.db'}"
    monkeypatch.setenv("LINAS_WHATSAPP_DATABASE_URL", url)
    monkeypatch.setenv("LINAS_WHATSAPP_ALLOW_SQLITE", "true")
    monkeypatch.setenv("WHATSAPP_CLOUD_PUBLIC_AVAILABILITY", "true")
    monkeypatch.setenv("META_WHATSAPP_EMBEDDED_SIGNUP_CONFIG_ID", "es-config-test")
    monkeypatch.setenv("PUBLIC_URL", "https://example.test")
    monkeypatch.setenv("META_APP_A_ID", "2963733803971681")
    reset_engine_for_tests()
    engine = create_engine(url, future=True)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    session = Session()
    yield session
    session.close()
    reset_engine_for_tests()


def _grant_whatsapp_plan(monkeypatch, tmp_path, tenant_id: str, plan_id: str = "starter") -> None:
    from services import entitlements_service as es
    from services.entitlements_service import EntitlementsStore
    from services.membership import whatsapp_gate as wg

    store = EntitlementsStore(root=tmp_path / "ent-wa-plan")
    monkeypatch.setattr(es, "entitlements_store", store)
    monkeypatch.setattr(wg, "entitlements_store", store)
    monkeypatch.setenv("SUBSCRIPTION_EXEMPT_TENANT_IDS", "linas")
    store.set_plan(tenant_id=tenant_id, plan_id=plan_id, status="active", source="admin")


def test_start_embedded_signup_returns_https_bridge_url(wa_db, monkeypatch, tmp_path):
    monkeypatch.setenv("WHATSAPP_CLOUD_PUBLIC_AVAILABILITY", "true")
    _grant_whatsapp_plan(monkeypatch, tmp_path, "t1")
    result = start_embedded_signup(tenant_id="t1", actor_user_id="u1", return_surface="mobile")
    assert result["success"] is True
    assert result["authorization_url"].startswith("https://example.test/integrations/whatsapp/embedded-signup?")
    assert "config_id=es-config-test" in result["authorization_url"]
    assert "feature_type=whatsapp_business_app_onboarding" in result["authorization_url"]
    assert result["feature_type"] == "whatsapp_business_app_onboarding"
    assert "state=" in result["authorization_url"]


def test_start_rejects_missing_config_id(wa_db, monkeypatch):
    monkeypatch.delenv("META_WHATSAPP_EMBEDDED_SIGNUP_CONFIG_ID", raising=False)
    with pytest.raises(WhatsAppSignupError) as exc:
        start_embedded_signup(tenant_id="t1", actor_user_id="u1", return_surface="mobile")
    assert exc.value.code == "embedded_signup_config_missing"
    assert exc.value.http_status == 503


def test_start_rejects_missing_bridge_url(wa_db, monkeypatch):
    monkeypatch.delenv("PUBLIC_URL", raising=False)
    monkeypatch.delenv("LINAS_PUBLIC_URL", raising=False)
    monkeypatch.delenv("META_WHATSAPP_EMBEDDED_SIGNUP_BRIDGE_URL", raising=False)
    with pytest.raises(WhatsAppSignupError) as exc:
        start_embedded_signup(tenant_id="t1", actor_user_id="u1", return_surface="mobile")
    assert exc.value.code == "bridge_url_misconfigured"


def test_start_rejects_non_pilot_when_public_off(wa_db, monkeypatch, tmp_path):
    monkeypatch.setenv("WHATSAPP_CLOUD_PUBLIC_AVAILABILITY", "false")
    monkeypatch.setenv("WHATSAPP_CLOUD_REQUIRE_PILOT_ENTITLEMENT", "true")
    _grant_whatsapp_plan(monkeypatch, tmp_path, "not-pilot")
    with pytest.raises(Exception) as exc:
        start_embedded_signup(tenant_id="not-pilot", actor_user_id="u1", return_surface="mobile")
    assert "WHATSAPP_PILOT_REQUIRED" in str(exc.value) or getattr(exc.value, "code", "") == "WHATSAPP_PILOT_REQUIRED"


def test_nginx_snippet_proxies_whatsapp_bridge():
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    full = (root / "deploy" / "nginx-linasaibot.conf").read_text(encoding="utf-8")
    include = (root / "deploy" / "nginx-api-include.conf").read_text(encoding="utf-8")
    assert "location ^~ /integrations/whatsapp/" in full
    assert "location ^~ /integrations/whatsapp/" in include
    assert "proxy_pass http://127.0.0.1:8003" in full


def test_pilot_grant_allows_start(wa_db, monkeypatch, tmp_path):
    monkeypatch.setenv("WHATSAPP_CLOUD_PUBLIC_AVAILABILITY", "false")
    monkeypatch.setenv("WHATSAPP_CLOUD_REQUIRE_PILOT_ENTITLEMENT", "true")
    _grant_whatsapp_plan(monkeypatch, tmp_path, "pilot-t")
    repo = WhatsAppCloudRepository(wa_db)
    repo.grant_pilot(tenant_id="pilot-t", granted_by_user_id="owner", reason="test")
    wa_db.commit()
    result = start_embedded_signup(tenant_id="pilot-t", actor_user_id="u1", return_surface="mobile")
    assert result["success"] is True
    assert "config_id=es-config-test" in result["authorization_url"]
