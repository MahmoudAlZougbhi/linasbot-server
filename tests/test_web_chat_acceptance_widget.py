"""Browser-level widget protocol acceptance (shipped runtime + live HTTP)."""

from __future__ import annotations

import pytest
from sqlalchemy import func, select

from services.web_chat.pg_models import WebChatMessageRow, WebChatOperationRow
from tests.web_chat_acceptance_support import (
    bootstrap_http,
    node_available,
    patch_acceptance_eligibility,
    patch_ai_reply,
    run_widget_protocol_harness,
    seed_acceptance_widget,
    seed_prefix_widget_pair,
)

_ORIGIN = "https://shop.example.com"


def _send(
    client,
    key: str,
    session: dict,
    content: str,
    *,
    client_message_key: str | None = None,
) -> dict:
    payload = {
        "session_id": session["session_id"],
        "session_authority": session["session_authority"],
        "widget_key": key,
        "content": content,
    }
    if client_message_key is not None:
        payload["client_message_key"] = client_message_key
    res = client.post(
        "/api/web-chat/session/messages",
        json=payload,
        headers={"Origin": "https://shop.example.com"},
    )
    return {"status_code": res.status_code, "body": res.json()}


def _count_user_turns(web_chat_ha_db, session_id: str, content: str) -> int:
    with web_chat_ha_db() as db:
        return int(
            db.execute(
                select(func.count())
                .select_from(WebChatMessageRow)
                .where(
                    WebChatMessageRow.session_id == session_id,
                    WebChatMessageRow.role == "user",
                    WebChatMessageRow.content == content,
                )
            ).scalar_one()
        )


def _count_operations(web_chat_ha_db, session_id: str) -> int:
    with web_chat_ha_db() as db:
        return int(
            db.execute(
                select(func.count())
                .select_from(WebChatOperationRow)
                .where(WebChatOperationRow.session_id == session_id)
            ).scalar_one()
        )


def test_shipped_runtime_exports_init(
    acceptance_client,
    acceptance_store,
    tmp_path,
    monkeypatch,
) -> None:
    """Served widget assets compose shared HTTP helpers with poll/ack orchestration."""
    widget = acceptance_client.get("/web-chat/widget.js")
    shared_resp = acceptance_client.get("/web-chat/widget-runtime-shared.js")
    runtime_resp = acceptance_client.get("/web-chat/widget-runtime.js")
    assert widget.status_code == 200
    assert shared_resp.status_code == 200
    assert runtime_resp.status_code == 200

    shared = shared_resp.text
    runtime = runtime_resp.text

    assert "widget-runtime-shared.js" in widget.text
    assert "widget-runtime.js" in widget.text
    assert "global.LinasWebChat = {" in runtime
    assert "global.LinasWebChatShared = {" in shared
    assert "widgetStorageDigest" in shared
    assert "newClientMessageKey" in shared
    assert "client_message_key" in shared
    assert "createApi" in shared
    assert "pollFollowups" in runtime
    assert "flushAckQueue" in runtime
    assert "api.poll" in runtime
    assert "api.ack" in runtime
    assert "/api/web-chat/session/poll" not in runtime
    assert "/api/web-chat/session/ack" not in runtime
    assert "widgetKey.slice(0, 12)" not in runtime
    assert "widgetKey.slice(0, 12)" not in shared

    patch_acceptance_eligibility(monkeypatch, tmp_path)
    key, _tid = seed_acceptance_widget(acceptance_store)
    session = bootstrap_http(acceptance_client, key)
    headers = {"Origin": _ORIGIN}

    acceptance_store.queue_assistant_message(
        session["session_id"],
        "Shipped runtime follow-up",
        idempotency_key="sfu:shipped-runtime:1",
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
    poll_body = polled.json()
    messages = poll_body["messages"]
    assert any(m["content"] == "Shipped runtime follow-up" for m in messages)
    poll_cursor = poll_body.get("cursor")
    assert poll_cursor

    acked = acceptance_client.post(
        "/api/web-chat/session/ack",
        json={
            "session_id": session["session_id"],
            "session_authority": session["session_authority"],
            "widget_key": key,
            "message_ids": ["sfu:shipped-runtime:1"],
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
            "cursor": poll_cursor,
        },
        headers=headers,
    )
    assert again.status_code == 200
    assert again.json()["messages"] == []


def test_node_harness_requires_node() -> None:
    assert node_available(), "Node.js is required for widget protocol harness"


@pytest.mark.integration
def test_widget_protocol_bootstrap_followup_ack_reload_no_duplicate(
    acceptance_live_server, acceptance_store, acceptance_client, monkeypatch
) -> None:
    patch_ai_reply(monkeypatch)
    key, _tid = seed_acceptance_widget(acceptance_store)
    session = bootstrap_http(acceptance_client, key)
    acceptance_store.queue_assistant_message(
        session["session_id"],
        "Node harness follow-up",
        idempotency_key="sfu:node:bootstrap:1",
    )
    result = run_widget_protocol_harness(
        scenario="bootstrap_followup_ack_reload",
        api_base=acceptance_live_server,
        widget_key=key,
        extra_env={
            "WEB_CHAT_SESSION_ID": session["session_id"],
            "WEB_CHAT_SESSION_AUTHORITY": session["session_authority"],
        },
    )
    assert result["ok"] is True
    assert result["assistant_before_reload"] >= 1
    assert result["reload_assistant_count"] <= result["assistant_before_reload"]
    assert len(set(result.get("reload_assistant_ids", []))) == result["reload_assistant_count"]


@pytest.mark.integration
def test_widget_protocol_lost_poll_ack_recovery(
    acceptance_live_server, acceptance_store, acceptance_client, monkeypatch
) -> None:
    patch_ai_reply(monkeypatch)
    key, _tid = seed_acceptance_widget(acceptance_store)
    session = bootstrap_http(acceptance_client, key)
    acceptance_store.queue_assistant_message(
        session["session_id"],
        "Node harness follow-up",
        idempotency_key="sfu:node:lost:1",
    )
    result = run_widget_protocol_harness(
        scenario="lost_poll_ack",
        api_base=acceptance_live_server,
        widget_key=key,
        extra_env={
            "WEB_CHAT_SESSION_ID": session["session_id"],
            "WEB_CHAT_SESSION_AUTHORITY": session["session_authority"],
        },
    )
    assert result["ok"] is True
    assert result["retry_poll_count"] >= 1
    assert result["after_ack_count"] == 0
    assert result["reload_assistant_count"] == 1
    assert len(result["pre_reload_assistant_ids"]) == 1
    assert result["reload_assistant_ids"] == result["pre_reload_assistant_ids"]
    assert len(set(result["reload_assistant_ids"])) == 1


@pytest.mark.integration
def test_widget_protocol_repeated_ack_failure_then_recovery(
    acceptance_live_server, acceptance_store, acceptance_client, monkeypatch
) -> None:
    patch_ai_reply(monkeypatch)
    key, _tid = seed_acceptance_widget(acceptance_store)
    session = bootstrap_http(acceptance_client, key)
    acceptance_store.queue_assistant_message(
        session["session_id"],
        "Node harness follow-up",
        idempotency_key="sfu:node:repeat-ack:1",
    )
    result = run_widget_protocol_harness(
        scenario="repeated_ack_failure_recovery",
        api_base=acceptance_live_server,
        widget_key=key,
        extra_env={
            "WEB_CHAT_SESSION_ID": session["session_id"],
            "WEB_CHAT_SESSION_AUTHORITY": session["session_authority"],
        },
    )
    assert result["ok"] is True
    assert result["followup_assistant_count"] == 1
    assert result["after_ack_count"] == 0
    assert len(result["ack_attempts"]) >= 4
    assert len(result["ack_requests"]) >= 1


@pytest.mark.integration
def test_widget_protocol_two_widgets_same_prefix_isolated(acceptance_live_server, acceptance_store) -> None:
    key_a, key_b = seed_prefix_widget_pair(acceptance_store)
    assert key_a[:12] == key_b[:12]
    result = run_widget_protocol_harness(
        scenario="two_widgets_same_prefix",
        api_base=acceptance_live_server,
        widget_key=key_a,
        extra_env={"WEB_CHAT_WIDGET_KEY_B": key_b},
    )
    assert result["ok"] is True
    assert result["session_a"] != result["session_b"]
    assert result["digest_a"] != result["digest_b"]
    assert result["cross_read"] is False
    assert result["overwrite"] is False
    assert result["shared_prefix_collision"] is False
    assert len(result["storage_keys"]) == 6


@pytest.mark.integration
def test_client_message_key_same_key_same_payload_is_canonical(
    acceptance_client,
    acceptance_store,
    web_chat_ha_db,
    tmp_path,
    monkeypatch,
) -> None:
    patch_acceptance_eligibility(monkeypatch, tmp_path)
    patch_ai_reply(monkeypatch)
    key, _tid = seed_acceptance_widget(acceptance_store)
    session = bootstrap_http(acceptance_client, key)
    client_key = "client-msg-canonical-1"

    first = _send(acceptance_client, key, session, "Need help", client_message_key=client_key)
    second = _send(acceptance_client, key, session, "Need help", client_message_key=client_key)

    assert first["status_code"] == 200
    assert second["status_code"] == 200
    assert first["body"]["reply"] == second["body"]["reply"]
    assert _count_user_turns(web_chat_ha_db, session["session_id"], "Need help") == 1
    assert _count_operations(web_chat_ha_db, session["session_id"]) == 1


@pytest.mark.integration
def test_client_message_key_same_key_different_payload_conflicts(
    acceptance_client,
    acceptance_store,
    tmp_path,
    monkeypatch,
) -> None:
    patch_acceptance_eligibility(monkeypatch, tmp_path)
    patch_ai_reply(monkeypatch)
    key, _tid = seed_acceptance_widget(acceptance_store)
    session = bootstrap_http(acceptance_client, key)
    client_key = "client-msg-conflict-1"

    ok = _send(acceptance_client, key, session, "First wording", client_message_key=client_key)
    conflict = _send(acceptance_client, key, session, "Second wording", client_message_key=client_key)

    assert ok["status_code"] == 200
    assert conflict["status_code"] == 409
    assert conflict["body"]["error"] == "operation_conflict"


@pytest.mark.integration
def test_client_message_key_different_keys_same_text_two_turns(
    acceptance_client,
    acceptance_store,
    web_chat_ha_db,
    tmp_path,
    monkeypatch,
) -> None:
    patch_acceptance_eligibility(monkeypatch, tmp_path)
    patch_ai_reply(monkeypatch)
    key, _tid = seed_acceptance_widget(acceptance_store)
    session = bootstrap_http(acceptance_client, key)

    first = _send(
        acceptance_client,
        key,
        session,
        "Same text twice",
        client_message_key="client-msg-dup-text-a",
    )
    second = _send(
        acceptance_client,
        key,
        session,
        "Same text twice",
        client_message_key="client-msg-dup-text-b",
    )

    assert first["status_code"] == 200
    assert second["status_code"] == 200
    assert _count_user_turns(web_chat_ha_db, session["session_id"], "Same text twice") == 2
    assert _count_operations(web_chat_ha_db, session["session_id"]) == 2
