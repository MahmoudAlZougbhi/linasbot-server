# -*- coding: utf-8 -*-
"""
Dynamic File-Based AI Retrieval Service

Two-phase flow:
  Step 1 (LLM): Select which files are needed (titles only, no content).
  Step 2 (LLM): Generate final answer using only selected file content.

Reduces token usage by loading only relevant files.
"""

import json
import re
from typing import Dict, List, Optional, Tuple

from services import content_files_service as cfs
from services.llm_core_service import client
import config

SELECTOR_PROMPT = """You are a file selector. Your ONLY job is to pick which files to load.
You do NOT decide actions, ask questions, or interpret the user. GPT does that.
You ONLY select file IDs. That is all.

Rules:
- Select specific files over general ones.
- Include price file if pricing is mentioned.
- Include gender-specific files if user mentions men/women.
- Always include one relevant style file.
- Maximum 5 files total.
- When unclear or vague, return empty files – the bot will use default content. GPT will decide if clarification is needed.
- Return JSON only. No explanation.

Output format (ONLY these two):

{
  "files": ["file_id_1", "file_id_2"],
  "action": "normal"
}

OR (when unclear which files to pick):

{
  "files": [],
  "action": "fallback_to_general"
}

USER MESSAGE:
{{USER_MESSAGE}}

AVAILABLE FILES:

KNOWLEDGE:
{{KNOWLEDGE_TITLES}}

PRICES:
{{PRICE_TITLES}}

STYLE:
{{STYLE_TITLES}}"""

ANSWER_PROMPT = """You are Marwa AI Assistant – the smart assistant for Lina's Laser Center. When asked "who is with me" or "من معي", respond that you are Marwa AI Assistant. When answering in Arabic, write your name as "مروى" and use Arabic script only (no Latin letters). In Arabic addressing, use respectful forms: أستاذ (male), عزيزتي (female), حضرتك (unknown), include known customer name after title in Arabic letters, and avoid "يا" + transliterated names. In Arabic, clinic name must appear exactly as: ليناز ليزر. Keep responses concise and ask at most one question per message.

Use ONLY the provided information to answer.
Do NOT invent details.
Do NOT mention file names.
If information is missing, ask clarification question.

RELEVANT INFORMATION:
{{MERGED_CONTENT}}

USER MESSAGE:
{{USER_MESSAGE}}

RESPONSE RULES:
- Respond like a friendly employee in a natural conversation – conversational, not robotic.
- Follow provided style guidelines.
- Be clear if prices are included.
- Personalize if gender-specific.
- Keep concise but informative.
- Do not repeat unnecessary text.
- Out-of-scope rule: if user asks about non-clinic topics (news/politics/general knowledge), politely refuse and redirect to clinic services only.
- When the user has answered your clarification question, you have enough info – answer their original question."""


def _format_titles_for_prompt(titles: List[dict]) -> str:
    """Format file titles for the selector prompt."""
    if not titles:
        return "(none)"
    lines = []
    for t in titles:
        tid = t.get("id", "")
        ttitle = t.get("title", "Untitled")
        tags = t.get("tags", [])
        tag_str = f" [tags: {', '.join(tags)}]" if tags else ""
        lines.append(f"  - {tid}: {ttitle}{tag_str}")
    return "\n".join(lines)


def _get_all_titles() -> Tuple[List[dict], List[dict], List[dict]]:
    """Get titles for all sections."""
    k = cfs.get_titles_only("knowledge")
    p = cfs.get_titles_only("price")
    s = cfs.get_titles_only("style")
    return k, p, s


def _has_any_content_files() -> bool:
    """Check if any content files exist (new file-based system in use)."""
    k, p, s = _get_all_titles()
    return len(k) > 0 or len(p) > 0 or len(s) > 0


async def select_files_llm(user_message: str) -> Dict:
    """
    Step 1: LLM selects which file IDs are needed.
    Returns: {"files": [id1, id2], "action": str, "raw_response": str} for Activity Flow.
    """
    k_titles, p_titles, s_titles = _get_all_titles()

    prompt = SELECTOR_PROMPT.replace("{{USER_MESSAGE}}", user_message)
    prompt = prompt.replace("{{KNOWLEDGE_TITLES}}", _format_titles_for_prompt(k_titles))
    prompt = prompt.replace("{{PRICE_TITLES}}", _format_titles_for_prompt(p_titles))
    prompt = prompt.replace("{{STYLE_TITLES}}", _format_titles_for_prompt(s_titles))

    try:
        response = await client.chat.completions.create(
            model="gpt-5.1",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
        )
        text = response.choices[0].message.content.strip()
        raw_response = text
        m = re.search(r"\{[\s\S]*\}", text)
        if m:
            data = json.loads(m.group())
            return {
                "files": data.get("files", []) if isinstance(data.get("files"), list) else [],
                "action": data.get("action", "normal"),
                "raw_response": raw_response[:600] if raw_response else None,
            }
    except Exception as e:
        print(f"⚠️ Dynamic retrieval select_files_llm error: {e}")
    return {"files": [], "action": "fallback_to_general", "raw_response": None}


def _normalize_for_match(s: str) -> str:
    """Normalize string for title/id matching (lowercase, collapse spaces/underscores)."""
    if not s:
        return ""
    return re.sub(r"[\s_\-]+", " ", str(s).lower().strip())


def _build_title_to_id_map() -> dict:
    """Build map: normalized_title -> (section, file_id) for fallback lookup when selector returns titles."""
    result = {}
    for section in ("knowledge", "price", "style"):
        for t in cfs.get_titles_only(section):
            fid = t.get("id", "")
            title = t.get("title", "")
            if fid and title:
                key = _normalize_for_match(title)
                if key and key not in result:
                    result[key] = (section, fid)
                # Also match id if it looks like a title (e.g. Laser_Hair_Removal_Men)
                key_id = _normalize_for_match(fid)
                if key_id and key_id not in result:
                    result[key_id] = (section, fid)
    return result


def _load_content_by_ids(files: List[str]) -> Tuple[str, bool]:
    """Load and merge content from selected file IDs across sections.
    Selector may return titles instead of IDs - we resolve via title-to-id map.
    Returns (merged_content, has_style)."""
    if not files:
        return "", False

    title_to_id = _build_title_to_id_map()
    parts = []
    has_style = False
    for fid in files:
        data, loaded_section = None, None
        for section in ("knowledge", "price", "style"):
            data = cfs.get_file(section, fid)
            if data and data.get("content"):
                loaded_section = section
                break
        if not data and fid:
            key = _normalize_for_match(fid)
            if key in title_to_id:
                loaded_section, resolved_id = title_to_id[key]
                data = cfs.get_file(loaded_section, resolved_id)
        if data and data.get("content"):
            title = data.get("title", "Untitled")
            parts.append(f"--- {title} ---\n{data['content']}")
            if loaded_section == "style":
                has_style = True
    return "\n\n".join(parts), has_style


def _get_default_general_and_style() -> str:
    """Fallback: use config legacy files when fallback_to_general."""
    parts = []
    if config.CORE_KNOWLEDGE_BASE:
        parts.append(f"--- Core Knowledge ---\n{config.CORE_KNOWLEDGE_BASE}")
    if config.BOT_STYLE_GUIDE:
        parts.append(f"--- Style Guide ---\n{config.BOT_STYLE_GUIDE}")
    if not parts:
        # Never send a "No knowledge available..." marker into GPT context.
        # Keep fallback neutral and style-first.
        return config.BOT_STYLE_GUIDE or "Be professional, friendly, and helpful. Do not invent information."
    return "\n\n".join(parts)


def _ensure_style_included(merged: str, has_style: bool) -> str:
    """Ensure style guidance exists without duplicating default style in final system prompt."""
    if has_style:
        return merged
    # The final GPT system prompt already includes BOT_STYLE_GUIDE as a foundation section.
    # Appending it here duplicates "Default Style" in custom selector context.
    if config.BOT_STYLE_GUIDE:
        return merged
    return (merged + "\n\n--- Style ---\nBe professional, friendly, and helpful. Do not invent information.") if merged else "Be professional, friendly, and helpful. Do not invent information."


async def retrieve_and_merge(
    user_message: str,
    include_price_hint: bool = False,
    response_lang: str = "ar",
) -> Tuple[str, Optional[str], str, Dict]:
    """
    Main entry: Select files via LLM, load content, merge.
    Selector ONLY picks files – no actions. GPT decides clarification etc.

    Returns: (merged_content, None, action, flow_meta)
    - action=fallback_to_general: merged_content has default general + style.
    - action=normal: merged_content has selected file content.
    - flow_meta: {"titles_sent": [...], "selected_files": [...], "action": ...} for Activity Flow.
    """
    flow_meta: Dict = {"titles_sent": [], "selected_files": [], "action": "fallback_to_general"}

    if not _has_any_content_files():
        return _get_default_general_and_style(), None, "fallback_to_general", flow_meta

    k_titles, p_titles, s_titles = _get_all_titles()
    all_titles = []
    for t in k_titles + p_titles + s_titles:
        tid = t.get("id", "")
        ttitle = t.get("title", "Untitled")
        all_titles.append({"id": tid, "title": ttitle})
    flow_meta["titles_sent"] = all_titles

    result = await select_files_llm(user_message)
    action = result.get("action", "normal")
    files = result.get("files", [])

    # Selector ONLY picks files – never returns ask_clarification. If it does (legacy), treat as fallback.
    if action == "ask_clarification":
        print("ℹ️ Selector returned ask_clarification – selector only picks files, GPT decides. Forcing fallback_to_general.")
        action = "fallback_to_general"
        result["raw_response"] = json.dumps(
            {"files": files, "action": action, "override_reason": "selector_files_only"},
            ensure_ascii=False,
        )

    flow_meta["action"] = action
    flow_meta["selected_files"] = files
    flow_meta["selector_ai_raw_response"] = result.get("raw_response")
    id_to_title = {t.get("id", ""): t.get("title", "Untitled") for t in all_titles}
    flow_meta["selected_titles"] = [id_to_title.get(fid, fid) for fid in files]
    flow_meta["bot_sent_to_selector"] = (
        f"User message: {user_message[:300]}{'...' if len(user_message) > 300 else ''}\n\n"
        + "Titles the Bot sent to AI (knowledge/price/style):\n"
        + "\n".join(f"  • {t.get('title', '')} (id: {t.get('id', '')})" for t in all_titles[:25])
    )

    if action == "fallback_to_general":
        # If selector returned files but chose fallback_to_general, prefer selected files.
        # Some selector outputs are mixed (files + fallback action). Use files when available.
        if files:
            merged, has_style = _load_content_by_ids(files)
            if merged:
                flow_meta["loaded_content_full"] = merged
                merged = _ensure_style_included(merged, has_style)
                if include_price_hint and config.PRICE_LIST and "price" not in merged.lower()[:200]:
                    merged += "\n\n--- Price List ---\n" + config.PRICE_LIST
                return merged, None, "normal", flow_meta
        # Do NOT send default KB+Style again: system prompt already has them as foundation.
        # Sending them here would duplicate ~same content and inflate tokens (e.g. 13k+).
        flow_meta["loaded_content_full"] = ""
        return "", None, "fallback_to_general", flow_meta

    # action == normal: load selected files
    merged, has_style = _load_content_by_ids(files)
    if not merged:
        # Selector returned files but none could be loaded (wrong IDs/titles).
        # Do NOT re-send default KB+Style (already in system prompt foundation) to avoid duplication.
        print(f"⚠️ Dynamic retrieval: selected files {files} could not be loaded. Relying on foundation KB/Style only.")
        merged = ""
        has_style = False
    else:
        merged = _ensure_style_included(merged, has_style)
    flow_meta["loaded_content_full"] = merged

    if include_price_hint and config.PRICE_LIST and "price" not in merged.lower()[:200]:
        merged += "\n\n--- Price List ---\n" + config.PRICE_LIST

    return merged, None, action, flow_meta


def is_dynamic_retrieval_available() -> bool:
    """Whether the dynamic file-based retrieval system has content files."""
    return _has_any_content_files()


async def generate_answer_from_content(merged_content: str, user_message: str) -> str:
    """
    Step 2: Generate final answer using only the provided merged content.
    """
    prompt = ANSWER_PROMPT.replace("{{MERGED_CONTENT}}", merged_content)
    prompt = prompt.replace("{{USER_MESSAGE}}", user_message)

    response = await client.chat.completions.create(
        model=getattr(config, "GPT_MODEL", None) or "gpt-5-mini",
        messages=[{"role": "user", "content": prompt}],
    )
    return (response.choices[0].message.content or "").strip()
