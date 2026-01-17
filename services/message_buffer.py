# Message Buffering Service
# Implements requirement #9 from project specifications

import asyncio
from typing import Dict, List, Optional
from datetime import datetime, timedelta
from collections import defaultdict

class MessageBuffer:
    """
    Buffers multiple messages from same user within 2.5 seconds
    Combines them into single message before processing
    """
    
    def __init__(self, buffer_time: float = 2.5):
        self.buffer_time = buffer_time  # seconds
        self.buffers: Dict[str, List[Dict]] = defaultdict(list)
        self.timers: Dict[str, asyncio.Task] = {}
        self.callbacks: Dict[str, callable] = {}
    
    async def add_message(
        self, 
        user_id: str, 
        message: str, 
        message_type: str = "text",
        callback: callable = None
    ) -> bool:
        """
        Add message to buffer
        Returns True if message is buffered, False if should process immediately
        """
        
        # For non-text messages, process immediately
        if message_type != "text":
            return False
        
        # Add message to buffer
        self.buffers[user_id].append({
            "message": message,
            "timestamp": datetime.now(),
            "type": message_type
        })
        
        # Store callback
        if callback:
            self.callbacks[user_id] = callback
        
        # Cancel existing timer if any
        if user_id in self.timers:
            self.timers[user_id].cancel()
        
        # Start new timer
        self.timers[user_id] = asyncio.create_task(
            self._process_buffer_after_delay(user_id)
        )
        
        return True
    
    async def _process_buffer_after_delay(self, user_id: str):
        """Wait for buffer time then process all messages"""
        await asyncio.sleep(self.buffer_time)
        
        # Get all buffered messages
        messages = self.buffers[user_id]
        if not messages:
            return
        
        # Combine messages
        combined_message = self._combine_messages(messages)
        
        # Clear buffer
        del self.buffers[user_id]
        if user_id in self.timers:
            del self.timers[user_id]
        
        # Call callback with combined message
        if user_id in self.callbacks:
            callback = self.callbacks[user_id]
            del self.callbacks[user_id]
            
            # Execute callback
            if asyncio.iscoroutinefunction(callback):
                await callback(user_id, combined_message)
            else:
                callback(user_id, combined_message)
    
    def _combine_messages(self, messages: List[Dict]) -> str:
        """Combine multiple messages into one"""
        if len(messages) == 1:
            return messages[0]["message"]
        
        # Check if messages are continuation of each other
        combined_parts = []
        for msg in messages:
            text = msg["message"].strip()
            if text:
                combined_parts.append(text)
        
        # Join with space if they seem like continuation
        # Join with newline if they seem like separate points
        combined = " ".join(combined_parts)
        
        # Clean up multiple spaces
        combined = " ".join(combined.split())
        
        return combined
    
    def get_buffer_status(self, user_id: str) -> Dict:
        """Get current buffer status for user"""
        if user_id not in self.buffers:
            return {"buffering": False, "message_count": 0}
        
        return {
            "buffering": True,
            "message_count": len(self.buffers[user_id]),
            "messages": [m["message"] for m in self.buffers[user_id]],
            "first_message_time": self.buffers[user_id][0]["timestamp"] if self.buffers[user_id] else None
        }
    
    def clear_buffer(self, user_id: str):
        """Clear buffer for specific user"""
        if user_id in self.buffers:
            del self.buffers[user_id]
        if user_id in self.timers:
            self.timers[user_id].cancel()
            del self.timers[user_id]
        if user_id in self.callbacks:
            del self.callbacks[user_id]

# Global instance
message_buffer = MessageBuffer(buffer_time=2.5)