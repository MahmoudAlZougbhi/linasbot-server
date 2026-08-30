"""HTTP redelivery after terminal inbound states must ACK 200 without enqueue."""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest
from starlette.requests import Request

from modules import meta_messaging_webhook
from services.meta_inbound_deletion_fence import (
    InboundBindingDeletionFencedError,
    InboundDeletionFenceStoreError,
)
from services.scale.inbound_event_store import TERMINAL_STATES, InboundEventRecord
from services.scale.meta_ingress import enqueue_meta_inbound_event
from services.scale.meta_webhook_accept import accept_meta_dm_events

APP_SECRET = "terminal-redelivery-secret"
PAGE_ID = "378696005334409"


def _sign(body: bytes) -> str:
    return "sha256=" + hmac.new(APP_SECRET.encode(), body, hashlib.sha256).hexdigest()


def _dm_body(*, mid: str) -> bytes:
    payload = {
        "object": "page",
        "entry": [
            {
                "id": PAGE_ID,
                "time": 1,
                "messaging": [
                    {
                        "sender": {"id": "tester-1"},
                        "recipient": {"id": PAGE_ID},
                        "timestamp": 1,
                        "message": {"mid": mid, "text": "LINAS_SAFETY_TEST"},
                    }
                ],
            }
        ],
    }
    return json.dumps(payload, separators=(",", ":")).encode()


def _request(body: bytes) -> Request:
    sent = False

    async def receive() -> dict[str, Any]:
        nonlocal sent
        if sent:
            return {"type": "http.request", "body": b"", "more_body": False}
        sent = True
        return {"type": "http.request", "body": body, "more_body": False}

    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/webhook/meta-messaging",
            "query_string": b"",
            "headers": [(b"x-hub-signature-256", _sign(body).encode())],
        },
        receive,
    )


def _record(*, state: str) -> InboundEventRecord:
    now = 1.0
    return InboundEventRecord(
        event_id="ibe_" + "a" * 40,
        kind="meta_dm",
        tenant_id="linas",
        claim_namespace="meta_social_dm_global",
        claim_key="facebook:page:mid",
        state=state,  # type: ignore[arg-type]
        created_at=now,
        updated_at=now,
        payload={"message_id": "mid-term"},
        binding_snapshot={"binding_id": "bind-1"},
        settings_snapshot={"binding_id": "bind-1"},
    )


def _install_http_mocks(monkeypatch: pytest.MonkeyPatch, *, persist) -> list[str]:
    enqueued: list[str] = []
    monkeypatch.setattr(meta_messaging_webhook, "_background_tasks", set())
    monkeypatch.setattr(meta_messaging_webhook, "meta_multi_app_registry_enabled", lambda: True)
    monkeypatch.setattr(
        meta_messaging_webhook,
        "identify_signed_meta_app",
        lambda _b, _s: SimpleNamespace(key="linas_first_party", app_secret=APP_SECRET),
    )
    monkeypatch.setattr(
        meta_messaging_webhook,
        "get_meta_messaging_settings",
        lambda: SimpleNamespace(enabled=True, app_secret=APP_SECRET),
    )
    event = {
        "channel": "facebook",
        "account_id": PAGE_ID,
        "message_id": "mid-term",
        "sender_id": "tester-1",
        "text": "LINAS_SAFETY_TEST",
    }
    binding = SimpleNamespace(
        binding_id="bind-1",
        tenant_id="linas",
        channel="facebook",
        app_key="linas_first_party",
        asset_id=PAGE_ID,
        auth_flow="facebook_login",
    )
    resolved = SimpleNamespace(event=event, binding=binding, settings=SimpleNamespace())
    monkeypatch.setattr(meta_messaging_webhook, "resolve_registry_events", AsyncMock(return_value=[resolved]))
    monkeypatch.setattr(meta_messaging_webhook, "resolve_registry_comment_events", lambda *a, **k: [])
    monkeypatch.setattr(meta_messaging_webhook, "count_raw_comment_changes", lambda _p: 0)
    monkeypatch.setattr("services.scale.meta_ingress.persist_meta_dm_accepted", persist)

    def _enqueue(event_id: str, **_k: Any) -> str:
        enqueued.append(event_id)
        raise AssertionError("redelivery must not enqueue")

    monkeypatch.setattr("services.scale.meta_ingress.enqueue_meta_inbound_event", _enqueue)
    return enqueued


@pytest.mark.parametrize("state", sorted(TERMINAL_STATES))
@pytest.mark.asyncio
async def test_http_terminal_redelivery_acks_duplicate(monkeypatch: pytest.MonkeyPatch, state: str) -> None:
    def persist(*_a: object, **_k: object) -> tuple[str, bool]:
        return ("ibe_" + "a" * 40, False)

    enqueued = _install_http_mocks(monkeypatch, persist=persist)
    monkeypatch.setattr("services.scale.meta_ingress.get_inbound_event", lambda *_a, **_k: _record(state=state))
    body = _dm_body(mid="mid-term")
    response = await meta_messaging_webhook.receive_meta_messaging_webhook(_request(body))
    payload = json.loads(response.body)
    assert response.status_code == 200
    assert payload["accepted"] == 0
    assert payload["duplicates"] == 1
    assert enqueued == []


@pytest.mark.parametrize("state", sorted(TERMINAL_STATES))
@pytest.mark.asyncio
async def test_http_one_hundred_concurrent_terminal_redeliveries(monkeypatch: pytest.MonkeyPatch, state: str) -> None:
    def persist(*_a: object, **_k: object) -> tuple[str, bool]:
        return ("ibe_" + "a" * 40, False)

    enqueued = _install_http_mocks(monkeypatch, persist=persist)

    async def _one() -> dict[str, Any]:
        body = _dm_body(mid="mid-term")
        response = await meta_messaging_webhook.receive_meta_messaging_webhook(_request(body))
        return {"http": response.status_code, **json.loads(response.body)}

    results = await asyncio.gather(*[_one() for _ in range(100)])
    assert [row["http"] for row in results] == [200] * 100
    assert all(row["accepted"] == 0 and row["duplicates"] == 1 for row in results)
    assert enqueued == []


def test_enqueue_skips_every_terminal_state_without_redis() -> None:
    for state in sorted(TERMINAL_STATES):
        assert enqueue_meta_inbound_event("ibe_x", record=_record(state=state)) == "duplicate_terminal"


@pytest.mark.asyncio
async def test_deletion_fence_acks_without_row(monkeypatch: pytest.MonkeyPatch) -> None:
    def persist(*_a: object, **_k: object) -> tuple[str, bool]:
        raise InboundBindingDeletionFencedError("Meta authorization is being deleted")

    enqueued = _install_http_mocks(monkeypatch, persist=persist)
    response = await meta_messaging_webhook.receive_meta_messaging_webhook(_request(_dm_body(mid="mid-f")))
    payload = json.loads(response.body)
    assert response.status_code == 200
    assert payload["accepted"] == 0
    assert payload["duplicates"] == 1
    assert enqueued == []


@pytest.mark.asyncio
async def test_deletion_fence_store_failure_is_fail_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    def persist(*_a: object, **_k: object) -> tuple[str, bool]:
        raise InboundDeletionFenceStoreError("Firestore inbound fence store is unavailable")

    _install_http_mocks(monkeypatch, persist=persist)
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc:
        await meta_messaging_webhook.receive_meta_messaging_webhook(_request(_dm_body(mid="mid-s")))
    assert exc.value.status_code == 503


def test_ingress_probe_skips_when_ports_closed() -> None:
    import asyncio

    from services.scale.ingress_listener_ready import probe_local_ingress_listeners

    result = asyncio.run(probe_local_ingress_listeners())
    assert result["ok"] is True
    assert result.get("skipped") is True


def test_ingress_probe_rejects_502(monkeypatch: pytest.MonkeyPatch) -> None:
    import asyncio

    import services.scale.ingress_listener_ready as probe_mod

    monkeypatch.setattr(probe_mod, "_port_open", lambda port: port == 8003)

    class _Resp:
        status_code = 502

    class _Client:
        async def __aenter__(self) -> _Client:
            return self

        async def __aexit__(self, *_a: object) -> None:
            return None

        async def post(self, *_a: object, **_k: object) -> _Resp:
            return _Resp()

    monkeypatch.setattr(probe_mod.httpx, "AsyncClient", lambda **_k: _Client())
    result = asyncio.run(probe_mod.probe_local_ingress_listeners())
    assert result["ok"] is False


def test_ingress_probe_lb_http_uses_forwarded_proto(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import asyncio

    import services.scale.ingress_listener_ready as probe_mod

    monkeypatch.setattr(probe_mod, "_port_open", lambda port: port in {8003, 80, 443})
    seen: list[tuple[str, dict[str, str], bool]] = []

    class _Resp:
        def __init__(self, status_code: int) -> None:
            self.status_code = status_code

    class _Client:
        def __init__(self, *, verify: bool = True, **_k: object) -> None:
            self.verify = verify

        async def __aenter__(self) -> _Client:
            return self

        async def __aexit__(self, *_a: object) -> None:
            return None

        async def post(self, url: str, *_a: object, headers: dict[str, str] | None = None, **_k: object) -> _Resp:
            hdrs = dict(headers or {})
            seen.append((url, hdrs, self.verify))
            return _Resp(401)

    monkeypatch.setattr(probe_mod.httpx, "AsyncClient", lambda **kwargs: _Client(**kwargs))
    result = asyncio.run(probe_mod.probe_local_ingress_listeners())
    assert result["ok"] is True
    http_nginx = [item for item in seen if item[0].startswith("http://127.0.0.1/webhook")]
    tls_nginx = [item for item in seen if item[0].startswith("https://127.0.0.1/")]
    assert http_nginx
    assert tls_nginx
    assert all(item[1].get("X-Forwarded-Proto") == "https" for item in http_nginx)
    assert all(item[2] is False for item in tls_nginx)


def test_ingress_probe_rejects_nginx_301(monkeypatch: pytest.MonkeyPatch) -> None:
    import asyncio

    import services.scale.ingress_listener_ready as probe_mod

    monkeypatch.setattr(probe_mod, "_port_open", lambda port: port == 80)

    class _Resp:
        status_code = 301

    class _Client:
        async def __aenter__(self) -> _Client:
            return self

        async def __aexit__(self, *_a: object) -> None:
            return None

        async def post(self, *_a: object, **_k: object) -> _Resp:
            return _Resp()

    monkeypatch.setattr(probe_mod.httpx, "AsyncClient", lambda **_k: _Client())
    result = asyncio.run(probe_mod.probe_local_ingress_listeners())
    assert result["ok"] is False
    assert result["probes"]["meta_nginx"]["http"] == 301


def test_one_hundred_threads_never_call_enqueue(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = {"enqueue": 0}

    def persist(*_a: object, **_k: object) -> tuple[str, bool]:
        return ("ibe_" + "b" * 40, False)

    monkeypatch.setattr("services.scale.meta_ingress.persist_meta_dm_accepted", persist)

    def boom(*_a: object, **_k: object) -> str:
        calls["enqueue"] += 1
        raise AssertionError("enqueue")

    monkeypatch.setattr("services.scale.meta_ingress.enqueue_meta_inbound_event", boom)
    resolved = SimpleNamespace(
        event={"channel": "facebook", "account_id": PAGE_ID, "message_id": "m"},
        binding=SimpleNamespace(binding_id="b", channel="facebook"),
        settings=SimpleNamespace(),
    )

    def _once() -> None:
        asyncio.run(
            accept_meta_dm_events(
                [resolved],
                track_task=lambda *_a, **_k: None,
                process_dm=AsyncMock(),
            )
        )

    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(lambda _i: _once(), range(100)))
    assert calls["enqueue"] == 0
