"""Shared SSE broadcaster for Live Chat events."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime
from typing import Any, Awaitable, Callable, Dict, Optional, Set

from fastapi import Request

from services.live_chat_contracts import utc_now


def _json_serializer(obj):
    if isinstance(obj, datetime):
        return obj.isoformat()
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")


class LiveChatSSEBroadcaster:
    """Stateful SSE hub with robust connect/disconnect handling."""

    HEARTBEAT_SECONDS = 25
    CLIENT_QUEUE_SIZE = 64

    def __init__(self):
        self._clients: Set[asyncio.Queue] = set()
        self._lock = asyncio.Lock()
        self._sequence = 0

    async def _register(self) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue(maxsize=self.CLIENT_QUEUE_SIZE)
        async with self._lock:
            self._clients.add(queue)
        return queue

    async def _unregister(self, queue: asyncio.Queue) -> None:
        async with self._lock:
            self._clients.discard(queue)

    async def _next_sequence(self) -> int:
        async with self._lock:
            self._sequence += 1
            return self._sequence

    async def _snapshot_clients(self):
        async with self._lock:
            return list(self._clients)

    async def active_clients_count(self) -> int:
        async with self._lock:
            return len(self._clients)

    async def publish(self, event_type: str, data: Dict[str, Any]) -> None:
        clients = await self._snapshot_clients()
        if not clients:
            return

        event = {
            "type": event_type,
            "data": data,
            "meta": {
                "sequence": await self._next_sequence(),
                "broadcast_at": utc_now().isoformat(),
            },
        }

        stale_clients = []
        for queue in clients:
            try:
                if queue.full():
                    # Prevent stalled clients from blocking the broadcaster forever.
                    queue.get_nowait()
                queue.put_nowait(event)
            except Exception:
                stale_clients.append(queue)

        if stale_clients:
            async with self._lock:
                for queue in stale_clients:
                    self._clients.discard(queue)

    async def stream(
        self,
        request: Request,
        initial_payload_loader: Optional[Callable[[], Awaitable[Optional[Dict[str, Any]]]]] = None,
    ):
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
                except asyncio.TimeoutError:
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
