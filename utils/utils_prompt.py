"""Legacy GPT system-instruction builder (linas bridge only)."""

from __future__ import annotations

import logging
from typing import Any

import config
from prompt_templates import (
    DEFAULT_SYSTEM_PROMPT_TEMPLATE,
    GENDER_INSTRUCTION_TOKEN,
    KNOWLEDGE_SECTION_TOKEN,
    OPERATIONAL_BLOCK_TOKEN,
    QA_REFERENCE_BLOCK_TOKEN,
)

_log = logging.getLogger(__name__)


def get_system_instruction(
    user_id: Any,
    response_lang: Any,
    qa_reference: str = "",
    include_price_list: bool = True,
    custom_knowledge_context: str | None = None,
    operational_context: str | None = None,
) -> Any:
    """
    Generate system instruction for GPT.

    Args:
        user_id: User identifier
        response_lang: Response language code (ar, en, fr, franco)
        qa_reference: Kept for backward compatibility (currently not injected)
        include_price_list: Whether to include the price_list.txt content in prompt context
        custom_knowledge_context: When provided (dynamic retrieval), ADDITIVE to KB/Style - never replaces
        operational_context: Structured block with state, original_question, task (Plan §10)

    ===== CM AI CONTROL PLANE =====
    Customer answers for published tenants use the CM runtime pipeline — not this helper.
    This helper remains for the temporary linas legacy bridge only; do not gate file injection
    on a global env flag (that would blank Linas legacy context incorrectly).
    """
    _ = qa_reference  # compatibility placeholder
    user_gender_str = config.user_gender.get(user_id, "unknown")

    published_mode = False
    if published_mode:
        include_price_list = False

    gender_instruction = ""
    if user_gender_str == "male":
        gender_instruction = "The user is male. You MUST use masculine forms exclusively in all your replies (e.g., 'Hello sir', 'How can I help you', 'I saw your question', 'tell us'). Adhere strictly to masculine phrasing in every sentence, verb, noun, and adjective. Do not mix forms."
    elif user_gender_str == "female":
        gender_instruction = "The user is female. You MUST use feminine forms exclusively in all your replies (e.g., 'Hello madam', 'How can I help you', 'I saw your question', 'tell us'). Adhere strictly to feminine phrasing in every sentence, verb, noun and adjective. Do not mix forms."
    else:  # This means gender is "غير محدد" or "unknown"
        gender_instruction = """
        **GENDER DECISION POLICY (AI-PRIMARY):**
        User's gender is UNKNOWN.
        - You are the decision owner: decide from context whether gender is required now.
        - If gender is required for safe/personalized next step, use action "ask_gender".
        - If gender is not required for the current informational answer, answer directly.
        - When the user provides gender, use action "confirm_gender" and continue naturally.
        - Use neutral wording whenever gender is still unknown.
        """

    price_list_section = ""
    if include_price_list and config.PRICE_LIST:
        price_list_section = f"""
        **💰 PRICE LIST:** (Use this to answer pricing questions)
        {config.PRICE_LIST}
        """

    style_guide = "" if published_mode else (config.BOT_STYLE_GUIDE or "")
    core_kb = "" if published_mode else (config.CORE_KNOWLEDGE_BASE or "")

    # KB + Style are ALWAYS the foundation (legacy mode). Selector content builds on top.
    knowledge_section = f"""
        **🔴 STYLE GUIDE (MANDATORY - Foundation - FOLLOW EVERY STEP IN ORDER):**
        The following contains MANDATORY rules for how you communicate AND the exact step-by-step flow for each service. You MUST follow every step in order. Do NOT skip steps. Do NOT jump ahead to booking if a step requires waiting (e.g., waiting for a photo before giving pricing).

        {style_guide}

        **📘 CORE KNOWLEDGE BASE (Foundation):** (Use this to answer questions about services, devices, IDs, and matching rules)
        {core_kb}

        {price_list_section}
        """
    if custom_knowledge_context and not published_mode:
        knowledge_section += f"""
        **📂 ADDITIONAL RELEVANT CONTEXT (Selector - use for this specific query):**
        {custom_knowledge_context}
        """

    operational_block = ""
    if operational_context:
        operational_block = f"""
        **📋 CONVERSATION STATE & TASK (Operational Context):**
        {operational_context}
        """

    # Keep token compatibility, but do not inject trained Q&A reference rules into GPT prompt.
    qa_reference_block = ""

    prompt_template = getattr(config, "SYSTEM_PROMPT_TEMPLATE", "")
    if not isinstance(prompt_template, str):
        prompt_template = ""

    # Safety fallback: avoid silently sending an empty system prompt when template file is blank/missing.
    # This keeps knowledge/style/operational sections active and prevents fragile runtime behavior.
    if not prompt_template.strip():
        prompt_template = DEFAULT_SYSTEM_PROMPT_TEMPLATE

    rendered_prompt = prompt_template
    token_values = (
        (KNOWLEDGE_SECTION_TOKEN, knowledge_section),
        (OPERATIONAL_BLOCK_TOKEN, operational_block),
        (GENDER_INSTRUCTION_TOKEN, gender_instruction),
        (QA_REFERENCE_BLOCK_TOKEN, qa_reference_block),
    )

    # Robust behavior for custom templates:
    # if a required token is missing from SYSTEM_PROMPT_TEMPLATE, append that section
    # so dynamic selector content/guardrails are never silently dropped.
    missing_tokens = []
    missing_sections = []
    for token, value in token_values:
        section_text = value or ""
        if token in rendered_prompt:
            rendered_prompt = rendered_prompt.replace(token, section_text)
        elif section_text.strip():
            missing_tokens.append(token)
            missing_sections.append(section_text.strip())

    if missing_sections:
        print(
            "⚠️ SYSTEM_PROMPT_TEMPLATE missing placeholders: "
            + ", ".join(missing_tokens)
            + ". Appending sections to preserve runtime context."
        )
        rendered_prompt = rendered_prompt.rstrip() + "\n\n" + "\n\n".join(missing_sections)

    return rendered_prompt
