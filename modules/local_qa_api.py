"""
Local Q&A API module: Simple JSON file-based Q&A management
Handles CRUD operations for local qa_pairs.jsonl file

Helpers: local_qa_api_helpers; FAQ correction: local_qa_api_faq (LOC split).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from modules.core import app

# Register FAQ correction routes; re-export handlers.
from modules.local_qa_api_faq import (  # noqa: E402, F401
    faq_create_from_livechat,
    faq_update_answer,
)
from modules.local_qa_api_helpers import (  # noqa: F401
    _LEGACY_FAQ_WRITE_BLOCKED,
    QA_FILE_PATH,
    _answer_in_arabic_script,
    _legacy_faq_writes_blocked,
    _translate_to_arabic_script,
    build_qa_entry,
    create_local_qa_pair_internal,
    ensure_qa_file_exists,
    read_qa_pairs,
    reload_local_qa_cache,
    write_qa_pairs,
)
from services.language_detection_service import language_detection_service


@app.get("/api/local-qa/list")
async def list_local_qa_pairs(language: str | None = None) -> Any:
    """List all Q&A pairs from local JSON file"""
    try:
        print("📖 Reading local Q&A pairs from file...")
        qa_pairs = read_qa_pairs()
        selected_language = language_detection_service.normalize_training_language(language, default="ar")

        if selected_language:
            qa_pairs = [
                qa
                for qa in qa_pairs
                if language_detection_service.normalize_training_language(qa.get("language"), default="")
                == selected_language
            ]

        by_language: dict[str, list[dict[str, Any]]] = {"ar": [], "en": [], "fr": [], "franco": []}
        for qa in qa_pairs:
            lang = language_detection_service.normalize_training_language(qa.get("language"))
            if lang not in by_language:
                by_language[lang] = []
            by_language[lang].append(qa)

        print(f"✅ Found {len(qa_pairs)} Q&A pairs{f' for {selected_language}' if selected_language else ''}")

        return {
            "success": True,
            "data": qa_pairs,
            "count": len(qa_pairs),
            "selected_language": selected_language,
            "by_language": by_language,
        }
    except Exception as e:
        print(f"❌ Error listing Q&A pairs: {e}")
        return {"success": False, "error": str(e)}


@app.post("/api/local-qa/create")
async def create_local_qa_pair(qa_data: dict) -> Any:
    """Create a new Q&A pair in local JSON file"""
    blocked = _legacy_faq_writes_blocked()
    if blocked is not None:
        return blocked
    try:
        question = qa_data.get("question", "").strip()
        answer = qa_data.get("answer", "").strip()
        category = qa_data.get("category", "general")
        requested_language = qa_data.get("language")
        return await create_local_qa_pair_internal(
            question=question,
            answer=answer,
            language=requested_language or "ar",
            category=category,
        )
    except Exception as e:
        print(f"❌ Error creating Q&A pair: {e}")
        import traceback

        traceback.print_exc()
        return {"success": False, "error": str(e)}


@app.put("/api/local-qa/{qa_id}")
async def update_local_qa_pair(qa_id: int, updates: dict) -> Any:
    """Update an existing Q&A pair in local JSON file"""
    blocked = _legacy_faq_writes_blocked()
    if blocked is not None:
        return blocked
    try:
        print(f"✏️ Updating Q&A pair ID: {qa_id}")

        qa_pairs = read_qa_pairs()

        # Find the Q&A pair by ID (line number)
        if qa_id < 1 or qa_id > len(qa_pairs):
            return {"success": False, "error": f"Q&A pair with ID {qa_id} not found"}

        # Update the Q&A pair (ID is 1-indexed, list is 0-indexed)
        qa_index = qa_id - 1

        if "question" in updates:
            qa_pairs[qa_index]["question"] = updates["question"]
        if "answer" in updates:
            qa_pairs[qa_index]["answer"] = updates["answer"]
        if "category" in updates:
            qa_pairs[qa_index]["category"] = updates["category"]
        if "language" in updates:
            qa_pairs[qa_index]["language"] = language_detection_service.normalize_training_language(updates["language"])

        # Re-detect language only if question changed and language not explicitly provided
        if "question" in updates and "language" not in updates:
            qa_pairs[qa_index]["language"] = language_detection_service.detect_training_language(updates["question"])

        qa_pairs[qa_index]["timestamp"] = datetime.now().isoformat()

        # Write back to file
        if write_qa_pairs(qa_pairs):
            reload_local_qa_cache()
            print(f"✅ Q&A pair {qa_id} updated successfully")
            return {"success": True, "message": "Q&A pair updated successfully", "data": qa_pairs[qa_index]}
        else:
            return {"success": False, "error": "Failed to write to file"}

    except Exception as e:
        print(f"❌ Error updating Q&A pair: {e}")
        return {"success": False, "error": str(e)}


@app.delete("/api/local-qa/{qa_id}")
async def delete_local_qa_pair(qa_id: int) -> Any:
    """Delete a Q&A pair from local JSON file"""
    blocked = _legacy_faq_writes_blocked()
    if blocked is not None:
        return blocked
    try:
        print(f"🗑️ Deleting Q&A pair ID: {qa_id}")

        qa_pairs = read_qa_pairs()

        # Find the Q&A pair by ID (line number)
        if qa_id < 1 or qa_id > len(qa_pairs):
            return {"success": False, "error": f"Q&A pair with ID {qa_id} not found"}

        # Remove the Q&A pair (ID is 1-indexed, list is 0-indexed)
        deleted_qa = qa_pairs.pop(qa_id - 1)

        # Write back to file
        if write_qa_pairs(qa_pairs):
            reload_local_qa_cache()
            print(f"✅ Q&A pair {qa_id} deleted successfully")
            print(f"   Deleted: {deleted_qa['question']}")
            return {"success": True, "message": "Q&A pair deleted successfully", "deleted": deleted_qa}
        else:
            return {"success": False, "error": "Failed to write to file"}

    except Exception as e:
        print(f"❌ Error deleting Q&A pair: {e}")
        return {"success": False, "error": str(e)}


@app.get("/api/local-qa/statistics")
async def get_local_qa_statistics() -> Any:
    """Get statistics about local Q&A pairs"""
    try:
        qa_pairs = read_qa_pairs()

        # Count by language
        language_counts: dict[str, Any] = {}
        category_counts: dict[str, Any] = {}

        for qa in qa_pairs:
            lang = language_detection_service.normalize_training_language(qa.get("language"), default="unknown")
            cat = qa.get("category", "general")

            language_counts[lang] = language_counts.get(lang, 0) + 1
            category_counts[cat] = category_counts.get(cat, 0) + 1

        return {
            "success": True,
            "statistics": {"total": len(qa_pairs), "by_language": language_counts, "by_category": category_counts},
        }
    except Exception as e:
        print(f"❌ Error getting statistics: {e}")
        return {"success": False, "error": str(e)}


@app.post("/api/local-qa/test-match")
async def test_local_qa_match(test_data: dict) -> Any:
    """Test if a question matches any Q&A pair in local file"""
    try:
        question = test_data.get("question", "")
        language = test_data.get("language", "ar")

        if not question:
            return {"success": False, "error": "Question is required"}

        print(f"\n{'=' * 80}")
        print("🧪 TESTING LOCAL Q&A MATCH")
        print(f"{'=' * 80}")
        print(f"📝 Question: {question}")
        print(f"🌐 Language: {language}")

        # Import local Q&A service
        from services.local_qa_service import local_qa_service

        # Reload Q&A pairs to ensure we have latest data
        local_qa_service.qa_pairs = local_qa_service.load_from_jsonl()
        print(f"📚 Loaded {len(local_qa_service.qa_pairs)} Q&A pairs")

        match_result = await local_qa_service.find_match(question, language)

        if match_result:
            qa_pair = match_result["qa_pair"]
            match_score = match_result["match_score"]

            print("✅ MATCH FOUND!")
            print(f"   Score: {match_score:.2%}")
            print(f"   Matched Question: {qa_pair.get('question')}")
            print(f"   Answer_len={len(str(qa_pair.get('answer') or ''))}")
            print(f"{'=' * 80}\n")

            return {
                "success": True,
                "match_found": True,
                "match_score": match_score,
                "matched_question": qa_pair.get("question"),
                "answer": qa_pair.get("answer"),
                "category": qa_pair.get("category"),
                "language": qa_pair.get("language"),
            }
        else:
            print("❌ NO MATCH FOUND")
            print(f"{'=' * 80}\n")

            return {"success": True, "match_found": False, "message": "No matching Q&A pair found (threshold: 90%)"}
    except Exception as e:
        print(f"❌ Error testing Q&A match: {e}")
        import traceback

        traceback.print_exc()
        return {"success": False, "error": str(e)}
