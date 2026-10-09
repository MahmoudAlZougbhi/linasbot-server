"""Return a price only when it belongs to the matched catalog row."""

from __future__ import annotations


def grounded_price(*, asked: str, title: str, price: str, placeholder: bool = False) -> str | None:
    if placeholder or not str(price or "").strip():
        return None
    if _norm(asked) != _norm(title):
        return None
    return str(price).strip()


def _norm(value: str) -> str:
    return " ".join((value or "").casefold().split())
