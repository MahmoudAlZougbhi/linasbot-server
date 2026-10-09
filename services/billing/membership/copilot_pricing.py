"""Token-range Copilot pricing. The live path stays on USD bands until the flag is on."""

from __future__ import annotations

from typing import Any

POLICY_VERSION = "message-economy-v2"

DEFAULT_BANDS: list[dict[str, Any]] = [
    {"min_tokens": 0, "max_tokens": 8000, "messages": 1},
    {"min_tokens": 8001, "max_tokens": 20000, "messages": 2},
    {"min_tokens": 20001, "max_tokens": 40000, "messages": 3},
    {"min_tokens": 40001, "max_tokens": 80000, "messages": 5},
    {"min_tokens": 80001, "max_tokens": None, "messages": 8},
]


def default_policy() -> dict[str, Any]:
    return {
        "policy_version": POLICY_VERSION,
        "token_bands": [dict(row) for row in DEFAULT_BANDS],
        "min_messages_per_request": 1,
        "max_messages_per_request": 10,
        "approval_threshold_messages": 1,
        "estimate_margin": 0.2,
    }


def validate_token_policy(raw: dict[str, Any]) -> dict[str, Any]:
    bands_raw = raw.get("token_bands")
    if not isinstance(bands_raw, list) or not bands_raw:
        raise ValueError("token_bands are required")
    bands: list[dict[str, Any]] = []
    expected = 0
    last_messages = 0
    for index, row in enumerate(bands_raw):
        if not isinstance(row, dict):
            raise ValueError(f"band {index} is not an object")
        start_raw = row.get("min_tokens")
        messages_raw = row.get("messages")
        if not isinstance(start_raw, int) or not isinstance(messages_raw, int):
            raise ValueError(f"band {index} needs integer bounds")
        start = start_raw
        end_raw = row.get("max_tokens")
        end = None if end_raw in (None, "") else int(end_raw) if isinstance(end_raw, int) else None
        if end_raw not in (None, "") and end is None:
            raise ValueError(f"band {index} max must be an integer or blank")
        messages = messages_raw
        if start != expected:
            raise ValueError("bands must be contiguous and start at 0")
        if end is not None and end < start:
            raise ValueError("band max is below min")
        if messages < last_messages:
            raise ValueError("messages must not decrease")
        if end is None and index != len(bands_raw) - 1:
            raise ValueError("only the last band may be open-ended")
        bands.append({"min_tokens": start, "max_tokens": end, "messages": messages})
        last_messages = messages
        expected = 0 if end is None else end + 1
    minimum = int(raw.get("min_messages_per_request") or 1)
    maximum = int(raw.get("max_messages_per_request") or 10)
    threshold = int(raw.get("approval_threshold_messages") or 1)
    if not 1 <= minimum <= maximum <= 1000 or threshold < 1:
        raise ValueError("min, max, and threshold are out of range")
    return {
        "policy_version": POLICY_VERSION,
        "token_bands": bands,
        "min_messages_per_request": minimum,
        "max_messages_per_request": maximum,
        "approval_threshold_messages": threshold,
        "estimate_margin": float(raw.get("estimate_margin") or 0.2),
    }


def messages_for_tokens(tokens: int, policy: dict[str, Any] | None = None) -> int:
    active = policy or default_policy()
    count = max(0, int(tokens))
    chosen = int(active["token_bands"][-1]["messages"])
    for band in active["token_bands"]:
        end = band["max_tokens"]
        if count >= int(band["min_tokens"]) and (end is None or count <= int(end)):
            chosen = int(band["messages"])
            break
    return max(int(active["min_messages_per_request"]), min(chosen, int(active["max_messages_per_request"])))


def needs_approval(messages_high: int, policy: dict[str, Any] | None = None) -> bool:
    active = policy or default_policy()
    return int(messages_high) > int(active["approval_threshold_messages"])


def estimate_copy(
    *,
    messages_low: int,
    messages_high: int,
    tokens_low: int,
    tokens_high: int,
    expected_tools: int,
    plan_remaining: int,
    purchased_remaining: int,
) -> dict[str, str]:
    en = (
        f"This request may cost between {messages_low} and {messages_high} messages, or more "
        f"(about {tokens_low}–{tokens_high} tokens, ~{expected_tools} tool steps). "
        "You are charged the actual cost after it runs. "
        f"Your balance: {plan_remaining} plan + {purchased_remaining} purchased."
    )
    ar = (
        f"هيدا الطلب ممكن يكلّف بين {messages_low} و {messages_high} رسائل، أو أكثر. "
        "بنخصم الكلفة الفعلية بعد ما يخلّص. "
        f"رصيدك: {plan_remaining} من الخطة + {purchased_remaining} مشترى."
    )
    fr = (
        f"Cette demande peut coûter entre {messages_low} et {messages_high} messages, ou plus. "
        "Le coût réel est débité après l'exécution. "
        f"Solde : {plan_remaining} du forfait + {purchased_remaining} achetés."
    )
    return {"en": en, "ar": ar, "fr": fr}
