"""Legacy GPT chat-response helpers group 6."""

from __future__ import annotations

import re
from typing import Any

import config
from services.booking.resolver import server_may_infer_body_parts
from services.chat_response_service_booking_resolve import _resolve_body_part_ids_from_area_hint
from services.chat_response_service_constants import (
    HAIR_REMOVAL_MACHINE_IDS,
    LASER_HAIR_REMOVAL_SERVICE_IDS,
    _safe_int,
)


def _fix_misassigned_tattoo_service_for_hair_booking(
    function_args: dict[str, Any],
    current_gender: str,
    user_input: str,
    context_messages: list[dict] | None,
) -> None:
    """
    GPT often confuses tattoo service_id (13) with NEO machine id (13) or sends 13 + Candela/Quadro.
    If the chosen machine is a hair device or the thread clearly mentions hair/Candela/underarm, remap to 1/12.
    """
    sid = _safe_int(function_args.get("service_id"))
    if sid != 13:
        return
    if current_gender not in ("male", "female"):
        return
    mid = _safe_int(function_args.get("machine_id"))
    blob = (user_input or "").lower()
    for msg in (context_messages or [])[-24:]:
        if isinstance(msg.get("content"), str):
            blob += " " + msg["content"].lower()
    hair_thread = any(
        t in blob
        for t in (
            "candela",
            "كانديلا",
            "kandila",
            "quadro",
            "كوادرو",
            " neo",
            "neo ",
            "niyo",
            "ليزر شعر",
            "إزالة شعر",
            "ازالة شعر",
            "ta7t el bat",
            "taht el bat",
            "t7t el bat",
            "تحت الإبط",
            "تحت الابط",
            "mw3ad",
            "maw3ad",
            "حجز",
            "موعد",
        )
    )
    tattoo_thread = any(t in blob for t in ("tattoo", "وشم", "تاتو", "détatouage", "detatouage"))
    if not tattoo_thread and (mid in HAIR_REMOVAL_MACHINE_IDS or hair_thread):
        new_sid = 12 if current_gender == "female" else 1
        print(f"DEBUG: Corrected service_id 13 → {new_sid} (hair booking; machine_id={mid}, hair_thread={hair_thread})")
        function_args["service_id"] = new_sid


def _recent_booking_context_blob(context_messages: list[dict] | None, user_input: str, last_n: int = 24) -> str:
    parts: list[str] = []
    if user_input and str(user_input).strip():
        parts.append(str(user_input))
    for msg in (context_messages or [])[-last_n:]:
        c = msg.get("content")
        if isinstance(c, str) and c.strip():
            parts.append(c)
    return " ".join(parts)


async def _try_infer_body_part_ids_from_conversation(
    service_id: int,
    user_input: str,
    context_messages: list[dict] | None,
    machine_id: int | None = None,
) -> list[int] | None:
    """When GPT omitted valid IDs but the user already named an area (e.g. underarm / ta7t el bat)."""
    if not server_may_infer_body_parts():
        return None
    if _safe_int(service_id) not in LASER_HAIR_REMOVAL_SERVICE_IDS:
        return None
    blob = _recent_booking_context_blob(context_messages, user_input).lower()
    if not blob.strip():
        return None
    compact = re.sub(r"[\s_\-]+", "", blob)
    underarm_franco = any(
        t in blob
        for t in (
            "ta7t el bat",
            "taht el bat",
            "t7t el bat",
            "7t el bat",
            "ta7t l bat",
            "ta7t elbet",
        )
    )
    underarm_ar = "ابط" in blob or "إبط" in blob or "اباط" in blob
    # "under arms", "under arm", "underarms" → compact contains underarm
    underarm_en = (
        "underarm" in compact or "armpit" in blob or "arm pit" in blob or "aisselle" in blob or "axilla" in blob
    )
    if underarm_franco or underarm_ar or underarm_en:
        for hint in ("underarm", "إبط", "ابط", "armpit"):
            resolved = await _resolve_body_part_ids_from_area_hint(hint, service_id, machine_id)
            if resolved:
                return resolved
    legs_ctx = (
        any(t in compact for t in ("ejren", "ejrin", "ejeren", "sa2en", "s2en", "se2en"))
        or any(t in blob for t in ("رجلين", "رجل", "ساق", "ساقين"))
        or re.search(r"\blegs?\b", blob) is not None
    )
    if legs_ctx:
        resolved = await _resolve_body_part_ids_from_area_hint(blob[:500], service_id, machine_id)
        if resolved:
            return resolved
    return None


def _is_placeholder_booking_customer_name(name: str | None) -> bool:
    if not name or not str(name).strip():
        return True
    n = str(name).strip().lower()
    placeholders = {
        "client",
        "unknown",
        "unknown customer",
        "instagram customer",
        "facebook customer",
        "test user",
        "guest",
        "user",
        "customer",
        "new user",
        "anonymous",
        "not known",
        "n/a",
        "na",
    }
    if n in placeholders:
        return True
    if n.startswith("test user"):
        return True
    return False


def _extract_latin_name_from_franco_booking_bundle(text: str) -> str | None:
    """
    Infer Latin customer name from Franco one-liners like:
    se3a 3 bilal bilal bilal esm
    Also scans [User clarified: ...] blocks when the main query is a stub.
    """
    if not text or not str(text).strip():
        return None
    chunks: list[str] = []
    for m in re.finditer(r"\[User clarified:\s*(.+?)\]", text, flags=re.IGNORECASE | re.DOTALL):
        inner = (m.group(1) or "").strip()
        if inner:
            chunks.append(inner.split("\n")[0].strip())
    tail = str(text).strip().split("\n")[0].strip()
    if tail and tail not in chunks:
        chunks.append(tail)

    noise_tokens = {
        "se3a",
        "sa3a",
        "s3a",
        "seaa",
        "saa",
        "so3a",
        "wa2t",
        "wakt",
        "waket",
        "please",
        "pls",
        "ok",
        "okay",
        "eh",
        "ah",
        "mw3ad",
        "mwede",
        "mw3ede",
        "maw3ad",
        "mawede",
        "7ajez",
        "hajez",
        "bede",
        "bade",
        "bedi",
        "tanen",
        "tenen",
        "tunun",
        "beirut",
        "beyrouth",
        "antelias",
        "antaliyas",
        "kifak",
        "kifek",
        "hi",
        "hey",
        "hello",
    }

    for raw in chunks:
        line = raw.strip()
        line = re.sub(
            r"\b(esm|esmi|esme|ism|isme|ismi|name)\b\.?$",
            "",
            line,
            flags=re.IGNORECASE,
        ).strip()
        if not line:
            continue
        tokens = line.split()
        latin_words: list[str] = []
        for t in tokens:
            tl = re.sub(r"^[^\w]+|[^\w]+$", "", t, flags=re.UNICODE)
            if not tl:
                continue
            low = tl.lower()
            if low in noise_tokens:
                continue
            if tl.isdigit():
                continue
            if re.fullmatch(r"\d{1,2}:\d{2}", tl):
                continue
            if re.search(r"[\u0600-\u06FF]", tl):
                continue
            if len(low) < 2:
                continue
            if not re.fullmatch(r"[A-Za-zÀ-ÿ]+(?:-[A-Za-zÀ-ÿ]+)?", tl):
                continue
            latin_words.append(tl)
        if not latin_words:
            continue
        lows = [w.lower() for w in latin_words]
        if len(set(lows)) == 1:
            cand = latin_words[0][:1].upper() + latin_words[0][1:].lower() if latin_words[0] else ""
        else:
            cand = " ".join(w[:1].upper() + w[1:].lower() if w else "" for w in latin_words)
        cand = cand.strip()
        if 2 <= len(cand) <= 80 and not _is_placeholder_booking_customer_name(cand):
            return cand
    return None


def _apply_inferred_name_from_user_bundle(
    user_id: str,
    user_input: str,
    parsed_response: dict[str, Any],
) -> None:
    """Backfill detected_name + session name when GPT missed Franco time+name bundles."""
    inferred = _extract_latin_name_from_franco_booking_bundle(user_input or "")
    if not inferred:
        return
    existing = (parsed_response.get("detected_name") or "").strip()
    if not existing:
        parsed_response["detected_name"] = inferred
    try:
        ud = config.user_data_whatsapp.setdefault(user_id, {})
        if not (str(ud.get("collected_name") or "")).strip():
            ud["collected_name"] = inferred
        config.user_names[user_id] = inferred
    except Exception as persist_e:
        print(f"⚠️ inferred name persist (bundle): {persist_e}")


def _prune_redundant_booking_questions_when_name_from_bundle(
    user_input: str,
    parsed_response: dict[str, Any],
) -> None:
    """
    If the user already bundled time + Latin name (Franco) but the model still asks for
    name / which Monday, strip those lines from bot_reply (Arabic-only; no Latin in reply).
    """
    if not _extract_latin_name_from_franco_booking_bundle(user_input or ""):
        return
    if (parsed_response.get("action") or "").strip().lower() != "ask_for_details_for_booking":
        return
    br = (parsed_response.get("bot_reply") or "").strip()
    if not br:
        return
    br2 = re.sub(
        r"(?m)^[^\n]*[١1]\)\s*[^\n]*(الاسم|اللاتين|الهوية|متل\s+الهوية)[^\n]*\n?",
        "",
        br,
    )
    br2 = re.sub(
        r"(?m)^[^\n]*[٢2]\)\s*[^\n]*(أي نهار|أي يوم)[^\n]*(تنين|إثنين|اثنين|الإثنين|الاثنين)[^\n]*\n?",
        "",
        br2,
    )
    br2 = re.sub(r"\n{3,}", "\n\n", br2).strip()
    if br2 == br:
        return
    still_numbered = bool(re.search(r"(?m)^\s*[١٢٣123][\).]", br2))
    if not still_numbered and (len(re.sub(r"\s+", "", br2)) < 20 or re.search(r"(شغلتين|سؤالين|أسألك)", br2)):
        parsed_response["bot_reply"] = "تمام أستاذ 🌷 تم تسجيل اسمك والوقت اللي ذكرتهما من رسالتك؛ منتابع لإكمال الحجز."
    else:
        parsed_response["bot_reply"] = br2
