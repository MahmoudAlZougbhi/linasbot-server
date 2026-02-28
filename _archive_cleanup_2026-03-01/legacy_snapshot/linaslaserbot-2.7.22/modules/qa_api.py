# -*- coding: utf-8 -*-
"""
QA API module: Q&A Management endpoints
Handles CRUD operations and search for Q&A pairs in the database.
"""

from typing import Optional
from fastapi import Request

from modules.core import app
from services.qa_database_service import qa_db_service


# DEBUG: Test endpoint to verify routes are registered
@app.get("/api/qa/test")
async def test_qa_endpoint():
    """Test endpoint to verify Q&A API is working"""
    return {
        "success": True,
        "message": "Q&A API is working!",
        "endpoints": [
            "GET /api/qa/list",
            "POST /api/qa/create",
            "PUT /api/qa/{qa_id}",
            "DELETE /api/qa/{qa_id}",
            "GET /api/qa/search",
            "POST /api/qa/test-match",
            "GET /api/qa/categories",
            "GET /api/qa/statistics"
        ]
    }


@app.get("/api/qa/list")
async def list_qa_pairs(
    category: Optional[str] = None,
    language: str = "ar",
    active_only: bool = True
):
    """List all Q&A pairs with optional filtering - FROM DATABASE"""
    try:
        response = await qa_db_service.get_qa_pairs(
            category=category,
            language=language,
            active_only=active_only
        )
        return response
    except Exception as e:
        print(f"❌ Error in list_qa_pairs: {e}")
        return {"success": False, "error": str(e)}


@app.post("/api/qa/create")
async def create_qa_pair(qa_data: dict):
    """Create a new Q&A pair in database"""
    try:
        print("\n" + "="*80)
        print("🔵 DEBUG: /api/qa/create endpoint hit!")
        print("="*80)
        print(f"📥 Received qa_data type: {type(qa_data)}")
        print(f"📥 Received qa_data: {qa_data}")
        question_ar = qa_data.get("question_ar", "").strip()
        answer_ar = qa_data.get("answer_ar", "").strip()
        question_en = qa_data.get("question_en", "").strip()
        answer_en = qa_data.get("answer_en", "").strip()
        question_fr = qa_data.get("question_fr", "").strip()
        answer_fr = qa_data.get("answer_fr", "").strip()
        question_franco = qa_data.get("question_franco", "").strip()
        answer_franco = qa_data.get("answer_franco", "").strip()

        # Accept compact payload shape: {question, answer, language, category, tags}
        question = qa_data.get("question", "").strip()
        answer = qa_data.get("answer", "").strip()
        if question and answer and not any(
            [question_ar, question_en, question_fr, question_franco]
        ):
            detected_language = language_detection_service.normalize_training_language(
                qa_data.get("language"),
                default=language_detection_service.detect_training_language(question),
            )
            if detected_language == "ar":
                question_ar = question
                answer_ar = answer
            elif detected_language == "en":
                question_en = question
                answer_en = answer
            elif detected_language == "fr":
                question_fr = question
                answer_fr = answer
            else:
                question_franco = question
                answer_franco = answer

        print(f"📥 question_ar: {question_ar}")
        print(f"📥 answer_ar: {answer_ar}")
        print(f"📥 question_en: {question_en}")
        print(f"📥 answer_en: {answer_en}")
        print(f"📥 question_fr: {question_fr}")
        print(f"📥 answer_fr: {answer_fr}")
        print(f"📥 question_franco: {question_franco}")
        print(f"📥 answer_franco: {answer_franco}")
        print(f"📥 category: {qa_data.get('category', 'general')}")
        print(f"📥 tags: {qa_data.get('tags', [])}")
        print("="*80 + "\n")
        
        response = await qa_db_service.create_qa_pair(
            question_ar=question_ar,
            answer_ar=answer_ar,
            question_en=question_en,
            answer_en=answer_en,
            question_fr=question_fr,
            answer_fr=answer_fr,
            question_franco=question_franco,
            answer_franco=answer_franco,
            category=qa_data.get("category", "general"),
            tags=qa_data.get("tags", [])
        )
        
        print("\n" + "="*80)
        print("✅ DEBUG: Q&A creation response")
        print("="*80)
        print(f"📤 Response: {response}")
        print("="*80 + "\n")
        
        return response
    except Exception as e:
        print(f"\n❌ ERROR in create_qa_pair: {e}")
        import traceback
        traceback.print_exc()
        return {"success": False, "error": str(e)}


@app.put("/api/qa/{qa_id}")
async def update_qa_pair(qa_id: int, updates: dict):
    """Update an existing Q&A pair in database"""
    try:
        response = await qa_db_service.update_qa_pair(qa_id, updates)
        return response
    except Exception as e:
        print(f"❌ Error in update_qa_pair: {e}")
        return {"success": False, "error": str(e)}


@app.delete("/api/qa/{qa_id}")
async def delete_qa_pair(qa_id: int):
    """Delete a Q&A pair from database (soft delete)"""
    try:
        response = await qa_db_service.delete_qa_pair(qa_id)
        return response
    except Exception as e:
        print(f"❌ Error in delete_qa_pair: {e}")
        return {"success": False, "error": str(e)}


@app.get("/api/qa/search")
async def search_qa_pairs(
    query: str,
    language: str = "ar",
    category: Optional[str] = None
):
    """Search Q&A pairs in database"""
    try:
        response = await qa_db_service.search_qa_pairs(query, language)
        return response
    except Exception as e:
        print(f"❌ Error in search_qa_pairs: {e}")
        return {"success": False, "error": str(e)}


@app.post("/api/qa/test-match")
async def test_qa_match(test_data: dict):
    """Test if a question matches any Q&A pair in database"""
    try:
        question = test_data.get("question", "")
        language = test_data.get("language", "ar")
        
        if not question:
            return {"success": False, "error": "Question is required"}
        
        match_result = await qa_db_service.find_match(question, language)
        
        if match_result:
            qa_pair = match_result["qa_pair"]
            answer = qa_db_service._extract_answer_for_language(qa_pair, language)
            
            return {
                "success": True,
                "match_found": True,
                "match_score": match_result["match_score"],
                "qa_pair": qa_pair,
                "answer": answer
            }
        else:
            return {
                "success": True,
                "match_found": False,
                "message": "No matching Q&A pair found"
            }
    except Exception as e:
        print(f"❌ Error in test_qa_match: {e}")
        return {"success": False, "error": str(e)}


@app.get("/api/qa/categories")
async def get_qa_categories():
    """Get list of available categories from database"""
    try:
        response = await qa_db_service.get_categories()
        return response
    except Exception as e:
        print(f"❌ Error in get_qa_categories: {e}")
        return {"success": False, "error": str(e)}


@app.get("/api/qa/statistics")
async def get_qa_statistics():
    """Get Q&A database statistics"""
    try:
        response = await qa_db_service.get_statistics()
        return response
    except Exception as e:
        print(f"❌ Error in get_qa_statistics: {e}")
        return {"success": False, "error": str(e)}


@app.post("/api/qa/track-usage")
async def track_qa_usage(usage_data: dict):
    """Track Q&A usage in database"""
    try:
        qa_id = usage_data.get("qa_id")
        customer_phone = usage_data.get("customer_phone")
        matched = usage_data.get("matched", True)
        match_score = usage_data.get("match_score", 0)
        
        if not qa_id:
            return {"success": False, "error": "qa_id is required"}
        
        response = await qa_db_service.track_usage(
            qa_id=qa_id,
            customer_phone=customer_phone,
            matched=matched,
            match_score=match_score
        )
        return response
    except Exception as e:
        print(f"❌ Error in track_qa_usage: {e}")
        return {"success": False, "error": str(e)}


# Training mode endpoints (bridge for dashboard compatibility)
@app.get("/api/training/list")
async def list_training_data():
    """Bridge endpoint - redirects to Q&A list"""
    return await list_qa_pairs()


@app.post("/api/training/create")
async def create_training_data(training_data: dict):
    """Bridge endpoint - redirects to Q&A create"""
    return await create_qa_pair(training_data)
