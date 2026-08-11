"""Authz matrix and IDOR guards for WhatsApp Cloud APIs."""

from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("LINAS_WHATSAPP_ALLOW_SQLITE", "true")
os.environ.setdefault("META_CREDENTIAL_ENCRYPTION_KEY", "y" * 32)
os.environ.setdefault("META_APP_A_ID", "2963733803971681")
os.environ.setdefault("META_APP_A_SECRET", "secret-a")
os.environ.setdefault("META_APP_A_WEBHOOK_VERIFY_TOKEN", "verify-a")
os.environ.setdefault("META_WHATSAPP_EMBEDDED_SIGNUP_CONFIG_ID", "cfg")
os.environ.setdefault("WHATSAPP_CLOUD_CONNECTION_UI_ENABLED", "true")
os.environ.setdefault("DASHBOARD_AUTH_SECRET", "pytest-dashboard-secret")
os.environ.setdefault("PUBLIC_URL", "https://example.test")


@pytest.fixture()
def client(tmp_path, monkeypatch):
    url = f"sqlite:///{tmp_path / 'wa_api.db'}"
    monkeypatch.setenv("LINAS_WHATSAPP_DATABASE_URL", url)
    monkeypatch.setenv("LINAS_WHATSAPP_ALLOW_SQLITE", "true")
    from db.models import Base
    from db.session import reset_engine_for_tests

    reset_engine_for_tests()
    engine = create_engine(url, future=True)
    Base.metadata.create_all(engine)

    # Import app after env is set.
    from modules.core import app

    with TestClient(app) as c:
        yield c
    reset_engine_for_tests()


def test_anonymous_status_requires_auth(client):
    res = client.get("/api/whatsapp/cloud/status")
    assert res.status_code in {401, 403}


def test_cross_tenant_conversation_idor(tmp_path, monkeypatch):
    url = f"sqlite:///{tmp_path / 'idor.db'}"
    monkeypatch.setenv("LINAS_WHATSAPP_DATABASE_URL", url)
    monkeypatch.setenv("LINAS_WHATSAPP_ALLOW_SQLITE", "true")
    from db.models import Base
    from db.session import reset_engine_for_tests
    from services.whatsapp_cloud.repository import WhatsAppCloudRepository

    reset_engine_for_tests()
    engine = create_engine(url, future=True)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, future=True)
    s = Session()
    repo = WhatsAppCloudRepository(s)
    conn = repo.create_connection_with_credential(
        tenant_id="tenant_a",
        created_by_user_id="u1",
        meta_app_key="linas_first_party",
        meta_app_id="2963733803971681",
        waba_id="1",
        phone_number_id="pn_idor",
        display_phone_number="+96170000000",
        verified_name="A",
        access_token="t",
        scopes=["whatsapp_business_management", "whatsapp_business_messaging"],
    )
    conv = repo.get_or_create_conversation(
        tenant_id="tenant_a", connection_id=conn.id, customer_wa_id="96171111111"
    )
    s.commit()
    assert repo.get_tenant_conversation(tenant_id="tenant_b", conversation_id=conv.id) is None
    assert repo.get_tenant_connection(tenant_id="tenant_b", connection_id=conn.id) is None
    s.close()
    reset_engine_for_tests()
