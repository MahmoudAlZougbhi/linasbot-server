"""Shared SSE broadcaster for Live Chat events (local hub + optional Valkey fanout)."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import threading
from collections.abc import Awaitable, Callable
from datetime import datetime
from typing import Any

from fastapi import Request

from services.live_chat_contracts import utc_now

logger = logging.getLogger(__name__)

_PUBSUB_CHANNEL = (os.getenv("LINAS_LIVE_CHAT_SSE_CHANNEL") or "linas:live_chat:sse").strip()


def _json_serializer(obj: Any) -> Any:
    if isinstance(obj, datetime):
        return obj.isoformat()
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")


class LiveChatSSEBroadcaster:
    """Stateful SSE hub with robust connect/disconnect handling."""

    HEARTBEAT_SECONDS = 25
    CLIENT_QUEUE_SIZE = 64

    def __init__(self) -> None:
        self._clients: set[asyncio.Queue] = set()
        self._lock = asyncio.Lock()
        self._sequence = 0
        self._loop: asyncio.AbstractEventLoop | None = None
        self._pubsub_started = False
        self._origin = f"pid:{os.getpid()}:{id(self)}"

    async def _register(self) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue(maxsize=self.CLIENT_QUEUE_SIZE)
        async with self._lock:
            self._clients.add(queue)
            self._loop = asyncio.get_running_loop()
        self._ensure_pubsub_listener()
        return queue

    async def _unregister(self, queue: asyncio.Queue) -> None:
        async with self._lock:
            self._clients.discard(queue)

    async def _next_sequence(self) -> int:
        async with self._lock:
            self._sequence += 1
            return self._sequence

    async def _snapshot_clients(self) -> Any:
        async with self._lock:
            return list(self._clients)

    async def active_clients_count(self) -> int:
        async with self._lock:
            return len(self._clients)

    def _redis_client(self) -> Any | None:
        try:
            from services.queues.config import redis_url

            url = redis_url()
            if not url:
                return None
            import redis

            client = redis.Redis.from_url(
                url,
                decode_responses=True,
                socket_connect_timeout=1.5,
                socket_timeout=1.5,
            )
            client.ping()
            return client
        except Exception:
            return None

    def _ensure_pubsub_listener(self) -> None:
        if self._pubsub_started:
            return
        self._pubsub_started = True
        thread = threading.Thread(target=self._pubsub_loop, name="live-chat-sse-pubsub", daemon=True)
        thread.start()

    def _pubsub_loop(self) -> None:
        while True:
            client = self._redis_client()
            if client is None:
                time_sleep = __import__("time").sleep
                time_sleep(2.0)
                continue
            try:
                pubsub = client.pubsub(ignore_subscribe_messages=True)
                pubsub.subscribe(_PUBSUB_CHANNEL)
                for message in pubsub.listen():
                    if not message or message.get("type") != "message":
                        continue
                    raw = message.get("data")
                    if not isinstance(raw, str):
                        continue
                    try:
                        envelope = json.loads(raw)
                    except ValueError:
                        continue
                    if envelope.get("origin") == self._origin:
                        continue
                    event = envelope.get("event")
                    if not isinstance(event, dict):
                        continue
                    loop = self._loop
                    if loop is None:
                        continue
                    asyncio.run_coroutine_threadsafe(self._deliver_local(event), loop)
            except Exception as exc:
                logger.warning("live chat SSE pubsub reconnect: %s", type(exc).__name__)
                __import__("time").sleep(1.0)

    async def _deliver_local(self, event: dict[str, Any]) -> None:
        clients = await self._snapshot_clients()
        if not clients:
            return
        stale_clients = []
        for queue in clients:
            try:
                if queue.full():
                    queue.get_nowait()
                queue.put_nowait(event)
            except Exception:
                stale_clients.append(queue)
        if stale_clients:
            async with self._lock:
                for queue in stale_clients:
                    self._clients.discard(queue)

    def _publish_redis(self, event: dict[str, Any]) -> None:
        client = self._redis_client()
        if client is None:
            return
        try:
            payload = json.dumps({"origin": self._origin, "event": event}, default=_json_serializer)
            client.publish(_PUBSUB_CHANNEL, payload)
        except Exception as exc:
            logger.warning("live chat SSE redis publish failed: %s", type(exc).__name__)

    async def publish(self, event_type: str, data: dict[str, Any]) -> None:
        event = {
            "type": event_type,
            "data": data,
            "meta": {
                "sequence": await self._next_sequence(),
                "broadcast_at": utc_now().isoformat(),
            },
        }
        await self._deliver_local(event)
        await asyncio.to_thread(self._publish_redis, event)

    async def stream(
        self,
        request: Request,
        initial_payload_loader: Callable[[], Awaitable[dict[str, Any] | None]] | None = None,
    ) -> Any:
        """Yield a resilient SSE stream for one connected client."""
        client_queue = await self._register()
        connected_payload = {"status": "connected", "connected_at": utc_now().isoformat()}

        try:
            yield f"event: connected\ndata: {json.dumps(connected_payload, default=_json_serializer)}\n\n"

            if initial_payload_loader is not None:
                try:
                    initial_payload = await initial_payload_loader()
                    if initial_payload is not None:
                        yield f"event: conversations\ndata: {json.dumps(initial_payload, default=_json_serializer)}\n\n"
                except Exception as exc:
                    print(f"⚠️ SSE initial payload error: {exc}")

            while True:
                if await request.is_disconnected():
                    break

                try:
                    event = await asyncio.wait_for(client_queue.get(), timeout=self.HEARTBEAT_SECONDS)
                    event_data = json.dumps(event.get("data", {}), default=_json_serializer)
                    event_type = event.get("type", "message")
                    yield f"event: {event_type}\ndata: {event_data}\n\n"
                except TimeoutError:
                    heartbeat = {
                        "timestamp": utc_now().isoformat(),
                        "active_clients": await self.active_clients_count(),
                    }
                    yield f"event: heartbeat\ndata: {json.dumps(heartbeat)}\n\n"
        except asyncio.CancelledError:
            pass
        finally:
            await self._unregister(client_queue)


live_chat_sse_broadcaster = LiveChatSSEBroadcaster()
