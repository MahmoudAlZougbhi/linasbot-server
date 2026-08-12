"""Scale / HA primitives: queues, locks, backpressure, shutdown, readiness."""

from __future__ import annotations

from services.scale.conversation_lock import ConversationLock
from services.scale.distributed_lock import DistributedLock
from services.scale.provider_limiter import ProviderLimiter
from services.scale.queue_protocol import DurableQueue, QueueMetrics
from services.scale.shutdown import ShutdownCoordinator, shutdown_coordinator

__all__ = [
    "ConversationLock",
    "DistributedLock",
    "DurableQueue",
    "ProviderLimiter",
    "QueueMetrics",
    "ShutdownCoordinator",
    "shutdown_coordinator",
]
