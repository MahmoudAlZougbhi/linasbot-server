"""Embed snippet generation for tenant website widgets."""

from __future__ import annotations

import os


def public_api_base() -> str:
    raw = (os.getenv("PUBLIC_URL") or os.getenv("LINAS_PUBLIC_URL") or "https://www.linasaibot.com").strip()
    return raw.rstrip("/")


def build_embed_snippet(*, widget_key: str) -> str:
    base = public_api_base()
    key = (widget_key or "").strip()
    return f'<script src="{base}/web-chat/widget.js" data-widget-key="{key}" async></script>'
