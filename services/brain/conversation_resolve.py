"""Bounded conversation carry-over for follow-up turns (no full-history stuffing)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from services.brain.catalog_intent import is_catalog_list
from services.brain.greeting import is_greeting_only
from services.brain.published_labels import match_published_label, published_label_index

_AUDIENCE = re.compile(r"\b(men|women|male|female|للرجال|للنساء)\b", re.I)
_FOLLOWUP = re.compile(r"^(and|what about|how about|for|in|و|شو عن|et)\b", re.I)
_HOURS = re.compile(r"\b(hour|hours|open|دوام|ساعات|horaires)\b", re.I)
_PRICE = re.compile(r"\b(price|cost|how much|سعر|prix)\b", re.I)
_PRONOUN = re.compile(r"\b(it|that|this|them|those|هي|هاد|هيدا|نفس)\b", re.I)


@dataclass(frozen=True)
class ConversationResolution:
    rewritten_query: str
    used_turns: tuple[dict[str, str], ...]
    carry: dict[str, str]


def _turns(history: list[Any] | tuple[Any, ...] | None, max_turns: int) -> list[dict[str, str]]:
    turns: list[dict[str, str]] = []
    for item in list(history or [])[-max_turns:]:
        if isinstance(item, dict):
            role = str(item.get("role") or "")
            body = str(item.get("text") or item.get("content") or "").strip()
        else:
            role = str(getattr(item, "role", "") or "")
            body = str(getattr(item, "text", "") or "").strip()
        if body:
            turns.append({"role": role, "text": body})
    return turns


def _prior_user_text(turns: list[dict[str, str]]) -> str:
    for turn in reversed(turns):
        if turn.get("role") in {"user", "customer"}:
            return turn.get("text") or ""
    return " ".join(turn["text"] for turn in turns)


def _intent(text: str) -> str:
    if is_greeting_only(text):
        return "greeting"
    if is_catalog_list(text):
        return "catalog"
    if _HOURS.search(text or ""):
        return "hours"
    if _PRICE.search(text or ""):
        return "price"
    return "other"


def resolve_followup_query(
    message: str,
    history: list[Any] | tuple[Any, ...] | None,
    *,
    max_turns: int = 4,
    tenant_id: str = "",
) -> ConversationResolution:
    text = (message or "").strip()
    turns = _turns(history, max_turns)
    labels = published_label_index(tenant_id) if tenant_id else {"branches": (), "services": (), "products": ()}
    prior = _prior_user_text(turns)
    current_intent = _intent(text)
    prior_intent = _intent(prior) if prior else ""
    same_intent = bool(prior_intent and current_intent == prior_intent and current_intent not in {"greeting", "other"})
    followup = bool(_FOLLOWUP.match(text) or _PRONOUN.search(text) or (text.endswith("?") and len(text.split()) <= 6))
    new_topic = current_intent in {"greeting", "catalog"} or (prior_intent and current_intent != prior_intent and current_intent != "other")
    carry: dict[str, str] = {}
    scan = [prior, text] if (followup and not new_topic) or same_intent else [text]
    for body in scan:
        branch = match_published_label(body, labels.get("branches") or ())
        if branch:
            carry["branch"] = branch
        service = match_published_label(body, labels.get("services") or ()) or match_published_label(
            body, labels.get("products") or ()
        )
        if service and current_intent != "catalog":
            carry["service"] = service
        audience = _AUDIENCE.search(body or "")
        if audience:
            carry["audience"] = audience.group(1).lower()
    if new_topic and current_intent == "catalog":
        carry.pop("branch", None)
        carry.pop("service", None)
    rewritten = text
    if followup and not new_topic:
        bits = [text]
        if same_intent or current_intent == "other":
            if carry.get("service"):
                bits.append(carry["service"])
            if carry.get("branch"):
                bits.append(carry["branch"])
            if carry.get("audience"):
                bits.append(carry["audience"])
        rewritten = " ".join(bits)
    elif same_intent and carry.get("branch") and carry["branch"].casefold() not in text.casefold():
        rewritten = " ".join([text, carry["branch"]])
    return ConversationResolution(rewritten_query=rewritten, used_turns=tuple(turns), carry=carry)
