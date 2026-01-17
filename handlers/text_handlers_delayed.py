# handlers/text_handlers_delayed.py
# Handles delayed message processing (message combining)

from handlers.text_handlers_firestore import *
from handlers.text_handlers_respond import _process_and_respond


async def _delayed_process_messages(user_id: str, user_data: dict, send_message_func, send_action_func):
    """
    Delays processing to combine rapid messages from the same user.
    """
    try:
        await send_action_func(user_id)  # Send typing indicator
        await asyncio.sleep(config.MESSAGE_COMBINING_DELAY)

        if config.user_pending_messages[user_id]:
            combined_message = " ".join(config.user_pending_messages[user_id])
            config.user_pending_messages[user_id].clear()

            await _process_and_respond(
                user_id, 
                user_name=config.user_names.get(user_id, "عميل"),
                user_input_to_process=combined_message,
                user_data=user_data,
                send_message_func=send_message_func,
                send_action_func=send_action_func
            )
            config.user_last_bot_response_time[user_id] = datetime.datetime.now()
        else:
            pass  # Queue was empty

    except asyncio.CancelledError:
        pass  # Task was cancelled
    except Exception as e:
        print(f"[_delayed_process_messages] ERROR: An error occurred in delayed processing for user {user_id}: {e}")
        import traceback
        traceback.print_exc()
