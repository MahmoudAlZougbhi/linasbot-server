"""Request definition graphs compiled from owner natural-language instructions.

Luna compiles. The system never invents fields that the owner did not name.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from typing import Any

_VAGUE = (
    "كل المعلومات المهمة",
    "كل شي مهم",
    "whatever you need",
    "all important information",
    "all the important",
    "جيب المعلومات المهمة",
    "any info you need",
)
_FIELD_ALIASES: tuple[tuple[str, str, str], ...] = (
    ("name", "الاسم", "string"),
    ("age", "العمر", "integer"),
    ("height", "الطول", "integer"),
    ("weight", "الوزن", "integer"),
    ("area", "المنطقة", "string"),
    ("day", "اليوم", "string"),
    ("phone", "الهاتف", "string"),
    ("email", "الإيميل", "string"),
    ("date", "التاريخ", "string"),
    ("time", "الوقت", "string"),
    ("branch", "الفرع", "string"),
    ("quantity", "الكمية", "integer"),
    ("address", "العنوان", "string"),
    ("notes", "ملاحظات", "string"),
)


@dataclass
class GraphCompileResult:
    title: str
    destination: str
    required_information: list[dict[str, Any]] = field(default_factory=list)
    optional_information: list[dict[str, Any]] = field(default_factory=list)
    linked_entities: list[dict[str, str]] = field(default_factory=list)
    confirmation_required: bool = True
    needs_owner_clarification: bool = False
    warnings: list[str] = field(default_factory=list)
    requested_reasoning_effort: str = "low"
    effective_reasoning_effort: str = "low"
    source_text_hash: str = ""
    used_llm: bool = False


def source_hash(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


def destination_from_type(raw: str) -> str:
    value = str(raw or "").strip().upper()
    if value in {"APPOINTMENT", "APPOINTMENTS"}:
        return "appointment"
    if value in {"ORDER", "ORDERS"}:
        return "order"
    return "general"


def _normalize_effort(raw: str | None, *, fallback: str) -> str:
    value = str(raw or fallback).strip().lower()
    if value in {"low", "medium"}:
        return value
    return fallback if fallback in {"low", "medium"} else "low"


def _is_vague(text: str) -> bool:
    hay = re.sub(r"\s+", " ", (text or "").strip().lower())
    return any(token in hay for token in _VAGUE)


def _has_token(hay: str, token: str) -> bool:
    if not token:
        return False
    if token.isascii() and token.isalpha():
        return re.search(rf"\b{re.escape(token)}\b", hay, flags=re.IGNORECASE) is not None
    return token in hay


def _explicit_fields(text: str) -> list[dict[str, Any]]:
    hay = (text or "").lower()
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for key, arabic, value_type in _FIELD_ALIASES:
        if not (_has_token(hay, key) or arabic in hay):
            continue
        if key in seen:
            continue
        seen.add(key)
        out.append(
            {
                "key": key,
                "label": arabic if arabic in hay else key,
                "value_type": value_type,
                "required": True,
                "validation": {},
            }
        )
    return out


def _is_complex(source_text: str, fields: list[dict[str, Any]]) -> bool:
    text = source_text or ""
    return len(fields) >= 6 or len(text) > 500


def _grounded_fields(source_text: str, rows: list[Any]) -> list[dict[str, Any]]:
    hay = (source_text or "").lower()
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in rows:
        if not isinstance(raw, dict):
            continue
        key = str(raw.get("key") or "").strip()
        label = str(raw.get("label") or key).strip()
        if not key or key in seen:
            continue
        if not (_has_token(hay, key) or (label and label.lower() in hay)):
            continue
        seen.add(key)
        out.append(
            {
                "key": key,
                "label": label or key,
                "value_type": str(raw.get("value_type") or "string"),
                "required": bool(raw.get("required", True)),
                "validation": dict(raw.get("validation") or {}),
            }
        )
    return out


def compile_request_graph(
    *,
    title: str,
    source_text: str,
    destination: str = "appointment",
    linked_entities: list[dict[str, str]] | None = None,
    llm_result: dict[str, Any] | None = None,
) -> GraphCompileResult:
    hashed = source_hash(source_text)
    dest = destination_from_type(destination)
    explicit = _explicit_fields(source_text)
    effort = "medium" if _is_complex(source_text, explicit) else "low"
    links = list(linked_entities or [])
    if _is_vague(source_text) and not explicit:
        return GraphCompileResult(
            title=title,
            destination=dest,
            linked_entities=links,
            needs_owner_clarification=True,
            warnings=["needs_owner_clarification"],
            requested_reasoning_effort=effort,
            effective_reasoning_effort=effort,
            source_text_hash=hashed,
        )
    if llm_result is not None:
        llm_effort = _normalize_effort(llm_result.get("effort"), fallback=effort)
        grounded = _grounded_fields(source_text, list(llm_result.get("required_information") or []))
        chosen = explicit or grounded
        if not chosen:
            return GraphCompileResult(
                title=title,
                destination=dest,
                linked_entities=links,
                needs_owner_clarification=True,
                warnings=["needs_owner_clarification"],
                requested_reasoning_effort=llm_effort,
                effective_reasoning_effort=llm_effort,
                source_text_hash=hashed,
                used_llm=True,
            )
        return GraphCompileResult(
            title=str(llm_result.get("title") or title),
            destination=destination_from_type(str(llm_result.get("destination") or dest)),
            required_information=chosen,
            optional_information=_grounded_fields(source_text, list(llm_result.get("optional_information") or [])),
            linked_entities=list(llm_result.get("linked_entities") or links),
            confirmation_required=bool(llm_result.get("confirmation_required", True)),
            source_text_hash=hashed,
            used_llm=True,
            requested_reasoning_effort=llm_effort,
            effective_reasoning_effort=llm_effort,
        )
    if not explicit:
        return GraphCompileResult(
            title=title,
            destination=dest,
            linked_entities=links,
            needs_owner_clarification=True,
            warnings=["needs_owner_clarification"],
            requested_reasoning_effort=effort,
            effective_reasoning_effort=effort,
            source_text_hash=hashed,
        )
    return GraphCompileResult(
        title=title,
        destination=dest,
        required_information=explicit,
        linked_entities=links,
        confirmation_required=True,
        source_text_hash=hashed,
        requested_reasoning_effort=effort,
        effective_reasoning_effort=effort,
    )
