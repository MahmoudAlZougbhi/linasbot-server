"""Durable bulk CM fill plan from a business description dump.

Stores section patches queued for propose→approve→draft. Does not write Live.
"""

from __future__ import annotations

import json
import re
import time
import uuid
from typing import Any

from services.cm.atomic_io import atomic_write_json, read_json_object
from services.cm.constants import CM_SECTIONS
from services.cm.paths import tenant_cm_root
from services.cm.schemas import default_section_payload
from services.cm.setup_chat import SECTION_MODELS


def _plan_path(tenant_id: str, user_id: str) -> Any:
    root = tenant_cm_root(tenant_id) / "bulk_fill_plans"
    root.mkdir(parents=True, exist_ok=True)
    safe_user = re.sub(r"[^a-zA-Z0-9_-]+", "_", user_id or "user")[:80]
    return root / f"{safe_user}.json"


def load_bulk_plan(tenant_id: str, user_id: str) -> dict[str, Any] | None:
    path = _plan_path(tenant_id, user_id)
    if not path.exists():
        return None
    data = read_json_object(path)
    return data if isinstance(data, dict) else None


def save_bulk_plan(tenant_id: str, user_id: str, plan: dict[str, Any]) -> dict[str, Any]:
    plan["updated_at"] = time.time()
    atomic_write_json(_plan_path(tenant_id, user_id), plan)
    return plan


def clear_bulk_plan(tenant_id: str, user_id: str) -> None:
    path = _plan_path(tenant_id, user_id)
    if path.exists():
        path.unlink()


def _validate_patch(section: str, patch: dict[str, Any]) -> dict[str, Any] | None:
    model = SECTION_MODELS.get(section)
    if model is None or not isinstance(patch, dict) or not patch:
        return None
    try:
        base = default_section_payload(section)
        merged = {**base, **patch}
        # Nested shallow merge for known dict fields only — model validates.
        validated = model.model_validate(merged)
        # Return only keys the dump provided (plus validated shape).
        full = validated.model_dump(mode="json")
        return {k: full[k] for k in patch if k in full}
    except Exception:
        return None


def store_bulk_sections(
    *,
    tenant_id: str,
    user_id: str,
    sections: list[dict[str, Any]],
    source: str,
    missing_notes: list[str] | None = None,
) -> dict[str, Any]:
    """Normalize + persist queued section patches from a dump."""
    queue: list[dict[str, Any]] = []
    rejected: list[str] = []
    for row in sections:
        if not isinstance(row, dict):
            continue
        sec = str(row.get("section") or "").strip().replace("-", "_")
        if sec not in CM_SECTIONS or sec not in SECTION_MODELS:
            rejected.append(sec or "?")
            continue
        patch = row.get("patch")
        if not isinstance(patch, dict):
            rejected.append(sec)
            continue
        clean = _validate_patch(sec, patch)
        if not clean:
            rejected.append(sec)
            continue
        queue.append(
            {
                "section": sec,
                "patch": clean,
                "note": str(row.get("note") or "")[:400],
                "status": "pending",
            }
        )
    plan = {
        "plan_id": uuid.uuid4().hex,
        "tenant_id": tenant_id,
        "user_id": user_id,
        "created_at": time.time(),
        "source": source,
        "queue": queue,
        "rejected": rejected,
        "missing_notes": [str(x)[:300] for x in (missing_notes or []) if str(x).strip()],
        "status": "active" if queue else "empty",
    }
    return save_bulk_plan(tenant_id, user_id, plan)


def peek_next_pending(plan: dict[str, Any]) -> dict[str, Any] | None:
    for row in plan.get("queue") or []:
        if isinstance(row, dict) and row.get("status") == "pending":
            return row
    return None


def mark_section_status(plan: dict[str, Any], section: str, status: str) -> dict[str, Any]:
    sec = section.strip().replace("-", "_")
    for row in plan.get("queue") or []:
        if isinstance(row, dict) and row.get("section") == sec:
            row["status"] = status
    pending = [r for r in (plan.get("queue") or []) if isinstance(r, dict) and r.get("status") == "pending"]
    plan["status"] = "active" if pending else "complete"
    return plan


async def extract_sections_from_dump(*, text: str, reply_style: str = "") -> dict[str, Any]:
    """LLM: map business dump → per-section patches (JSON only)."""
    from services.llm_core_service import build_chat_completion_kwargs, client
    from services.model_policy import emit_model_policy_trace, resolve_owner_policy

    policy = resolve_owner_policy(
        surface="owner_copilot",
        owner_mode="work",
        mutation_hint=True,
        user_text=text[:2000],
    )
    section_hints = {
        sec: default_section_payload(sec)
        for sec in (
            "ai_basics",
            "languages",
            "style",
            "dynamic_messages",
            "services",
            "branches",
            "opening_hours",
            "prices",
            "care",
            "knowledge",
            "faq",
            "handoff",
            "restricted",
            "actions",
            "ai_limits",
            "off_days",
        )
        if sec in SECTION_MODELS
    }
    system = (
        "You distribute a business owner's dump into Linas AI Setup section patches. "
        'Return JSON: {"sections":[{"section":"ai_basics","patch":{...},"note":"..."}],'
        '"missing_notes":["..."]}. '
        "Only include sections you can fill from the dump. Never invent phones, prices, URLs, "
        "medical claims, or hours that were not provided. Prefer professional structure. "
        "For style/reply voice, honor reply_style when present. Patches are partial field updates."
    )
    user = (
        f"reply_style={reply_style[:2000]}\n"
        f"section_examples={json.dumps(section_hints, ensure_ascii=False)[:9000]}\n"
        f"business_dump=\n{text[:24000]}\n"
        "Return JSON only."
    )
    kwargs = build_chat_completion_kwargs(
        model=policy.model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        max_tokens=4000,
        temperature=0.2,
        reasoning_effort=str(policy.reasoning_effort),
    )
    kwargs["response_format"] = {"type": "json_object"}
    emit_model_policy_trace(policy, extra={"surface": "cm_bulk_fill"})
    response = await client.chat.completions.create(**kwargs)
    content = (response.choices[0].message.content or "{}").strip()
    parsed = json.loads(content)
    if not isinstance(parsed, dict):
        raise ValueError("bulk extract was not an object")
    return parsed
