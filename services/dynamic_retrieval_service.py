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

SELECTOR_PROMPT = """You are a retrieval selector.
Your job is NOT to answer the user.
You must ONLY select which files are required to answer.

Rules:
- Select specific files over general ones.
- Include price file if pricing is mentioned.
- Include gender-specific files if user mentions men/women.
- Always include one relevant style file.
- Maximum 5 files total.
- If unclear, request clarification.
- If nothing matches, fallback to general file.
- Return JSON only. No explanation.

Output format:

{
  "files": ["file_id_1", "file_id_2"],
  "action": "normal"
}

OR

{
  "files": [],
  "action": "ask_clarification"
}

OR

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

ANSWER_PROMPT = """You are Marwa AI Assistant – the smart assistant for Lina's Laser Center. When asked "who is with me" or "من معي", respond that you are Marwa AI Assistant.

Use ONLY the provided information to answer.
Do NOT invent details.
Do NOT mention file names.
If information is missing, ask clarification question.

RELEVANT INFORMATION:
{{MERGED_CONTENT}}

USER MESSAGE:
{{USER_MESSAGE}}

RESPONSE RULES:
- Natural and human tone
- Follow provided style guidelines
- Be clear if prices are included
- Personalize if gender-specific
- Keep concise but informative
- Do not repeat unnecessary text"""


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
            model="gpt-4o-mini",
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


def _load_content_by_ids(files: List[str]) -> Tuple[str, bool]:
    """Load and merge content from selected file IDs across sections.
    Returns (merged_content, has_style)."""
    if not files:
        return "", False

    parts = []
    has_style = False
    for fid in files:
        for section in ("knowledge", "price", "style"):
            data = cfs.get_file(section, fid)
            if data and data.get("content"):
                title = data.get("title", "Untitled")
                parts.append(f"--- {title} ---\n{data['content']}")
                if section == "style":
                    has_style = True
                break
    return "\n\n".join(parts), has_style


def _get_default_general_and_style() -> str:
    """Fallback: use config legacy files when fallback_to_general."""
    parts = []
    if config.CORE_KNOWLEDGE_BASE:
        parts.append(f"--- Core Knowledge ---\n{config.CORE_KNOWLEDGE_BASE}")
    if config.BOT_STYLE_GUIDE:
        parts.append(f"--- Style Guide ---\n{config.BOT_STYLE_GUIDE}")
    if not parts:
        return "No knowledge available. Ask user for clarification."
    return "\n\n".join(parts)


def _ensure_style_included(merged: str, has_style: bool) -> str:
    """Ensure at least one style file is in merged content."""
    if has_style:
        return merged
    if config.BOT_STYLE_GUIDE:
        return (merged + "\n\n--- Default Style ---\n" + config.BOT_STYLE_GUIDE) if merged else config.BOT_STYLE_GUIDE
    return (merged + "\n\n--- Style ---\nBe professional, friendly, and helpful. Do not invent information.") if merged else "Be professional, friendly, and helpful. Do not invent information."


async def retrieve_and_merge(
    user_message: str,
    include_price_hint: bool = False,
) -> Tuple[str, Optional[str], str, Dict]:
    """
    Main entry: Select files via LLM, load content, merge.

    Returns: (merged_content, clarification_question, action, flow_meta)
    - If action=ask_clarification: merged_content is empty, clarification_question has the question.
    - If action=fallback_to_general: merged_content has default general + style.
    - If action=normal: merged_content has selected file content.
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

    if action == "ask_clarification":
        clarification = (
            "Could you provide more details so I can give you an accurate answer? "
            "For example: which service are you asking about? (hair removal, tattoo removal, whitening, etc.)"
        )
        return "", clarification, "ask_clarification", flow_meta

    if action == "fallback_to_general":
        merged = _get_default_general_and_style()
        merged = _ensure_style_included(merged, False)
        return merged, None, "fallback_to_general", flow_meta

    # action == normal: load selected files
    merged, has_style = _load_content_by_ids(files)
    merged = _ensure_style_included(merged, has_style)

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
        model=getattr(config, "GPT_MODEL", None) or "gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.7,
    )
    return (response.choices[0].message.content or "").strip()
