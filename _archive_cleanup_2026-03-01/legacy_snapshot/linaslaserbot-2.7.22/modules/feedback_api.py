# -*- coding: utf-8 -*-
"""
Feedback API module: Conversation feedback endpoints
Handles feedback collection, statistics, and wrong answer tracking.
"""

from typing import Optional

from modules.core import app
from modules.models import FeedbackRequest
from services.conversation_feedback_service import feedback_service


@app.post("/api/feedback/submit")
async def submit_feedback(feedback: FeedbackRequest):
    """Submit feedback on a bot response"""
    try:
        result = await feedback_service.submit_feedback(
            conversation_id=feedback.conversation_id,
            message_id=feedback.message_id,
            user_question=feedback.user_question,
            bot_response=feedback.bot_response,
            feedback_type=feedback.feedback_type,
            correct_answer=feedback.correct_answer,
            feedback_reason=feedback.feedback_reason,
            operator_id=feedback.operator_id,
            language=feedback.language
        )
        return result
    except Exception as e:
        print(f"❌ Error submitting feedback: {e}")
        return {"success": False, "error": str(e)}


@app.get("/api/feedback/stats")
async def get_feedback_stats():
    """Get feedback statistics"""
    try:
        stats = feedback_service.get_feedback_stats()
        return {"success": True, "stats": stats}
    except Exception as e:
        print(f"❌ Error getting feedback stats: {e}")
        return {"success": False, "error": str(e)}


@app.get("/api/feedback/recent")
async def get_recent_feedback(limit: int = 10):
    """Get recent feedback entries"""
    try:
        feedback = feedback_service.get_recent_feedback(limit)
        return {"success": True, "feedback": feedback}
    except Exception as e:
        print(f"❌ Error getting recent feedback: {e}")
        return {"success": False, "error": str(e)}


@app.get("/api/feedback/wrong-answers")
async def get_wrong_answers(limit: int = 20):
    """Get recent wrong answers that need attention"""
    try:
        wrong_answers = feedback_service.get_wrong_answers(limit)
        return {"success": True, "wrong_answers": wrong_answers}
    except Exception as e:
        print(f"❌ Error getting wrong answers: {e}")
        return {"success": False, "error": str(e)}
