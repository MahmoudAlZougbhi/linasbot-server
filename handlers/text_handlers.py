from __future__ import annotations

# handlers/text_handlers.py
# Parent module importing all text handler parts
# (no logic, just clean aggregation)
from handlers.text_handlers_delayed import _delayed_process_messages
from handlers.text_handlers_firestore import _delayed_processing_tasks
from handlers.text_handlers_message import handle_message
from handlers.text_handlers_respond import _process_and_respond
from handlers.text_handlers_start import start_command
from handlers.VERSION import BUILD_ID, LAST_MODIFIED, VERSION, print_version_info

# Print version info when module is loaded
print_version_info()

# Export version info
__version__ = VERSION
__build_id__ = BUILD_ID
__last_modified__ = LAST_MODIFIED

__all__ = [
    "start_command",
    "handle_message",
    "_delayed_process_messages",
    "_process_and_respond",
    "_delayed_processing_tasks",
    "__version__",
    "__last_modified__",
    "__build_id__",
]
