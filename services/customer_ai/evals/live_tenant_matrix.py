"""Capture-only live GPT matrix across Linas Laser + two isolated test tenants."""

from __future__ import annotations

import json
import time
import uuid
from typing import Any

from services.customer_ai.evals.live_tenant_seed import (
    MARKER_LINAS,
    MARKER_TEST,
    MARKER_TEST_2,
    TENANT_LINAS,
    TENANT_TEST,
    TENANT_TEST_2,
)
from services.customer_ai.runtime import run_customer_ai_dm

Case = dict[str, Any]


def capture_ids(token: str) -> dict[str, str]:
    """Lab-prefixed ids skip live Instagram outbox hydrate/billing persist."""
    short = (token or uuid.uuid4().hex)[:8]
    return {
        "channel": "instagram_dm",
        "conversation_id": f"lab:mt{short}",
        "user_id": f"lab:mu{short}",
        "message_id": f"lab:mm{short}",
    }


def matrix_cases() -> list[Case]:
    return [
        {
            "tenant_id": TENANT_LINAS,
            "id": "hi",
            "message": "Hi",
            "expect": "hello",
            "forbid": ["11:00", "99 USD", "5 USD"],
        },
        {
            "tenant_id": TENANT_LINAS,
            "id": "hours_antelias",
            "message": "شو ساعات عمل فرع أنطلياس؟",
            "expect": "hours_antelias",
            "forbid": ["09:00", "15:00", "99 USD", MARKER_TEST, MARKER_TEST_2],
        },
        {
            "tenant_id": TENANT_LINAS,
            "id": "price_laser",
            "message": "قديش سعر الليزر أنطلياس؟",
            "expect": "price_70",
            "forbid": ["99 USD", "5 USD", MARKER_TEST],
        },
        {
            "tenant_id": TENANT_LINAS,
            "id": "product",
            "message": "قديش سعر After Care Cream؟",
            "expect": "price_25",
            "forbid": ["99 USD", "5 USD"],
        },
        {
            "tenant_id": TENANT_LINAS,
            "id": "photo",
            "message": "ابعتلي صورة الليزر",
            "expect": "resource",
            "forbid": [MARKER_TEST],
        },
        {
            "tenant_id": TENANT_LINAS,
            "id": "video",
            "message": "فرجيني فيديو الجلسة",
            "expect": "resource",
            "forbid": [MARKER_TEST],
        },
        {
            "tenant_id": TENANT_LINAS,
            "id": "link",
            "message": "ابعتلي رابط الحجز",
            "expect": "resource",
            "forbid": [MARKER_TEST],
        },
        {
            "tenant_id": TENANT_LINAS,
            "id": "appointment",
            "message": "بدي موعد ليزر أنطلياس",
            "expect": "appointment",
            "forbid": [],
        },
        {
            "tenant_id": TENANT_LINAS,
            "id": "order",
            "message": "بدي اطلب After Care Cream",
            "expect": "order",
            "forbid": [],
        },
        {
            "tenant_id": TENANT_LINAS,
            "id": "human",
            "message": "بدي احكي مع حدا",
            "expect": "human",
            "forbid": [],
        },
        {
            "tenant_id": TENANT_LINAS,
            "id": "isolation",
            "message": f"what is {MARKER_TEST}?",
            "expect": "no_foreign_marker",
            "forbid": [MARKER_TEST, MARKER_TEST_2, "99 USD"],
        },
        {
            "tenant_id": TENANT_TEST,
            "id": "hours_hamra",
            "message": "What are Hamra hours on Monday?",
            "expect": "hours_hamra",
            "forbid": ["11:00", "19:00", MARKER_LINAS, MARKER_TEST_2, "5 USD"],
        },
        {
            "tenant_id": TENANT_TEST,
            "id": "price_alpha",
            "message": "How much is Product Alpha?",
            "expect": "price_99",
            "forbid": ["70 USD", "5 USD", MARKER_LINAS],
        },
        {
            "tenant_id": TENANT_TEST,
            "id": "appointment_blocked",
            "message": "I want to book an appointment tomorrow",
            "expect": "no_appointment",
            "forbid": [],
        },
        {
            "tenant_id": TENANT_TEST,
            "id": "order",
            "message": "I want to order Product Alpha",
            "expect": "order",
            "forbid": [],
        },
        {
            "tenant_id": TENANT_TEST_2,
            "id": "hours_jounieh",
            "message": "What are Jounieh hours?",
            "expect": "hours_jounieh",
            "forbid": ["11:00", "19:00", "09:00", MARKER_LINAS, MARKER_TEST],
        },
        {
            "tenant_id": TENANT_TEST_2,
            "id": "price_alpha",
            "message": "How much is Product Alpha?",
            "expect": "price_5",
            "forbid": ["99 USD", "70 USD", MARKER_LINAS],
        },
        {
            "tenant_id": TENANT_TEST_2,
            "id": "human",
            "message": "I want to talk to a human",
            "expect": "human",
            "forbid": [],
        },
        {
            "tenant_id": TENANT_TEST_2,
            "id": "order_blocked",
            "message": "I want to order Product Alpha",
            "expect": "no_order",
            "forbid": [],
        },
    ]


def _blob(outcome: Any) -> str:
    meta = outcome.metadata if isinstance(getattr(outcome, "metadata", None), dict) else {}
    reply = str(getattr(outcome, "reply", None) or "")
    pending = meta.get("pending_actions") or []
    receipts = meta.get("receipts") or meta.get("resource_receipts") or []
    return " ".join(
        [
            reply,
            str(getattr(outcome, "reason", "") or ""),
            str(meta.get("phase") or ""),
            str(pending),
            str(receipts),
            str(meta.get("awaiting_confirmation") or ""),
        ]
    )


def judge(case: Case, outcome: Any) -> tuple[bool, str]:
    blob = _blob(outcome)
    lower = blob.lower()
    reply = str(getattr(outcome, "reply", None) or "")
    for needle in case.get("forbid") or []:
        if needle and needle.lower() in lower:
            return False, f"leaked:{needle}"
    expect = case["expect"]
    if expect == "hello":
        ok = bool(reply.strip()) and "couldn" not in reply.lower()
        return ok, "hello" if ok else "empty_or_fail_copy"
    if expect == "hours_antelias":
        ok = "11:00" in reply and "19:00" in reply
        return ok, "antelias_clocks" if ok else "missing_antelias_clocks"
    if expect == "hours_hamra":
        ok = "09:00" in reply and "15:00" in reply
        return ok, "hamra_clocks" if ok else "missing_hamra_clocks"
    if expect == "hours_jounieh":
        ok = "08:00" in reply and "16:00" in reply
        return ok, "jounieh_clocks" if ok else "missing_jounieh_clocks"
    if expect == "price_70":
        ok = "70" in reply
        return ok, "laser_70" if ok else "missing_70"
    if expect == "price_25":
        ok = "25" in reply
        return ok, "cream_25" if ok else "missing_25"
    if expect == "price_99":
        ok = "99" in reply
        return ok, "alpha_99" if ok else "missing_99"
    if expect == "price_5":
        ok = "5" in reply
        return ok, "alpha_5" if ok else "missing_5"
    if expect == "resource":
        ok = any(
            needle in lower
            for needle in (
                "send_resource",
                "resource_request",
                "awaiting_delivery",
                "resource_not_found",
                "pending",
            )
        ) or any(needle in reply.lower() for needle in ("photo", "video", "http", "link", "صورة", "فيديو", "رابط"))
        return ok, "resource" if ok else "no_resource"
    if expect == "appointment":
        ok = "appointment" in lower or "confirm" in lower or "موعد" in blob
        return ok, "appointment" if ok else "no_appointment"
    if expect == "order":
        ok = "order" in lower or "confirm" in lower or "طلب" in blob
        return ok, "order" if ok else "no_order"
    if expect == "human":
        ok = "human" in lower or "handoff" in lower or "teammate" in lower or "موظف" in blob or "حدا" in blob
        return ok, "human" if ok else "no_human"
    if expect == "no_appointment":
        ok = "APPOINTMENT" not in blob
        return ok, "no_appointment" if ok else "appointment_leaked"
    if expect == "no_order":
        ok = "ORDER" not in blob
        return ok, "no_order" if ok else "order_leaked"
    if expect == "no_foreign_marker":
        ok = MARKER_TEST not in blob and MARKER_TEST_2 not in blob
        return ok, "isolated" if ok else "marker_leak"
    return False, f"unknown_expect:{expect}"


async def run_case(case: Case) -> dict[str, Any]:
    ids = capture_ids(uuid.uuid4().hex[:8])
    started = time.perf_counter()
    try:
        outcome = await run_customer_ai_dm(
            tenant_id=case["tenant_id"],
            message=case["message"],
            channel=ids["channel"],
            conversation_id=ids["conversation_id"],
            user_id=ids["user_id"],
            message_id=ids["message_id"],
            apply_customer_usage_limits=False,
        )
    except Exception as exc:  # noqa: BLE001 — matrix records provider/runtime faults
        return {
            "tenant_id": case["tenant_id"],
            "id": case["id"],
            "ok": False,
            "detail": f"exc:{type(exc).__name__}",
            "elapsed_ms": int((time.perf_counter() - started) * 1000),
            "stop": True,
            "reason": type(exc).__name__,
            "phase": "",
            "reply_len": 0,
            "reply_preview": "",
        }
    elapsed_ms = int((time.perf_counter() - started) * 1000)
    ok, detail = judge(case, outcome)
    meta = outcome.metadata if isinstance(getattr(outcome, "metadata", None), dict) else {}
    reply = str(getattr(outcome, "reply", None) or "")
    return {
        "tenant_id": case["tenant_id"],
        "id": case["id"],
        "ok": ok,
        "detail": detail,
        "elapsed_ms": elapsed_ms,
        "stop": bool(getattr(outcome, "stop", False)),
        "reason": str(getattr(outcome, "reason", "") or ""),
        "phase": meta.get("phase"),
        "reply_len": len(reply),
        "reply_preview": reply[:220],
    }


async def run_matrix() -> dict[str, Any]:
    rows = []
    for case in matrix_cases():
        row = await run_case(case)
        rows.append(row)
        print("[tenant-matrix-case] " + json.dumps(row, ensure_ascii=False, default=str)[:1500], flush=True)
        time.sleep(0.4)
    passed = sum(1 for row in rows if row.get("ok"))
    return {
        "ok": passed == len(rows),
        "passed": passed,
        "total": len(rows),
        "cases": rows,
    }
