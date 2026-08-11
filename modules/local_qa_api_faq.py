"""FAQ correction endpoints from Live Chat (LOC split from local_qa_api)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from modules.core import app
from modules.local_qa_api_helpers import (
    _answer_in_arabic_script,
    _translate_to_arabic_script,
    create_local_qa_pair_internal,
    read_qa_pairs,
    reload_local_qa_cache,
    write_qa_pairs,
)
from services.language_detection_service import language_detection_service


# ---------- FAQ Correction Workflow (Live Chat Dislike) ----------


@app.post("/api/faq/update-answer")
async def faq_update_answer(body: dict) -> Any:
    """
    Update an existing FAQ entry's answer (e.g. from Live Chat dislike → Save Change).
    Body: { faq_id, new_answer_text, updated_by, source }.
    Answer is stored in Arabic; all rows with same qa_group_id get the same Arabic answer.
    """
    try:
        faq_id = body.get("faq_id")
        new_answer_text = (body.get("new_answer_text") or "").strip()
        updated_by = body.get("updated_by") or "operator"
        source = body.get("source") or "live_chat_dislike"
        if not new_answer_text:
            return {"success": False, "error": "new_answer_text is required"}
        if faq_id is None:
            return {"success": False, "error": "faq_id is required"}

        qa_id = (
            int(faq_id)
            if isinstance(faq_id, str) and str(faq_id).isdigit()
            else (int(faq_id) if isinstance(faq_id, int) else None)
        )
        if qa_id is None or qa_id < 1:
            return {"success": False, "error": "Invalid faq_id"}

        qa_pairs = read_qa_pairs()
        if qa_id > len(qa_pairs):
            return {"success": False, "error": f"FAQ entry {faq_id} not found"}

        row = qa_pairs[qa_id - 1]
        qa_group_id = row.get("qa_group_id")
        detected_language = language_detection_service.normalize_training_language(row.get("language"), default="ar")
        answer_ar = new_answer_text
        if not _answer_in_arabic_script(answer_ar):
            answer_ar = await _translate_to_arabic_script(answer_ar, detected_language)
            if not _answer_in_arabic_script(answer_ar):
                answer_ar = await _translate_to_arabic_script(answer_ar, "franco")

        now = datetime.now().isoformat()
        for qa in qa_pairs:
            if qa_group_id and qa.get("qa_group_id") == qa_group_id:
                qa["answer"] = answer_ar
                qa["updated_at"] = now
                qa["updated_by"] = updated_by
                qa["source"] = source
            elif not qa_group_id and qa is row:
                qa["answer"] = answer_ar
                qa["updated_at"] = now
                qa["updated_by"] = updated_by
                qa["source"] = source

        if write_qa_pairs(qa_pairs):
            reload_local_qa_cache()
            return {
                "success": True,
                "message": "FAQ answer updated",
                "faq_id": qa_id,
                "updated_at": now,
                "updated_by": updated_by,
            }
        return {"success": False, "error": "Failed to write Q&A file"}
    except Exception as e:
        print(f"❌ Error in faq_update_answer: {e}")
        import traceback

        traceback.print_exc()
        return {"success": False, "error": str(e)}


@app.post("/api/faq/create-from-livechat")
async def faq_create_from_livechat(body: dict) -> Any:
    """
    Create a new FAQ entry from Live Chat dislike → Save New.
    Body: { question_text, question_language, answer_text, created_by, source, related_faq_id?, match_similarity? }.
    Question stays in original language; answer stored in Arabic; answer_franco = answer_ar.
    """
    try:
        question_text = (body.get("question_text") or "").strip()
        answer_text = (body.get("answer_text") or "").strip()
        question_language = body.get("question_language") or "ar"
        created_by = body.get("created_by") or "operator"
        source = body.get("source") or "live_chat_dislike"
        related_faq_id = body.get("related_faq_id")
        match_similarity = body.get("match_similarity")

        if not question_text or not answer_text:
            return {"success": False, "error": "question_text and answer_text are required"}

        result = await create_local_qa_pair_internal(
            question=question_text,
            answer=answer_text,
            language=question_language,
            category="live_chat_dislike",
        )
        if not result.get("success"):
            return result

        created_entries = result.get("created_entries") or []
        qa_group_id = result.get("qa_group_id")
        if qa_group_id:
            qa_pairs = read_qa_pairs()
            now = datetime.now().isoformat()
            for qa in qa_pairs:
                if qa.get("qa_group_id") == qa_group_id:
                    qa["created_by"] = created_by
                    qa["source"] = source
                    qa["created_at"] = now
                    if related_faq_id is not None:
                        qa["derived_from_faq_id"] = related_faq_id
                    if match_similarity is not None:
                        qa["match_similarity"] = match_similarity
            write_qa_pairs(qa_pairs)
            reload_local_qa_cache()

        return {
            "success": True,
            "message": "New FAQ entry created",
            "created_entries": created_entries,
            "count_created": result.get("count_created", 0),
            "created_by": created_by,
            "source": source,
        }
    except Exception as e:
        print(f"❌ Error in faq_create_from_livechat: {e}")
        import traceback

        traceback.print_exc()
        return {"success": False, "error": str(e)}
