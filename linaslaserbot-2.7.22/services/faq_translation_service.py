# -*- coding: utf-8 -*-
"""
FAQ Translation Service - Auto-translate FAQ on save (Franco/Arabic/English/French -> AR/EN/FR).
"""

import re
from typing import Tuple

# Franco-Arabic to Arabic character mapping (common)
FRANCO_TO_AR = {
    "2": "أ", "3": "ع", "5": "خ", "6": "ط", "7": "ح", "8": "ق", "9": "ص",
    "ch": "ش", "gh": "غ", "kh": "خ", "sh": "ش", "th": "ث", "dh": "ذ", "7a": "ح",
}


def _detect_input_language(text: str) -> str:
    """Detect if text is Arabic, Franco-Arabic, English, or French."""
    if not text or not text.strip():
        return "ar"
    text_lower = text.lower().strip()
    arabic_chars = len(re.findall(r"[\u0600-\u06FF]", text))
    latin_chars = len(re.findall(r"[a-zA-Z]", text))
    digits = len(re.findall(r"[0-9]", text))
    total_letters = arabic_chars + latin_chars
    if total_letters == 0:
        return "ar"
    arabic_ratio = arabic_chars / total_letters
    if arabic_ratio > 0.5:
        # Check Franco: mix of Arabic + Latin + numbers
        if latin_chars > 0 or digits > 0:
            return "franco"
        return "ar"
    # Latin: guess EN vs FR (simple heuristic)
    fr_indicators = ["é", "è", "ê", "à", "â", "û", "ô", "ç", "c'est", "vous", "nous", "pour", "avec", "dans"]
    if any(ind in text_lower for ind in fr_indicators):
        return "fr"
    return "en"


def _translate_with_deep_translator(text: str, source: str, target: str) -> str:
    """Translate text using deep-translator. Returns original if translation fails."""
    if not text or not text.strip():
        return ""
    if source == target:
        return text
    try:
        from deep_translator import GoogleTranslator
        translator = GoogleTranslator(source=source, target=target)
        result = translator.translate(text)
        return result.strip() if result else text
    except Exception as e:
        print(f"⚠️ Translation {source}->{target} failed: {e}")
        return text


def translate_faq_pair(question: str, answer: str) -> dict:
    """
    Take question+answer in any language (Franco, AR, EN, FR) and produce structured:
    question_ar, answer_ar, question_en, answer_en, question_fr, answer_fr
    """
    detected = _detect_input_language(question)
    if not detected:
        detected = "ar"

    source_q = question.strip() or ""
    source_a = answer.strip() or ""

    result = {
        "question_ar": "",
        "answer_ar": "",
        "question_en": "",
        "answer_en": "",
        "question_fr": "",
        "answer_fr": "",
    }

    # Set source as-is (Franco treated as Arabic)
    src_lang = "ar" if detected in ("ar", "franco") else detected
    if src_lang == "ar":
        result["question_ar"] = source_q
        result["answer_ar"] = source_a
    elif src_lang == "en":
        result["question_en"] = source_q
        result["answer_en"] = source_a
    else:
        result["question_fr"] = source_q
        result["answer_fr"] = source_a

    # Translate to missing languages
    for target in ["ar", "en", "fr"]:
        q_key = f"question_{target}"
        a_key = f"answer_{target}"
        if result[q_key]:
            continue
        result[q_key] = _translate_with_deep_translator(source_q, src_lang, target)
        result[a_key] = _translate_with_deep_translator(source_a, src_lang, target)

    return result
