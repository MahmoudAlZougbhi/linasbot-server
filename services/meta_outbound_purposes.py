"""Meta outbound purpose identities for at-most-once HA sends.

Each purpose has its own attempt document. Sibling purposes may both send for
the same inbound event without weakening primary_reply duplicate protection.
"""

from __future__ import annotations

from typing import Literal

MetaOutboundPurpose = Literal[
    "primary_reply",
    "session_greeting",
    "gender_ack",
    "image_quota_notice",
    "comment_private_dm",
    "product_media",
]

ALLOWED_PURPOSES = frozenset(
    {
        "primary_reply",
        "session_greeting",
        "gender_ack",
        "image_quota_notice",
        "comment_private_dm",
        "product_media",
    }
)

# Empty predecessors: independent identity. Do not list primary_reply here —
# that would block a second send whenever the public/text reply is in-flight
# or needs owner action.
PURPOSE_PREDECESSORS: dict[MetaOutboundPurpose, tuple[MetaOutboundPurpose, ...]] = {
    "primary_reply": ("session_greeting", "gender_ack"),
    "session_greeting": ("primary_reply",),
    "gender_ack": ("session_greeting", "primary_reply"),
    "image_quota_notice": (),
    "comment_private_dm": (),
    "product_media": (),
}
