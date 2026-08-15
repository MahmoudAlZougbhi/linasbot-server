"""HTTP-level Web Chat API tests."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from services.web_chat.store import WebChatStore
from services.web_chat.store_pg import WebChatPgStore


async def _fake_process(**_kwargs) -> str:
    return "Hello from custom UI"


@pytest.fixture()
def web_store(tmp_path, monkeypatch):
    store = WebChatStore(root=tmp_path / "web_chat")
    monkeypatch.setattr("services.web_chat.store.web_chat_store", store)
    monkeypatch.setattr("modules.web_chat_helpers.web_chat_store", store)
    monkeypatch.setattr("modules.web_chat_public_routes.web_chat_store", store)
    monkeypatch.setattr("services.web_chat.public_handlers.web_chat_store", store)
    monkeypatch.setattr("services.web_chat.delivery_outbox.web_chat_store", store)
    monkeypatch.setattr("modules.web_chat_mobile_routes.web_chat_store", store)
    return store


@pytest.fixture()
def client(monkeypatch, web_store):
    monkeypatch.setenv("WEB_CHAT_PUBLIC_AVAILABILITY", "true")
    from services import entitlements_service as es
    from services.entitlements_service import EntitlementsStore
    from services.membership import web_gate as wg

    ent = EntitlementsStore(root=web_store._root.parent / "ent")
    monkeypatch.setattr(es, "entitlements_store", ent)
    monkeypatch.setattr(wg, "entitlements_store", ent)
    ent.set_plan(tenant_id="biz", plan_id="max", status="active", source="admin")

    from main import app

    return TestClient(app)


def _seed_widget(store: WebChatStore) -> tuple[str, str]:
    widget = store.update_widget(
        "biz",
        site_url="https://shop.example.com",
        enabled=True,
        integration_mode="linas_widget",
    )
    return widget.widget_key, widget.tenant_id


def _seed_widget_pg(store: WebChatPgStore) -> tuple[str, str]:
    widget = store.update_widget(
        "biz",
        site_url="https://shop.example.com",
        enabled=True,
        integration_mode="linas_widget",
    )
    return widget.widget_key, widget.tenant_id


@pytest.fixture()
def pg_client(monkeypatch, web_chat_pg_store, tmp_path) -> TestClient:
    monkeypatch.setenv("WEB_CHAT_PUBLIC_AVAILABILITY", "true")
    from main import app

    return TestClient(app)


def _bootstrap(client: TestClient, key: str) -> dict:
    res = client.post(
        "/api/web-chat/session",
        json={"widget_key": key},
        headers={"Origin": "https://shop.example.com"},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["session_authority"]
    assert body["session_id"]
    return body


def test_public_config_and_heartbeat(client, web_store, monkeypatch) -> None:
    key, _tid = _seed_widget(web_store)
    monkeypatch.setattr(
        "services.web_chat.processor.evaluate_web_ai_eligibility",
        lambda *_a, **_k: (True, None),
    )

    cfg = client.get(
        f"/api/web-chat/config?widget_key={key}",
        headers={"Origin": "https://shop.example.com"},
    )
    assert cfg.status_code == 200
    body = cfg.json()
    assert body["success"] is True
    assert body["config"]["integration_mode"] == "linas_widget"
    assert body["config"]["appearance"]["identity"]["display_name"]

    hb = client.post(
        "/api/web-chat/heartbeat",
        json={"widget_key": key},
        headers={"Origin": "https://www.shop.example.com"},
    )
    assert hb.status_code == 200
    updated = web_store.get_widget_by_key(key)
    assert updated is not None
    assert updated.installation.last_seen_at is not None


def test_origin_reject_and_server_issued_session(client, web_store, monkeypatch) -> None:
    key, _tid = _seed_widget(web_store)
    monkeypatch.setattr(
        "services.web_chat.processor.evaluate_web_ai_eligibility",
        lambda *_a, **_k: (True, None),
    )
    bad = client.post(
        "/api/web-chat/session",
        json={"widget_key": key},
        headers={"Origin": "https://evil.example"},
    )
    assert bad.status_code == 403

    ok = _bootstrap(client, key)
    assert ok["channel"] == "web"


def test_custom_chat_mode_still_reports_web_channel(client, web_store, monkeypatch) -> None:
    key, _tid = _seed_widget(web_store)
    web_store.update_widget("biz", integration_mode="custom_chat")
    monkeypatch.setattr(
        "services.web_chat.processor.evaluate_web_ai_eligibility",
        lambda *_a, **_k: (True, None),
    )
    monkeypatch.setattr(
        "services.web_chat.public_handlers.process_web_chat_message",
        _fake_process,
    )

    session = _bootstrap(client, key)

    msg = client.post(
        "/api/web-chat/session/messages",
        json={
            "session_id": session["session_id"],
            "session_authority": session["session_authority"],
            "widget_key": key,
            "content": "Need pricing",
        },
        headers={"Origin": "https://shop.example.com"},
    )
    assert msg.status_code == 200
    assert msg.json()["channel"] == "web"
    assert msg.json()["reply"] == "Hello from custom UI"


def test_poll_and_ack_endpoints(pg_client, web_chat_pg_store, monkeypatch) -> None:
    store = web_chat_pg_store
    key, _tid = _seed_widget_pg(store)
    monkeypatch.setattr(
        "services.web_chat.processor.evaluate_web_ai_eligibility",
        lambda *_a, **_k: (True, None),
    )
    session = _bootstrap(pg_client, key)
    visitor = store.get_visitor(session["session_id"])
    assert visitor is not None
    store.queue_assistant_message(session["session_id"], "Follow up", idempotency_key="sfu:1")
    headers = {"Origin": "https://shop.example.com"}
    body = {
        "session_id": session["session_id"],
        "session_authority": session["session_authority"],
        "widget_key": key,
    }

    polled = pg_client.post("/api/web-chat/session/poll", json=body, headers=headers)
    assert polled.status_code == 200
    assert polled.json()["messages"][0]["content"] == "Follow up"

    acked = pg_client.post(
        "/api/web-chat/session/ack",
        json={**body, "message_ids": ["sfu:1"]},
        headers=headers,
    )
    assert acked.status_code == 200
    assert acked.json()["acked"] == 1


def test_mobile_payload_includes_mode_and_installation(client, web_store, monkeypatch) -> None:
    key, _tid = _seed_widget(web_store)
    web_store.record_installation_heartbeat(
        web_store.get_widget_by_key(key),  # type: ignore[arg-type]
        origin="https://shop.example.com",
    )
    monkeypatch.setattr(
        "services.web_chat.processor.evaluate_web_ai_eligibility",
        lambda *_a, **_k: (True, None),
    )

    from services.dashboard_session_service import SESSION_COOKIE_NAME, session_service

    session = session_service.create_session(
        user_id="u-web",
        email="web@example.com",
        role="admin",
        permissions=None,
        tenant_id="biz",
    )
    token = session_service.cookie_value_for(session)

    res = client.get("/api/mobile/web-chat", cookies={SESSION_COOKIE_NAME: token})
    assert res.status_code == 200
    payload = res.json()["web_chat"]
    assert payload["integration_mode"] == "linas_widget"
    assert payload["membership_allows"] is True
    assert payload["installation"]["installed"] is True
    assert payload["installation_status"] in {"connected", "waiting", "domain_mismatch", "disabled"}


def test_legacy_widget_without_appearance_gets_defaults(web_store) -> None:
    web_store.get_or_create_widget("legacy")
    raw_path = web_store._tenant_path("legacy")
    raw_path.write_text(
        '{"tenant_id":"legacy","widget_key":"k123456789012345678901234","site_url":"","enabled":false,'
        '"created_at":1,"updated_at":1}',
        encoding="utf-8",
    )
    loaded = web_store.get_or_create_widget("legacy")
    assert loaded.appearance["theme"]["mode"] == "light"
    assert loaded.integration_mode == "linas_widget"


def test_widget_disabled_blocks_config(client, web_store) -> None:
    widget = web_store.update_widget("biz", site_url="https://shop.example.com", enabled=False)
    res = client.get(f"/api/web-chat/config?widget_key={widget.widget_key}")
    assert res.status_code == 403
