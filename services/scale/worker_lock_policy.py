"""Which job types may run without a per-conversation lock.

Inbound persist/buffer jobs must not hold the conversation lock across the
combine quiet period. Generate/flush/send jobs still serialize per conversation.
"""

from __future__ import annotations

# These jobs append to the shared combine buffer or persist inbound state.
# Holding ConversationLock here blocks the next message from joining the batch.
BUFFER_JOB_TYPES = frozenset(
    {
        "meta_inbound_process",
    }
)


def job_requires_conversation_lock(job_type: str) -> bool:
    kind = (job_type or "").strip()
    if kind in BUFFER_JOB_TYPES:
        return False
    return True
