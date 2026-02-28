# -*- coding: utf-8 -*-
"""
Q&A Management API Routes
"""
from fastapi import APIRouter
from typing import Optional
import datetime
from services.qa_manager_service import qa_manager

router = APIRouter()

@router.get("/qa/list")
async def list_qa_pairs(
    category: Optional[str] = None,
    language: Optional[str] = None,
    active_only: bool = True
):
    """List all Q&A pairs with optional filtering"""
    try:
        qa_pairs = qa_manager.search_qa_pairs(
            category=category,
            language=language,
            active_only=active_only
        )
        return {
            "success": True,
            "data": qa_pairs,
            "count": len(qa_pairs)
        }
    except Exception as e:
        return {"success": False, "error": str(e)}

@router.post("/qa/create")
async def create_qa_pair(qa_data: dict):
    """Create a new Q&A pair in all 4 languages"""
    try:
        required_fields = ["question_ar", "answer_ar", "question_en", "answer_en", 
                          "question_fr", "answer_fr", "question_franco", "answer_franco"]
        
        for field in required_fields:
            if field not in qa_data:
                return {"success": False, "error": f"Missing required field: {field}"}
        
        qa_id = qa_manager.create_qa_pair(
            question_ar=qa_data["question_ar"],
            answer_ar=qa_data["answer_ar"],
            question_en=qa_data["question_en"],
            answer_en=qa_data["answer_en"],
            question_fr=qa_data["question_fr"],
            answer_fr=qa_data["answer_fr"],
            question_franco=qa_data["question_franco"],
            answer_franco=qa_data["answer_franco"],
            category=qa_data.get("category", "general"),
            tags=qa_data.get("tags", [])
        )
        
        return {
            "success": True,
            "qa_id": qa_id,
            "message": "Q&A pair created successfully"
        }
    except Exception as e:
        return {"success": False, "error": str(e)}

@router.put("/qa/{qa_id}")
async def update_qa_pair(qa_id: str, updates: dict):
    """Update an existing Q&A pair"""
    try:
        success = qa_manager.update_qa_pair(qa_id, updates)
        if success:
            return {
                "success": True,
                "message": "Q&A pair updated successfully"
            }
        else:
            return {"success": False, "error": "Q&A pair not found"}
    except Exception as e:
        return {"success": False, "error": str(e)}

@router.delete("/qa/{qa_id}")
async def delete_qa_pair(qa_id: str):
    """Delete a Q&A pair (soft delete)"""
    try:
        success = qa_manager.delete_qa_pair(qa_id)
        if success:
            return {
                "success": True,
                "message": "Q&A pair deleted successfully"
            }
        else:
            return {"success": False, "error": "Q&A pair not found"}
    except Exception as e:
        return {"success": False, "error": str(e)}

@router.get("/qa/search")
async def search_qa_pairs(
    query: str,
    language: str = "ar",
    category: Optional[str] = None
):
    """Search Q&A pairs"""
    try:
        results = qa_manager.search_qa_pairs(
            query=query,
            category=category,
            language=language
        )
        return {
            "success": True,
            "data": results,
            "count": len(results)
        }
    except Exception as e:
        return {"success": False, "error": str(e)}

@router.post("/qa/test-match")
async def test_qa_match(test_data: dict):
    """Test if a question matches any Q&A pair"""
    try:
        question = test_data.get("question", "")
        language = test_data.get("language", "ar")
        
        if not question:
            return {"success": False, "error": "Question is required"}
        
        match_result = qa_manager.find_match(question, language)
        
        if match_result:
            return {
                "success": True,
                "match_found": True,
                "match_score": match_result["match_score"],
                "qa_pair": match_result["qa_pair"],
                "answer": match_result["qa_pair"][language]["answer"] if language in match_result["qa_pair"] else match_result["qa_pair"]["ar"]["answer"]
            }
        else:
            return {
                "success": True,
                "match_found": False,
                "message": "No matching Q&A pair found"
            }
    except Exception as e:
        return {"success": False, "error": str(e)}

@router.get("/qa/categories")
async def get_qa_categories():
    """Get list of available categories"""
    try:
        categories = qa_manager.qa_database.get("categories", ["general", "pricing", "services", "appointments", "medical"])
        return {
            "success": True,
            "categories": categories
        }
    except Exception as e:
        return {"success": False, "error": str(e)}

@router.get("/qa/statistics")
async def get_qa_statistics():
    """Get Q&A database statistics"""
    try:
        stats = qa_manager.get_statistics()
        return {
            "success": True,
            "statistics": stats
        }
    except Exception as e:
        return {"success": False, "error": str(e)}

@router.post("/qa/track-usage")
async def track_qa_usage(usage_data: dict):
    """Track Q&A usage"""
    try:
        qa_id = usage_data.get("qa_id")
        customer_phone = usage_data.get("customer_phone")
        
        if not qa_id:
            return {"success": False, "error": "qa_id is required"}
        
        for qa in qa_manager.qa_database["qa_pairs"]:
            if qa["id"] == qa_id:
                qa["usage_count"] = qa.get("usage_count", 0) + 1
                qa["last_used"] = datetime.datetime.now().isoformat()
                if customer_phone:
                    if "used_by" not in qa:
                        qa["used_by"] = []
                    qa["used_by"].append({
                        "phone": customer_phone,
                        "timestamp": datetime.datetime.now().isoformat()
                    })
                qa_manager.save_database()
                return {
                    "success": True,
                    "message": "Usage tracked successfully"
                }
        
        return {"success": False, "error": "Q&A pair not found"}
    except Exception as e:
        return {"success": False, "error": str(e)}

# Training mode endpoints (bridge for dashboard compatibility)
@router.get("/api/training/list")
async def list_training_data():
    """Bridge endpoint - redirects to Q&A list"""
    return await list_qa_pairs()

@router.post("/api/training/create")
async def create_training_data(training_data: dict):
    """Bridge endpoint - redirects to Q&A create"""
    return await create_qa_pair(training_data)
