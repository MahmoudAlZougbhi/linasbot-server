"""AI Setup Chat — authoring assistant that patches the same CM drafts as the manual UI.

The LLM never writes storage directly. Flow:
  user message → structured typed patch → schema validate → put_draft (same SoT).
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
from services.cm.schemas import (
    ActionsSection,
    AiBasics,
    AiLimitsSection,
    BranchesSection,
    CareSection,
    CmBaseModel,
    DynamicMessagesSection,
    FaqSection,
    HandoffPolicy,
    KnowledgeSection,
    LanguagePolicy,
    OffDaysSection,
    OpeningHoursSection,
    PricesSection,
    RestrictedPolicy,
    ServicesSection,
    StylePolicy,
    default_section_payload,
)
from services.cm.storage import ConflictError, get_draft, put_draft

SECTION_MODELS: dict[str, type[CmBaseModel]] = {
    "ai_basics": AiBasics,
    "languages": LanguagePolicy,
    "style": StylePolicy,
    "dynamic_messages": DynamicMessagesSection,
    "services": ServicesSection,
    "branches": BranchesSection,
    "opening_hours": OpeningHoursSection,
    "prices": PricesSection,
    "care": CareSection,
    "knowledge": KnowledgeSection,
    "faq": FaqSection,
    "handoff": HandoffPolicy,
    "restricted": RestrictedPolicy,
    "actions": ActionsSection,
    "ai_limits": AiLimitsSection,
    "off_days": OffDaysSection,
}

# Interview order for guided setup (Sources/Publish are UI hubs, not draft sections).
SETUP_SECTION_ORDER: tuple[str, ...] = tuple(s for s in CM_SECTIONS if s in SECTION_MODELS)

INTRO_MESSAGE = (
    "أنا مساعد إعداد الـAI الخاص بعملك. سأساعدك على تجهيز إعدادات Content Management "
    "خطوة بخطوة. يمكنك الإجابة علي هنا، ويمكنك دائماً تعديل أي شيء يدوياً من الأقسام الموجودة تحت."
)

SECTION_PROMPTS: dict[str, str] = {
    "ai_basics": (
        "لنبدأ بهوية الـAI. ما اسم عملك؟ وما الاسم الذي تريد أن يستخدمه المساعد؟ "
        "صف باختصار دور الـAI وما يساعد العملاء به."
    ),
    "languages": "ما اللغات التي تريد دعمها (عربي، إنجليزي، فرنسي، فرانكو)؟ وما اللغة الافتراضية؟",
    "style": "كيف تريد أسلوب الرد: رسمي أم ودي؟ قصير أم مفصّل؟ هل تستخدم إيموجي؟",
    "dynamic_messages": "هل تريد رسالة ترحيب خاصة؟ اكتب نص الترحيب إن وجد، أو قل تخطي.",
    "services": "ما الخدمات أو المنتجات التي تقدّمها؟ اذكرها سطراً بسطر إن أمكن.",
    "branches": "هل لديك فروع أو مواقع؟ إن نعم، اذكر الاسم والعنوان/المدينة. إن لا، قل لا يوجد.",
    "opening_hours": ("ما ساعات العمل؟ يمكنك إنشاء جداول باسم (رجال/نساء/فرع). لكل يوم: من–إلى أو عطلة. أو قل لاحقاً."),
    "prices": "هل تريد إضافة أسعار الآن؟ اذكر الخدمة والسعر والعملة، أو قل لاحقاً.",
    "care": "هل لديك تعليمات تحضير/عناية أو سياسات مهمة للعملاء؟",
    "knowledge": "هل لديك معلومات إضافية يجب أن يعرفها الـAI عن عملك؟",
    "faq": "هل لديك أسئلة شائعة وإجاباتها؟ يمكنك إضافتها لاحقاً من قسم FAQ أيضاً.",
    "handoff": (
        "كيف يتواصل العميل مع إنسان؟ أعطني رقم واتساب أو رابط wa.me أو إيميل أو رابط موقع "
        "(لا تخترع أرقاماً — فقط ما تؤكده أنت)."
    ),
    "restricted": "هل هناك مواضيع يجب أن يرفضها الـAI؟ إن نعم اذكرها، وإلا قل لا.",
    "actions": (
        "هل تريد الرد على رسائل فيسبوك/إنستغرام الخاصة؟ هل تريد الرد على التعليقات؟ "
        "هل تريد تحليل الصور؟ (افتراضياً الصور معطّلة)."
    ),
    "ai_limits": "ما حد الصور يومياً/أسبوعياً لكل عميل؟ وما حد أسطر السياق تقريباً؟",
    "off_days": "هل عندكم يوم عطلة أسبوعي؟ وهل هناك تواريخ محددة يكون العمل فيها مغلقاً؟",
}


def _state_path(tenant_id: str, user_id: str) -> Any:
    root = tenant_cm_root(tenant_id) / "setup_chat"
    root.mkdir(parents=True, exist_ok=True)
    safe_user = re.sub(r"[^a-zA-Z0-9_-]+", "_", user_id or "user")[:80]
    return root / f"{safe_user}.json"


def load_setup_state(tenant_id: str, user_id: str) -> dict[str, Any]:
    path = _state_path(tenant_id, user_id)
    if not path.exists():
        return {
            "conversation_id": uuid.uuid4().hex,
            "current_section": SETUP_SECTION_ORDER[0],
            "completed_sections": [],
            "messages": [],
            "updated_at": time.time(),
        }
    data = read_json_object(path)
    return data if isinstance(data, dict) else {}


def save_setup_state(tenant_id: str, user_id: str, state: dict[str, Any]) -> None:
    state["updated_at"] = time.time()
    atomic_write_json(_state_path(tenant_id, user_id), state)


def section_progress(tenant_id: str) -> list[dict[str, Any]]:
    """Setup-chat progress rows (materializes missing drafts for interview continuity)."""
    from services.cm.progress import list_section_fill_status

    by_name = {str(row.get("section")): row for row in list_section_fill_status(tenant_id, create_missing=True)}
    return [by_name[name] for name in SETUP_SECTION_ORDER if name in by_name]


def _merge_dict(base: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    out = dict(base)
    for key, value in patch.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _merge_dict(out[key], value)
        else:
            out[key] = value
    return out


def apply_section_patch(
    *,
    tenant_id: str,
    section: str,
    patch: dict[str, Any],
    actor_id: str,
) -> dict[str, Any]:
    """Validate patch against section schema and save into the same CM draft store."""
    name = section.strip().replace("-", "_")
    model_cls = SECTION_MODELS.get(name)
    if model_cls is None:
        raise ValueError(f"Unknown setup section: {section}")
    if not isinstance(patch, dict):
        raise ValueError("Patch must be an object")

    # Reject attempts to smuggle platform/security fields.
    forbidden = {"tenant_id", "permissions", "role", "platform_rules"}
    bad = forbidden.intersection(patch.keys())
    if bad:
        raise ValueError(f"Forbidden patch fields: {sorted(bad)}")

    env = get_draft(name, tenant_id=tenant_id, create_default=True)
    current = dict(env.payload) if isinstance(env.payload, dict) else default_section_payload(name)
    merged = _merge_dict(current, patch)
    validated = model_cls.model_validate(merged)
    payload = validated.model_dump(mode="json")
    try:
        updated = put_draft(
            name,
            payload=payload,
            if_match=env.etag,
            updated_by=actor_id,
            tenant_id=tenant_id,
        )
    except ConflictError:
        # One retry with fresh etag for setup chat UX.
        env2 = get_draft(name, tenant_id=tenant_id, create_default=True)
        updated = put_draft(
            name,
            payload=payload,
            if_match=env2.etag,
            updated_by=actor_id,
            tenant_id=tenant_id,
        )
    return {
        "section": name,
        "revision": updated.revision,
        "etag": updated.etag,
        "payload": updated.payload,
    }


def _heuristic_patch(section: str, message: str) -> dict[str, Any] | None:
    """Deterministic fallback when LLM is unavailable — never invents phones/prices."""
    text = (message or "").strip()
    if not text or text.lower() in {"skip", "تخطي", "later", "لاحقا", "لاحقاً"}:
        return {}
    if section == "ai_basics":
        # "Business X, assistant Y" style — store only what user typed.
        return {
            "clinic_name": text[:120],
            "business_purpose": text[:500],
            "short_introduction": text[:500],
        }
    if section == "style":
        return {"tone": text[:200], "notes": text[:500]}
    if section == "handoff":
        # Only store as policy text; never fabricate phone_e164 contacts.
        return {"policy_text": text[:1000]}
    if section == "off_days":
        return {"notes": text[:500]}
    if section == "ai_limits":
        nums = [int(n) for n in re.findall(r"\b(\d{1,5})\b", text)]
        patch: dict[str, Any] = {}
        if len(nums) >= 1:
            patch["image_per_day"] = nums[0]
        if len(nums) >= 2:
            patch["image_per_week"] = nums[1]
        return patch
    if section == "actions":
        lower = text.lower()
        items = ActionsSection().model_dump(mode="json")["items"]
        for item in items:
            if item["id"].endswith("comments"):
                item["enabled"] = any(w in lower for w in ("comment", "تعليق", "comments"))
            if item["id"] == "photo_analysis":
                item["enabled"] = any(w in lower for w in ("photo", "image", "صور", "صورة"))
            if "dm" in item["id"] or "handoff" in item["id"]:
                item["enabled"] = True
        return {"items": items}
    if section in {
        "services",
        "branches",
        "knowledge",
        "care",
        "faq",
        "prices",
        "restricted",
        "dynamic_messages",
        "languages",
    }:
        return {"notes": text[:1000]}
    return {"notes": text[:1000]}


async def interpret_and_patch(
    *,
    tenant_id: str,
    user_id: str,
    message: str,
    actor_id: str,
    section: str | None = None,
    use_llm: bool = True,
) -> dict[str, Any]:
    """Apply a user turn to the current setup section (same draft SoT as manual UI)."""
    from services.token_metering import assert_tenant_can_use_ai, debit_ai_usage

    assert_tenant_can_use_ai(tenant_id)
    state = load_setup_state(tenant_id, user_id)
    current = (section or state.get("current_section") or SETUP_SECTION_ORDER[0]).strip().replace("-", "_")
    if current not in SECTION_MODELS:
        current = SETUP_SECTION_ORDER[0]

    patch = _heuristic_patch(current, message)
    llm_meta: dict[str, Any] = {"used_llm": False}
    if use_llm and (message or "").strip():
        try:
            llm_patch, llm_meta = await _llm_patch(tenant_id=tenant_id, section=current, message=message)
            if isinstance(llm_patch, dict):
                patch = llm_patch
        except Exception as exc:
            llm_meta = {"used_llm": False, "error": type(exc).__name__}

    result = apply_section_patch(
        tenant_id=tenant_id,
        section=current,
        patch=patch or {},
        actor_id=actor_id,
    )

    completed = list(state.get("completed_sections") or [])
    if current not in completed:
        completed.append(current)
    # Advance to next incomplete section
    next_section = current
    for name in SETUP_SECTION_ORDER:
        if name not in completed:
            next_section = name
            break
    else:
        next_section = current

    reply = (
        f"تم حفظ قسم `{current}` في مسودة Content Management (نفس البيانات التي يعدّلها النموذج اليدوي)."
        if patch
        else f"تم تخطي قسم `{current}`."
    )
    if next_section != current:
        reply += f"\n\nالتالي: `{next_section}`.\n{SECTION_PROMPTS.get(next_section, '')}"
    else:
        reply += "\n\nكل أقسام الإعداد الأساسية مغطاة. راجع يدوياً ثم Publish عندما تكون جاهزاً."

    messages = list(state.get("messages") or [])
    messages.append({"role": "user", "content": message, "section": current, "ts": time.time()})
    messages.append({"role": "assistant", "content": reply, "section": current, "ts": time.time()})
    state.update(
        {
            "current_section": next_section,
            "completed_sections": completed,
            "messages": messages[-40:],
        }
    )
    save_setup_state(tenant_id, user_id, state)

    # Meter a small setup turn when LLM was used (heuristic turns are free/local).
    if llm_meta.get("used_llm"):
        try:
            debit_ai_usage(
                tenant_id=tenant_id,
                model=str(llm_meta.get("model") or _setup_llm_model()),
                prompt_tokens=int(llm_meta.get("prompt_tokens") or 0),
                completion_tokens=int(llm_meta.get("completion_tokens") or 0),
                reference=f"cm_setup_chat:{current}",
            )
        except Exception:
            pass

    return {
        "reply": reply,
        "section": current,
        "next_section": next_section,
        "saved": result,
        "progress": section_progress(tenant_id),
        "intro": INTRO_MESSAGE,
        "llm": llm_meta,
    }


def _setup_llm_model() -> str:
    """Content Manager setup chat uses gpt-5.6-sol (owner policy)."""
    from services.model_policy import owner_model_id

    return owner_model_id()


async def _llm_patch(*, tenant_id: str, section: str, message: str) -> tuple[dict[str, Any], dict[str, Any]]:
    """Ask the model for a JSON patch only — validated by apply_section_patch."""
    from services.llm_core_service import build_chat_completion_kwargs, client
    from services.model_policy import emit_model_policy_trace, resolve_owner_policy

    policy = resolve_owner_policy(surface="owner_setup", mutation_hint=True, user_text=message)
    model = _setup_llm_model()
    schema_hint = json.dumps(default_section_payload(section), ensure_ascii=False)[:4000]
    system = (
        "You help a business owner fill Content Management drafts. "
        "Return ONLY a JSON object patch for the current section fields. "
        "Never invent phones, prices, URLs, or medical facts. "
        "If the user did not provide a fact, omit that field. "
        "Do not include tenant_id, permissions, or platform rules."
    )
    user = (
        f"tenant={tenant_id}\nsection={section}\n"
        f"current_schema_example={schema_hint}\n"
        f"owner_message={message}\n"
        "Return JSON patch only."
    )
    kwargs = build_chat_completion_kwargs(
        model=model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        max_tokens=1200,
        temperature=0.2,
        reasoning_effort=str(policy.reasoning_effort),
    )
    kwargs["response_format"] = {"type": "json_object"}
    emit_model_policy_trace(policy, extra={"section": section})
    response = await client.chat.completions.create(**kwargs)
    content = (response.choices[0].message.content or "{}").strip()
    patch = json.loads(content)
    usage = getattr(response, "usage", None)
    meta = {
        "used_llm": True,
        "model": model,
        "reasoning_mode": policy.reasoning_mode,
        "reasoning_effort": policy.reasoning_effort,
        "prompt_tokens": getattr(usage, "prompt_tokens", None),
        "completion_tokens": getattr(usage, "completion_tokens", None),
    }
    if not isinstance(patch, dict):
        raise ValueError("LLM patch was not an object")
    return patch, meta


def start_setup(tenant_id: str, user_id: str) -> dict[str, Any]:
    state = load_setup_state(tenant_id, user_id)
    progress = section_progress(tenant_id)
    current = state.get("current_section") or SETUP_SECTION_ORDER[0]
    for row in progress:
        if row["status"] == "incomplete":
            current = row["section"]
            break
    state["current_section"] = current
    save_setup_state(tenant_id, user_id, state)
    return {
        "intro": INTRO_MESSAGE,
        "current_section": current,
        "prompt": SECTION_PROMPTS.get(current, ""),
        "progress": progress,
        "messages": state.get("messages") or [],
    }
