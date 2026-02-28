# Message Buffering Service
# Implements requirement #9 from project specifications
# Concurrency-safe for WhatsApp webhook (multiple rapid messages from same user)

import asyncio
from typing import Dict, List, Optional
from datetime import datetime, timedelta
from collections import defaultdict
import logging

logger = logging.getLogger(__name__)


class MessageBuffer:
    """
    Buffers multiple messages from same user within configurable seconds (default 3).
    Waits 3 seconds after LAST message, then combines all into single message before processing.
    Concurrency-safe for webhook: uses asyncio.Lock per user.
    """

    def __init__(self, buffer_time: float = 3.0):
        self.buffer_time = buffer_time  # seconds (wait after LAST message)
        self.buffers: Dict[str, List[Dict]] = defaultdict(list)
        self.timers: Dict[str, asyncio.Task] = {}
        self.callbacks: Dict[str, callable] = {}
        self._locks: Dict[str, asyncio.Lock] = {}
        self._dict_lock: Optional[asyncio.Lock] = None  # Created lazily when event loop exists

    def _ensure_dict_lock(self) -> asyncio.Lock:
        """Create _dict_lock lazily (requires event loop)."""
        if self._dict_lock is None:
            self._dict_lock = asyncio.Lock()
        return self._dict_lock

    async def _get_lock(self, user_id: str) -> asyncio.Lock:
        """Get or create lock for user_id. Concurrency-safe."""
        async with self._ensure_dict_lock():
            if user_id not in self._locks:
                self._locks[user_id] = asyncio.Lock()
            return self._locks[user_id]

    async def add_message(
        self,
        user_id: str,
        message: str,
        message_type: str = "text",
        callback: callable = None
    ) -> bool:
        """
        Add message to buffer.
        Returns True if message is buffered, False if should process immediately.
        Concurrency-safe: uses lock per user.
        """
        # For non-text messages, process immediately
        if message_type != "text":
            return False

        lock = await self._get_lock(user_id)
        async with lock:
            # Add message to buffer
            self.buffers[user_id].append({
                "message": message,
                "timestamp": datetime.now(),
                "type": message_type
            })

            # Store callback
            if callback:
                self.callbacks[user_id] = callback

            # Cancel existing timer if any (reset: wait 3s after THIS last message)
            if user_id in self.timers:
                try:
                    self.timers[user_id].cancel()
                except asyncio.CancelledError:
                    pass
                del self.timers[user_id]

            # Start new timer (3 seconds after THIS message = last so far)
            self.timers[user_id] = asyncio.create_task(
                self._process_buffer_after_delay(user_id)
            )

        return True

    async def _process_buffer_after_delay(self, user_id: str):
        """Wait for buffer time after last message, then process all messages."""
        try:
            await asyncio.sleep(self.buffer_time)
        except asyncio.CancelledError:
            return

        lock = await self._get_lock(user_id)
        async with lock:
            # Get all buffered messages
            messages = list(self.buffers.get(user_id, []))
            if not messages:
                return

            # Clear buffer and timer
            if user_id in self.buffers:
                del self.buffers[user_id]
            if user_id in self.timers:
                del self.timers[user_id]

            callback = self.callbacks.pop(user_id, None)

        # Combine and invoke callback outside lock to avoid deadlock
        combined_message = self._combine_messages(messages)

        if callback:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(user_id, combined_message)
                else:
                    callback(user_id, combined_message)
            except Exception as e:
                logger.exception(f"MessageBuffer callback error for {user_id}: {e}")

    def _combine_messages(self, messages: List[Dict]) -> str:
        """Combine multiple messages into one."""
        if len(messages) == 1:
            return messages[0]["message"]

        combined_parts = []
        for msg in messages:
            text = msg["message"].strip()
            if text:
                combined_parts.append(text)

        combined = " ".join(combined_parts)
        combined = " ".join(combined.split())
        return combined

    def get_buffer_status(self, user_id: str) -> Dict:
        """Get current buffer status for user."""
        if user_id not in self.buffers:
            return {"buffering": False, "message_count": 0}

        return {
            "buffering": True,
            "message_count": len(self.buffers[user_id]),
            "messages": [m["message"] for m in self.buffers[user_id]],
            "first_message_time": self.buffers[user_id][0]["timestamp"] if self.buffers[user_id] else None
        }

    async def clear_buffer(self, user_id: str):
        """Clear buffer for specific user. Concurrency-safe."""
        lock = await self._get_lock(user_id)
        async with lock:
            if user_id in self.buffers:
                del self.buffers[user_id]
            if user_id in self.timers:
                try:
                    self.timers[user_id].cancel()
                except asyncio.CancelledError:
                    pass
                del self.timers[user_id]
            if user_id in self.callbacks:
                del self.callbacks[user_id]


# Global instance: 3 seconds after LAST message
message_buffer = MessageBuffer(buffer_time=3.0)
