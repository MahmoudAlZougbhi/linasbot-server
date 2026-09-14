"""Choose the Brain outbound destination from turn surface + channel."""

from __future__ import annotations


def outbound_destination(turn: object | None, channel: str) -> str:
    """Public comments must not be labeled as private DMs.

    The agent/FAQ pipelines historically treated every non-web channel as
    ``dm``. Comment turns share that path, so a live Instagram/Facebook
    comment reply was posted (or attempted) as a private reply and the
    public comment stayed silent.
    """

    surface = str(getattr(turn, "surface", "") or "").strip().lower()
    ch = (channel or "").strip().lower()
    if surface == "comment" or "comment" in ch:
        return "comment"
    if "web" in ch or "web" in surface:
        return "web_chat"
    return "dm"
