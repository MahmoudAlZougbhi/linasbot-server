"""Deterministic first-pass task split. Not a substitute for the OpenAI planner."""

from __future__ import annotations

import re

from services.customer_ai.contracts.enums import SourceFamily, TaskType
from services.customer_ai.contracts.plan import PlannerPlan, PlannerTask, TaskSpan

_HUMAN = re.compile(r"\b(human|agent|operator|handoff|موظف|شخص حقيقي|تحدث مع)\b", re.I)
_BOOK = re.compile(r"\b(book|booking|appoint|appointment|reserve|حجز|موعد)\b", re.I)
_ORDER = re.compile(r"\b(order|buy|purchase|اطلب|اشتري)\b", re.I)
_PHOTO = re.compile(r"\b(photo|picture|video|image|صورة|صور|فيديو)\b", re.I)
_HOURS = re.compile(r"\b(hour|hours|open|close|opening|ساعات|مفتوح|مغلق|وقت الدوام)\b", re.I)
_PRICE = re.compile(r"\b(price|cost|how much|كم|سعر|غلى|كلفة)\b", re.I)
_PRODUCT = re.compile(r"\b(product|serum|cream|shampoo|منتج|سيروم|كريم)\b", re.I)
_CANCEL = re.compile(r"\b(cancel|status|الغِ|الغي|وين صار)\b", re.I)
_NEGATE_BOOK = re.compile(
    r"(لا تحجز|ما تحجز|don't book|do not book|just asking|بس عم اسأل|بس اسأل|not booking)",
    re.I,
)
_NEGATE_HUMAN = re.compile(
    r"(i do not want a human|don't want a human|لا أريد موظف|ما بدي موظف|مش بدي حدا)",
    re.I,
)
_REFERENCE = re.compile(
    r"\b(the first one|the second one|that one|this one|the same one|هي|هاد|هيدا|الأول|التاني)\b",
    re.I,
)
_CORRECT = re.compile(
    r"\b(i meant|i mean|not the|actually the|قصدت|مش ال|مو ال|غلط.? قصدي)\b",
    re.I,
)


def _has(pattern: re.Pattern[str], text: str, *substrings: str) -> bool:
    if pattern.search(text):
        return True
    hay = text.casefold()
    return any(token.casefold() in hay for token in substrings)


def _task(task_id: str, task_type: TaskType, text: str, families: list[SourceFamily]) -> PlannerTask:
    return PlannerTask(
        id=task_id,
        type=task_type,
        span=TaskSpan(text=text, end=len(text)),
        source_families=families,
    )


def plan_message(message: str) -> PlannerPlan:
    text = (message or "").strip()
    tasks: list[PlannerTask] = []
    if _has(_HUMAN, text, "موظف", "شخص حقيقي") and not _NEGATE_HUMAN.search(text):
        tasks.append(_task("t_human", "human_request", text, ["none"]))
    if _has(_CANCEL, text, "الغي", "وين صار"):
        tasks.append(_task("t_status", "cancel_or_status", text, ["requests"]))
    if _has(_BOOK, text, "حجز", "موعد") and not _NEGATE_BOOK.search(text):
        tasks.append(_task("t_book", "service_request", text, ["services", "branches", "hours"]))
    if _has(_ORDER, text, "اطلب", "اشتري"):
        tasks.append(_task("t_order", "product_request", text, ["products"]))
    if _has(_PHOTO, text, "صورة", "صور", "فيديو"):
        tasks.append(_task("t_media", "resource_request", text, ["services", "products", "knowledge"]))
    if _has(_HOURS, text, "ساعات", "مفتوح", "مغلق", "الدوام"):
        tasks.append(_task("t_hours", "hours", text, ["hours", "branches"]))
    if _has(_PRICE, text, "سعر", "كلفة", "غلى") or _has(_PRODUCT, text, "منتج", "سيروم", "كريم"):
        families: list[SourceFamily] = ["services", "prices"]
        if _has(_PRODUCT, text, "منتج", "سيروم", "كريم"):
            families = ["products", "prices"]
        tasks.append(_task("t_info", "information", text, families))
    questions = [part.strip() for part in re.split(r"[؟?]+", text) if part.strip()]
    if len(questions) > 1 and all(item.type in {"information", "hours", "comparison"} for item in tasks):
        tasks = [
            _task(f"t_q{index}", "information", part, ["knowledge", "care", "services", "faq", "branches"])
            for index, part in enumerate(questions, start=1)
        ]
    if _CORRECT.search(text):
        fix = _task("t_fix", "draft_correction", text, ["knowledge", "services", "products", "faq"])
        fix.entity_mentions = ["correction"]
        tasks.append(fix)
    if _REFERENCE.search(text):
        tagged = False
        for item in tasks:
            if item.type in {"information", "hours", "comparison"}:
                if "anaphor" not in item.entity_mentions:
                    item.entity_mentions.append("anaphor")
                tagged = True
        if not tagged:
            ref = _task("t_ref", "information", text, ["knowledge", "services", "products", "faq"])
            ref.entity_mentions = ["anaphor"]
            tasks.append(ref)
    if not tasks:
        tasks.append(_task("t_info", "information", text, ["knowledge", "care", "services", "faq", "branches"]))
    read_only = all(
        item.type in {"information", "comparison", "hours", "acknowledgement", "draft_correction"} for item in tasks
    )
    return PlannerPlan(tasks=tasks, read_only=read_only)
