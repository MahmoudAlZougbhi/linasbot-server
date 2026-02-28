# -*- coding: utf-8 -*-
"""
Smart Retrieval Service - AI selects the right files based on user question.
Two-phase: 1) Load titles only, 2) Select relevant files, 3) Load content of selected files only.
Uses audience (men/women/general) and priority (1-5) for selection.
"""

import re
import time
from typing import List, Optional, Tuple
from difflib import SequenceMatcher

from services import content_files_service as cfs


# Cache for titles (60 seconds)
_TITLES_CACHE: dict = {}
_TITLES_CACHE_TIME: dict = {}
CACHE_TTL_SECONDS = 60

# Hard fallback message when no knowledge found
NO_KNOWLEDGE_FALLBACK = "ما عندي هالمعلومة حالياً. ممكن تعطيني تفاصيل أكثر وأحاول ألاقي الجواب؟"
DEFAULT_SAFE_STYLE = "Be professional, friendly, and helpful. Do not invent information."


def _get_cached_titles(section: str) -> List[dict]:
    """Get titles for a section, with 60s cache."""
    now = time.time()
    if section in _TITLES_CACHE and (now - _TITLES_CACHE_TIME.get(section, 0)) < CACHE_TTL_SECONDS:
        return _TITLES_CACHE[section]
    titles = cfs.get_titles_only(section)
    _TITLES_CACHE[section] = titles
    _TITLES_CACHE_TIME[section] = now
    return titles


def invalidate_titles_cache():
    """Invalidate titles cache (call after create/update/delete)."""
    _TITLES_CACHE.clear()
    _TITLES_CACHE_TIME.clear()


def _normalize(text: str) -> str:
    """Normalize text for matching."""
    if not text:
        return ""
    text = re.sub(r"\s+", " ", str(text).strip())
    text = re.sub(r"[؟?!.،,;:]", "", text)
    text = text.replace("أ", "ا").replace("إ", "ا").replace("آ", "ا")
    text = text.replace("ة", "ه").replace("ى", "ي")
    return text.lower()


def _score_title_relevance(query: str, title: str, tags: List[str]) -> float:
    """Score how relevant a title/tags is to the query."""
    q_norm = _normalize(query)
    t_norm = _normalize(title)
    if not q_norm:
        return 0.0
    title_score = SequenceMatcher(None, q_norm, t_norm).ratio()
    q_words = set(q_norm.split())
    t_words = set(t_norm.split())
    tag_words = set()
    for tag in tags or []:
        tag_words.update(_normalize(tag).split())
    all_target = t_words | tag_words
    overlap = len(q_words & all_target) / max(len(q_words), 1)
    return 0.7 * title_score + 0.3 * overlap


def _audience_matches(file_audience: str, gender_hint: Optional[str]) -> bool:
    """Check if file audience matches detected gender."""
    file_aud = (file_audience or "general").lower()
    if file_aud == "general":
        return True
    if not gender_hint:
        return True  # unknown gender accepts general
    g = gender_hint.lower()
    if g == "male":
        return file_aud == "men"
    if g == "female":
        return file_aud == "women"
    return True


def _audience_score(file_audience: str, gender_hint: Optional[str]) -> float:
    """
    Score for audience match: gender-specific > general when gender known.
    Returns higher value for better match.
    """
    file_aud = (file_audience or "general").lower()
    if not gender_hint:
        return 1.0 if file_aud == "general" else 0.5  # Prefer general when unknown
    g = gender_hint.lower()
    if file_aud == "general":
        return 0.5  # Acceptable but not preferred
    if g == "male" and file_aud == "men":
        return 1.5  # Strong match
    if g == "female" and file_aud == "women":
        return 1.5
    return 0.0  # Mismatch


# Keywords for intent detection
PRICE_KEYWORDS = [
    "price", "cost", "how much", "pricing", "سعر", "اسعار", "كم", "قديش", "أديش", "تكلفة",
    "prix", "coût", "combien", "tarif", "adesh", "adde", "2adde", "2adesh", "kam", "sa3er",
]
SERVICE_KEYWORDS = [
    "laser", "ليزر", "hair removal", "إزالة شعر", "tattoo", "وشم", "تاتو", "whitening", "تبييض",
    "epilation", "épilation", "dpl", "homme", "رجال", "نساء", "men", "women", "female", "male",
]


def detect_intent(query: str) -> Tuple[str, Optional[str]]:
    """
    Detect intent: service_question, price_question, or general.
    Returns (intent, gender_hint) where gender_hint is "male", "female", or None.
    """
    q = _normalize(query)
    is_price = any(kw in q for kw in PRICE_KEYWORDS)
    if is_price:
        return "price_question", None

    gender_hint = None
    male_words = ["رجال", "رجل", "men", "homme", "male", "شب", "chab", "للذكور"]
    female_words = ["نساء", "امرأة", "women", "femme", "female", "صبية", "sabieh", "للإناث"]
    if any(w in q for w in male_words):
        gender_hint = "male"
    elif any(w in q for w in female_words):
        gender_hint = "female"

    is_service = any(kw in q for kw in SERVICE_KEYWORDS)
    if is_service:
        return "service_question", gender_hint
    return "general", gender_hint


def _select_with_audience_priority(
    items: List[dict],
    query: str,
    gender_hint: Optional[str],
    max_count: int,
    min_score: float = 0.1,
) -> Tuple[List[dict], List[dict]]:
    """
    Select files using audience + priority rules.
    Returns (selected_file_objects, selected_ids) - file objects for debug logging.
    """
    if not items:
        return [], []

    scored = []
    for t in items:
        rel = _score_title_relevance(query, t.get("title", ""), t.get("tags", []))
        aud_score = _audience_score(t.get("audience", "general"), gender_hint)
        if aud_score == 0:
            continue  # Audience mismatch
        prio = t.get("priority", 3)
        try:
            prio = max(1, min(5, int(prio)))
        except (TypeError, ValueError):
            prio = 3
        combined = rel * aud_score + (prio * 0.05)  # priority as tie-breaker
        if combined >= min_score:
            scored.append((t, combined))
    scored.sort(key=lambda x: (x[1], x[0].get("priority", 3)), reverse=True)
    selected = [t for t, _ in scored[:max_count]]
    return selected, [t["id"] for t in selected]


def select_relevant_files(
    query: str,
    intent: str,
    gender_hint: Optional[str] = None,
    max_knowledge: int = 2,
    max_style: int = 1,
    max_price: int = 2,
) -> Tuple[dict, dict]:
    """
    Select relevant file IDs for each section based on query, intent, audience, priority.
    Returns (selected_ids_dict, selected_files_for_debug) where:
    - selected_ids_dict: {"knowledge": [id1], "style": [id1], "price": [id1]}
    - selected_files_for_debug: {"knowledge": [{id, title}], ...} for logging
    """
    result = {"knowledge": [], "style": [], "price": []}
    debug_files = {"knowledge": [], "style": [], "price": []}

    # Style: always one, best by relevance
    style_titles = _get_cached_titles("style")
    if style_titles:
        best_style = max(style_titles, key=lambda x: _score_title_relevance(query, x.get("title", ""), x.get("tags", [])))
        result["style"] = [best_style["id"]]
        debug_files["style"] = [{"id": best_style["id"], "title": best_style.get("title", "")}]

    if intent == "price_question":
        price_titles = _get_cached_titles("price")
        if price_titles:
            selected, ids = _select_with_audience_priority(price_titles, query, gender_hint, max_price)
            if not selected:
                selected = [price_titles[0]]
                ids = [price_titles[0]["id"]]
            result["price"] = ids
            debug_files["price"] = [{"id": t["id"], "title": t.get("title", "")} for t in selected]
        return result, debug_files

    if intent == "service_question":
        knowledge_titles = _get_cached_titles("knowledge")
        if knowledge_titles:
            selected, ids = _select_with_audience_priority(knowledge_titles, query, gender_hint, max_knowledge)
            if not selected:
                selected = [knowledge_titles[0]]
                ids = [knowledge_titles[0]["id"]]
            result["knowledge"] = ids
            debug_files["knowledge"] = [{"id": t["id"], "title": t.get("title", "")} for t in selected]

        if any(kw in _normalize(query) for kw in PRICE_KEYWORDS):
            price_titles = _get_cached_titles("price")
            if price_titles:
                selected, ids = _select_with_audience_priority(price_titles, query, gender_hint, max_price)
                if selected:
                    result["price"] = ids
                    debug_files["price"] = [{"id": t["id"], "title": t.get("title", "")} for t in selected]
    else:
        knowledge_titles = _get_cached_titles("knowledge")
        if knowledge_titles:
            selected, ids = _select_with_audience_priority(knowledge_titles, query, gender_hint, 1)
            if selected:
                result["knowledge"] = ids
                debug_files["knowledge"] = [{"id": t["id"], "title": t.get("title", "")} for t in selected]
            else:
                result["knowledge"] = [knowledge_titles[0]["id"]]
                debug_files["knowledge"] = [{"id": knowledge_titles[0]["id"], "title": knowledge_titles[0].get("title", "")}]

    return result, debug_files


def retrieve_content(
    query: str,
    include_price: bool = False,
) -> dict:
    """
    Main entry: retrieve knowledge, style, and (optional) price content.
    Returns: {
        "knowledge": str,
        "style": str,
        "price": str,
        "selected_files": {"knowledge": [...], "style": [...], "price": [...]},
        "no_price_file_found": bool,
        "no_knowledge_file_found": bool,
    }
    Hard fallback safety: if no price file and include_price → price="", no_price_file_found=True.
    """
    import config

    intent, gender_hint = detect_intent(query)
    if include_price:
        intent = "price_question" if intent == "price_question" else intent

    selected_ids, selected_files = select_relevant_files(query, intent, gender_hint)

    result = {
        "knowledge": cfs.load_file_contents("knowledge", selected_ids["knowledge"]),
        "style": cfs.load_file_contents("style", selected_ids["style"]),
        "price": "",
        "selected_files": selected_files,
        "no_price_file_found": False,
        "no_knowledge_file_found": False,
        "detected_intent": intent,
        "detected_gender": gender_hint,
    }

    # Price: HARD SAFETY - never generate price if no price file
    if include_price:
        price_content = cfs.load_file_contents("price", selected_ids["price"])
        if not price_content:
            result["no_price_file_found"] = True
            result["price"] = ""  # NEVER use config fallback for price - prevent hallucination
        else:
            result["price"] = price_content
    else:
        result["price"] = ""

    # Style: fallback to config if empty
    if not result["style"] and config.BOT_STYLE_GUIDE:
        result["style"] = config.BOT_STYLE_GUIDE
    if not result["style"]:
        result["style"] = DEFAULT_SAFE_STYLE

    # Knowledge: fallback to config for general info, but mark if no file found
    if not result["knowledge"]:
        result["no_knowledge_file_found"] = True
        if config.CORE_KNOWLEDGE_BASE:
            result["knowledge"] = config.CORE_KNOWLEDGE_BASE
        else:
            result["knowledge"] = NO_KNOWLEDGE_FALLBACK

    return result
