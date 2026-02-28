# handlers/text_handlers_delayed.py
# Handles delayed message processing (message combining)
# Waits 3 seconds after LAST message, merges all, sends ONE reply. Concurrency-safe for webhook.

from handlers.text_handlers_firestore import *
from handlers.text_handlers_firestore import get_message_merge_lock
from handlers.text_handlers_respond import _process_and_respond


async def _delayed_process_messages(user_id: str, user_data: dict, send_message_func, send_action_func):
    """
    Waits 3 seconds after LAST message, merges all rapid messages, sends ONE reply.
    Concurrency-safe for WhatsApp webhook.
    """
    try:
        await send_action_func(user_id)  # Send typing indicator
        await asyncio.sleep(config.MESSAGE_COMBINING_DELAY)

        # Concurrency-safe: acquire lock, copy messages, clear, release
        lock = await get_message_merge_lock(user_id)
        async with lock:
            messages = list(config.user_pending_messages.get(user_id, []))
            if user_id in config.user_pending_messages:
                config.user_pending_messages[user_id].clear()
            if user_id in _delayed_processing_tasks:
                del _delayed_processing_tasks[user_id]

        if messages:
            combined_message = " ".join(messages)
            await _process_and_respond(
                user_id,
                user_name=config.user_names.get(user_id, "عميل"),
                user_input_to_process=combined_message,
                user_data=user_data,
                send_message_func=send_message_func,
                send_action_func=send_action_func
            )
            config.user_last_bot_response_time[user_id] = datetime.datetime.now()

    except asyncio.CancelledError:
        pass  # Task was cancelled (new message arrived, new task scheduled)
    except Exception as e:
        print(f"[_delayed_process_messages] ERROR: An error occurred in delayed processing for user {user_id}: {e}")
        import traceback
        traceback.print_exc()
