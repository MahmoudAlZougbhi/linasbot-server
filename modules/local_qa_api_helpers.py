"""Local Q&A file IO, builders, and create-internal (LOC split from local_qa_api)."""

from __future__ import annotations

import json
import os
import re
import uuid
from datetime import datetime
from typing import Any

from services.language_detection_service import language_detection_service
from storage.persistent_storage import QA_PAIRS_FILE, ensure_dirs

QA_FILE_PATH = str(QA_PAIRS_FILE)

_LEGACY_FAQ_WRITE_BLOCKED = {
    "success": False,
    "error": "CM_FAQ_CANONICAL",
    "message": "Legacy Bot Training FAQ writes are disabled. Use AI Setup → FAQ.",
    "redirect": "/content-managers/faq",
}


def _legacy_faq_writes_blocked() -> dict[str, Any] | None:
    """Block dashboard Bot Training writes when CM FAQ is the sole authoring entry."""
    from services.cm.constants import cm_faq_canonical

    if cm_faq_canonical():
        return dict(_LEGACY_FAQ_WRITE_BLOCKED)
    return None


def ensure_qa_file_exists() -> None:
    """Ensure the Q&A file exists"""
    ensure_dirs()
    if not os.path.exists(QA_FILE_PATH):
        open(QA_FILE_PATH, "w", encoding="utf-8").close()  # Create empty file


def read_qa_pairs() -> Any:
    """Read all Q&A pairs from JSONL file"""
    ensure_qa_file_exists()
    qa_pairs = []

    try:
        with open(QA_FILE_PATH, encoding="utf-8") as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if line:
                    try:
                        qa_pair = json.loads(line)
                        qa_pair["id"] = line_num  # Use line number as ID
                        qa_pairs.append(qa_pair)
                    except json.JSONDecodeError as e:
                        print(f"⚠️ Error parsing line {line_num}: {e}")
                        continue
    except Exception as e:
        print(f"❌ Error reading Q&A file: {e}")

    return qa_pairs


def write_qa_pairs(qa_pairs: Any) -> Any:
    """Write all Q&A pairs to JSONL file"""
    ensure_qa_file_exists()

    try:
        with open(QA_FILE_PATH, "w", encoding="utf-8") as f:
            for qa_pair in qa_pairs:
                # Remove 'id' field before writing (it's generated from line number)
                qa_to_write = {k: v for k, v in qa_pair.items() if k != "id"}
                f.write(json.dumps(qa_to_write, ensure_ascii=False) + "\n")
        return True
    except Exception as e:
        print(f"❌ Error writing Q&A file: {e}")
        return False


def build_qa_entry(
    question: str,
    answer: str,
    language: str,
    category: str,
    qa_group_id: str,
    source_language: str,
    is_auto_translated: bool,
) -> Any:
    """Build a normalized Q&A entry for JSONL storage."""
    return {
        "question": question,
        "answer": answer,
        "language": language_detection_service.normalize_training_language(language),
        "category": category,
        "timestamp": datetime.now().isoformat(),
        "qa_group_id": qa_group_id,
        "source_language": language_detection_service.normalize_training_language(source_language),
        "is_auto_translated": bool(is_auto_translated),
    }


def reload_local_qa_cache() -> None:
    """Reload in-memory local QA cache so bot uses latest training instantly."""
    try:
        from services.local_qa_service import local_qa_service

        local_qa_service.qa_pairs = local_qa_service.load_from_jsonl()
    except Exception as e:
        print(f"⚠️ Failed to reload local_qa_service cache: {e}")


def _answer_in_arabic_script(text: str) -> bool:
    """True if text contains Arabic script (not Franco/Latin only)."""
    if not text:
        return False
    return bool(re.search(r"[\u0600-\u06FF]", text))


async def _translate_to_arabic_script(text: str, source_language: str) -> str:
    """
    Translate a single text to Arabic script (for Franco/Latin input).
    Returns the same text if already in Arabic script.
    """
    if not text or _answer_in_arabic_script(text):
        return text or ""
    result = await language_detection_service.translate_training_pair(
        question=text, answer=text, source_language=source_language, target_languages=["ar"]
    )
    ar_trans = result.get("translations", {}).get("ar", {})
    out = ar_trans.get("answer") or ar_trans.get("question") or ""
    if out and _answer_in_arabic_script(out):
        return out
    return text


async def create_local_qa_pair_internal(
    question: str,
    answer: str,
    language: str = "ar",
    category: str = "operator_trained",
) -> dict:
    """
    Create Q&A pair in local JSON file (used by Save to FAQ from Live Chat).
    Rule:
    - AR: question in Arabic script, answer in Arabic script.
    - Franco: question in Franco (Latin), answer always in Arabic script.
    """
    question = (question or "").strip()
    answer = (answer or "").strip()
    if not question or not answer:
        return {"success": False, "error": "Question and answer are required"}

    detected_language = language_detection_service.normalize_training_language(
        language,
        default=language_detection_service.detect_training_language(question),
    )
    # Answer must ALWAYS be in Arabic script for both AR and Franco
    answer_ar_canonical = answer
    if not _answer_in_arabic_script(answer):
        answer_ar_canonical = await _translate_to_arabic_script(answer, detected_language)
        # Retry with explicit franco if still not Arabic (e.g. detected_language was wrong)
        if not _answer_in_arabic_script(answer_ar_canonical):
            answer_ar_canonical = await _translate_to_arabic_script(answer, "franco")
        if not _answer_in_arabic_script(answer_ar_canonical):
            answer_ar_canonical = answer  # fallback only if translation fails

    qa_group_id = f"qa_{uuid.uuid4().hex[:10]}"
    created_entries = []

    target_languages_all = ["ar", "en", "fr", "franco"]
    translation_result = await language_detection_service.translate_training_pair(
        question=question,
        answer=answer_ar_canonical,
        source_language=detected_language,
        target_languages=target_languages_all,
    )
    if not translation_result.get("success"):
        return {
            "success": False,
            "error": "Failed to auto-translate Q&A to all 4 languages",
        }

    translations = translation_result.get("translations", {})
    for lang in target_languages_all:
        translated = translations.get(lang, {})
        # Question: AR = Arabic script only; Franco = Franco (Latin) only
        q_text = translated.get("question", "") or question
        # Answer: always Arabic script for ar and franco
        if lang in ("ar", "franco"):
            a_text = answer_ar_canonical
        else:
            a_text = translated.get("answer", "") or answer_ar_canonical
        # AR row: question MUST be in Arabic script (never Franco in AR view)
        if lang == "ar" and q_text and not _answer_in_arabic_script(q_text):
            q_text = await _translate_to_arabic_script(q_text, detected_language)
            if not _answer_in_arabic_script(q_text):
                q_text = await _translate_to_arabic_script(q_text, "franco")
        # Franco row: question in Franco; keep as from translation or original if source was Franco
        if lang == "franco":
            if not q_text or _answer_in_arabic_script(q_text):
                franco_trans = translations.get("franco", {})
                q_text = franco_trans.get("question", "") or (question if detected_language == "franco" else "")
        if not q_text or not a_text:
            continue
        # Do not save AR entry with Franco script (would show wrong in Manage Data)
        if lang == "ar" and not _answer_in_arabic_script(q_text):
            continue
        created_entries.append(
            build_qa_entry(
                question=q_text,
                answer=a_text,
                language=lang,
                category=category,
                qa_group_id=qa_group_id,
                source_language=detected_language,
                is_auto_translated=(lang != detected_language),
            )
        )

    qa_pairs = read_qa_pairs()
    qa_pairs.extend(created_entries)
    if write_qa_pairs(qa_pairs):
        reload_local_qa_cache()
        return {
            "success": True,
            "message": "Q&A pair saved to Manage Data",
            "data": created_entries[0],
            "created_entries": created_entries,
            "count_created": len(created_entries),
            "detected_language": detected_language,
            "qa_group_id": qa_group_id,
        }
    return {"success": False, "error": "Failed to write to file"}


