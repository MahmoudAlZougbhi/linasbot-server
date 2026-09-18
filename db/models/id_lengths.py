"""Durable string lengths for provider and tenant-scoped operation keys.

Meta Instagram message IDs are already ~164 characters. Composite keys are
``tenant_id + ':' + provider_id`` (and ``llm:`` prefixes for expense events).
"""

from __future__ import annotations

# Original provider / inbound IDs (Meta mid, comment id, Graph event id).
PROVIDER_REF_MAX = 512
# tenant_id (128) + separator + PROVIDER_REF_MAX, or ``llm:`` + provider id.
COMPOSITE_REF_MAX = 640
