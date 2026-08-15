"""FastAPI route registration and HTTP acceptance for Website Chat."""

from __future__ import annotations

from fastapi.routing import APIRoute

from tests.web_chat_acceptance_support import bootstrap_http, seed_acceptance_widget


def test_web_chat_routes_registered_on_app(acceptance_client) -> None:
    from main import app

    paths = {route.path for route in app.routes if isinstance(route, APIRoute)}
    expected = {
        "/api/web-chat/config",
        "/api/web-chat/heartbeat",
        "/api/web-chat/session",
        "/api/web-chat/session/messages",
        "/api/web-chat/session/poll",
        "/api/web-chat/session/ack",
        "/api/web-chat/sdk-docs",
        "/web-chat/widget.js",
        "/web-chat/sdk-docs",
    }
    missing = expected - paths
    assert not missing, f"missing routes: {sorted(missing)}"
    runtime = acceptance_client.get("/web-chat/widget-runtime.js")
    shared = acceptance_client.get("/web-chat/widget-runtime-shared.js")
    assert runtime.status_code == 200
    assert shared.status_code == 200
    assert "/api/web-chat/session/poll" in shared.text


def test_http_bootstrap_send_poll_ack_roundtrip(acceptance_client, acceptance_store, tmp_path, monkeypatch) -> None:
    from tests.web_chat_acceptance_support import patch_acceptance_eligibility, patch_ai_reply

    patch_acceptance_eligibility(monkeypatch, tmp_path)
    patch_ai_reply(monkeypatch)
    key, _tid = seed_acceptance_widget(acceptance_store)
    session = bootstrap_http(acceptance_client, key)
    headers = {"Origin": "https://shop.example.com"}

    sent = acceptance_client.post(
        "/api/web-chat/session/messages",
        json={
            "session_id": session["session_id"],
            "session_authority": session["session_authority"],
            "widget_key": key,
            "content": "Need help",
            "client_message_key": "route-roundtrip-key-1",
        },
        headers=headers,
    )
    assert sent.status_code == 200
    assert sent.json()["success"] is True
    assert sent.json()["reply"]

    acceptance_store.queue_assistant_message(
        session["session_id"],
        "Background follow-up",
        idempotency_key="sfu:http:1",
    )
    polled = acceptance_client.post(
        "/api/web-chat/session/poll",
        json={
            "session_id": session["session_id"],
            "session_authority": session["session_authority"],
            "widget_key": key,
            "cursor": None,
        },
        headers=headers,
    )
    assert polled.status_code == 200
    messages = polled.json()["messages"]
    assert any(m["content"] == "Background follow-up" for m in messages)

    acked = acceptance_client.post(
        "/api/web-chat/session/ack",
        json={
            "session_id": session["session_id"],
            "session_authority": session["session_authority"],
            "widget_key": key,
            "message_ids": ["sfu:http:1"],
        },
        headers=headers,
    )
    assert acked.status_code == 200
    assert acked.json()["acked"] == 1

    again = acceptance_client.post(
        "/api/web-chat/session/poll",
        json={
            "session_id": session["session_id"],
            "session_authority": session["session_authority"],
            "widget_key": key,
            "cursor": polled.json().get("cursor"),
        },
        headers=headers,
    )
    assert again.status_code == 200
    assert again.json()["messages"] == []


def test_static_widget_assets_served(acceptance_client) -> None:
    widget = acceptance_client.get("/web-chat/widget.js")
    runtime = acceptance_client.get("/web-chat/widget-runtime.js")
    shared = acceptance_client.get("/web-chat/widget-runtime-shared.js")
    docs = acceptance_client.get("/api/web-chat/sdk-docs")
    assert widget.status_code == 200
    assert runtime.status_code == 200
    assert shared.status_code == 200
    assert docs.status_code == 200
    assert "data-widget-key" in widget.text
    assert "widget-runtime-shared.js" in widget.text
    assert "LinasWebChat" in runtime.text
    assert "/api/web-chat/session/poll" in shared.text
    assert "/api/web-chat/session/poll" in docs.text
