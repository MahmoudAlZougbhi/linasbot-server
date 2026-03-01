#!/usr/bin/env python3
"""
Conversation Feedback Service
Allows operators to provide feedback on bot responses and train the bot
"""

import os
from datetime import datetime
from typing import Dict, List, Optional
from dotenv import load_dotenv
from services.qa_database_service import qa_db_service
from services.language_detection_service import language_detection_service

load_dotenv()


class ConversationFeedbackService:
    """
    Service to handle conversation feedback and bot training
    """
    
    def __init__(self):
        self.feedback_log = []  # In-memory log (could be moved to database)
        print("🎓 ConversationFeedbackService initialized")
    
    async def submit_feedback(
        self,
        conversation_id: str,
        message_id: str,
        user_question: str,
        bot_response: str,
        feedback_type: str,  # 'good', 'wrong', 'inappropriate', 'unclear'
        correct_answer: Optional[str] = None,
        feedback_reason: Optional[str] = None,
        operator_id: Optional[str] = None,
        language: str = "ar"
    ) -> Dict:
        """
        Submit feedback on a bot response
        
        Args:
            conversation_id: ID of the conversation
            message_id: ID of the specific message
            user_question: The user's original question
            bot_response: The bot's response that received feedback
            feedback_type: Type of feedback (good, wrong, inappropriate, unclear)
            correct_answer: The correct answer (if feedback_type is 'wrong')
            feedback_reason: Reason for the feedback
            operator_id: ID of the operator providing feedback
            language: Language of the conversation
        
        Returns:
            dict: Result of feedback submission
        """
        try:
            feedback_entry = {
                "conversation_id": conversation_id,
                "message_id": message_id,
                "user_question": user_question,
                "bot_response": bot_response,
                "feedback_type": feedback_type,
                "correct_answer": correct_answer,
                "feedback_reason": feedback_reason,
                "operator_id": operator_id,
                "language": language,
                "timestamp": datetime.now().isoformat()
            }
            
            # Log feedback
            self.feedback_log.append(feedback_entry)
            print(f"📝 Feedback received: {feedback_type} for message {message_id}")
            print(f"   Question: {user_question}")
            print(f"   Bot Response: {bot_response}")
            
            # If feedback is negative and correct answer provided, train the bot (single language)
            if feedback_type == "wrong" and correct_answer:
                print(f"🎓 Training bot with correct answer...")
                training_result = await self.train_from_feedback(
                    user_question=user_question,
                    correct_answer=correct_answer,
                    language=language,
                    category="feedback_trained"
                )
                
                return {
                    "success": True,
                    "message": "Feedback submitted and bot trained successfully",
                    "feedback_id": len(self.feedback_log) - 1,
                    "training_result": training_result
                }
            
            # If "save_to_faq" (Like on AI answer): save to LOCAL QA so it appears in Manage Data
            if feedback_type == "save_to_faq" and correct_answer:
                print(f"🎓 Saving to FAQ (Manage Data) in 4 languages...")
                try:
                    from modules.local_qa_api import create_local_qa_pair_internal
                    local_result = await create_local_qa_pair_internal(
                        question=user_question,
                        answer=correct_answer,
                        language=language,
                        category="operator_trained",
                    )
                    if local_result.get("success"):
                        print(f"✅ Saved to Manage Data! Count: {local_result.get('count_created', 0)}")
                        return {
                            "success": True,
                            "message": "Saved to FAQ in 4 languages",
                            "feedback_id": len(self.feedback_log) - 1,
                            "training_result": {"success": True, "qa_id": "local"}
                        }
                    # Fallback to external QA if local fails
                    print(f"⚠️ Local save failed: {local_result.get('error')}, trying external QA...")
                except Exception as e:
                    print(f"⚠️ Local QA save error: {e}, trying external QA...")
                # Fallback: also save to external QA database
                training_result = await self.train_from_feedback_multilang(
                    user_question=user_question,
                    correct_answer=correct_answer,
                    source_language=language,
                    category="operator_trained"
                )
                return {
                    "success": True,
                    "message": "Saved to FAQ in 4 languages",
                    "feedback_id": len(self.feedback_log) - 1,
                    "training_result": training_result
                }
            
            return {
                "success": True,
                "message": "Feedback submitted successfully",
                "feedback_id": len(self.feedback_log) - 1
            }
            
        except Exception as e:
            print(f"❌ Error submitting feedback: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    async def train_from_feedback(
        self,
        user_question: str,
        correct_answer: str,
        language: str = "ar",
        category: str = "feedback_trained"
    ) -> Dict:
        """
        Train the bot by creating a Q&A pair from feedback
        
        Args:
            user_question: The user's question
            correct_answer: The correct answer
            language: Language of the Q&A
            category: Category for the Q&A pair
        
        Returns:
            dict: Result of training
        """
        try:
            # Prepare Q&A data based on language
            qa_data = {
                "question_ar": user_question if language == "ar" else "",
                "answer_ar": correct_answer if language == "ar" else "",
                "question_en": user_question if language == "en" else "",
                "answer_en": correct_answer if language == "en" else "",
                "question_fr": user_question if language == "fr" else "",
                "answer_fr": correct_answer if language == "fr" else "",
                "question_franco": user_question if language == "franco" else "",
                "answer_franco": correct_answer if language == "franco" else "",
                "category": category,
                "tags": ["operator_trained", "feedback"]
            }
            
            # Create Q&A pair in database
            result = await qa_db_service.create_qa_pair(**qa_data)
            
            if result.get("success"):
                qa_id = result.get("data", {}).get("qa_id")
                print(f"✅ Bot trained successfully! Q&A ID: {qa_id}")
                return {
                    "success": True,
                    "qa_id": qa_id,
                    "message": "Bot trained with new Q&A pair"
                }
            else:
                print(f"❌ Failed to train bot: {result.get('message')}")
                return {
                    "success": False,
                    "error": result.get("message")
                }
                
        except Exception as e:
            print(f"❌ Error training bot: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    async def train_from_feedback_multilang(
        self,
        user_question: str,
        correct_answer: str,
        source_language: str = "ar",
        category: str = "operator_trained"
    ) -> Dict:
        """
        Save Q&A to FAQ in all 4 languages (ar, en, fr, franco).
        Uses translation service to produce all language variants.
        """
        try:
            norm_source = language_detection_service.normalize_training_language(source_language, default="ar")
            result = await language_detection_service.translate_training_pair(
                question=user_question,
                answer=correct_answer,
                source_language=norm_source,
                target_languages=["ar", "en", "fr", "franco"],
            )
            translations = result.get("translations", {})
            
            qa_data = {
                "question_ar": translations.get("ar", {}).get("question", user_question if norm_source == "ar" else ""),
                "answer_ar": translations.get("ar", {}).get("answer", correct_answer if norm_source == "ar" else ""),
                "question_en": translations.get("en", {}).get("question", user_question if norm_source == "en" else ""),
                "answer_en": translations.get("en", {}).get("answer", correct_answer if norm_source == "en" else ""),
                "question_fr": translations.get("fr", {}).get("question", user_question if norm_source == "fr" else ""),
                "answer_fr": translations.get("fr", {}).get("answer", correct_answer if norm_source == "fr" else ""),
                "question_franco": translations.get("franco", {}).get("question", user_question if norm_source == "franco" else ""),
                "answer_franco": translations.get("franco", {}).get("answer", correct_answer if norm_source == "franco" else ""),
                "category": category,
                "tags": ["operator_trained", "save_to_faq", "live_chat"]
            }
            
            # Ensure we have at least Arabic or source language
            if not qa_data["question_ar"] and not qa_data["question_en"]:
                qa_data["question_ar"] = user_question
                qa_data["answer_ar"] = correct_answer
            
            result = await qa_db_service.create_qa_pair(**qa_data)
            
            if result.get("success"):
                qa_id = result.get("data", {}).get("qa_id")
                print(f"✅ Saved to FAQ in 4 languages! Q&A ID: {qa_id}")
                return {
                    "success": True,
                    "qa_id": qa_id,
                    "message": "Saved to FAQ in 4 languages"
                }
            return {
                "success": False,
                "error": result.get("message", "Unknown error")
            }
        except Exception as e:
            print(f"❌ Error saving to FAQ: {e}")
            return {"success": False, "error": str(e)}
    
    def get_feedback_stats(self) -> Dict:
        """
        Get statistics about feedback received
        
        Returns:
            dict: Feedback statistics
        """
        if not self.feedback_log:
            return {
                "total_feedback": 0,
                "good": 0,
                "wrong": 0,
                "inappropriate": 0,
                "unclear": 0,
                "trained_count": 0
            }
        
        stats = {
            "total_feedback": len(self.feedback_log),
            "good": sum(1 for f in self.feedback_log if f["feedback_type"] == "good"),
            "wrong": sum(1 for f in self.feedback_log if f["feedback_type"] == "wrong"),
            "inappropriate": sum(1 for f in self.feedback_log if f["feedback_type"] == "inappropriate"),
            "unclear": sum(1 for f in self.feedback_log if f["feedback_type"] == "unclear"),
            "trained_count": sum(1 for f in self.feedback_log if f["feedback_type"] == "wrong" and f["correct_answer"])
        }
        
        return stats
    
    def get_recent_feedback(self, limit: int = 10) -> List[Dict]:
        """
        Get recent feedback entries
        
        Args:
            limit: Maximum number of entries to return
        
        Returns:
            list: Recent feedback entries
        """
        return self.feedback_log[-limit:] if self.feedback_log else []
    
    def get_wrong_answers(self, limit: int = 20) -> List[Dict]:
        """
        Get recent wrong answers that need attention
        
        Args:
            limit: Maximum number of entries to return
        
        Returns:
            list: Wrong answer entries
        """
        wrong_answers = [
            f for f in self.feedback_log 
            if f["feedback_type"] == "wrong"
        ]
        return wrong_answers[-limit:] if wrong_answers else []


# Singleton instance
feedback_service = ConversationFeedbackService()


# Helper function for easy access
async def submit_conversation_feedback(
    conversation_id: str,
    message_id: str,
    user_question: str,
    bot_response: str,
    feedback_type: str,
    correct_answer: Optional[str] = None,
    feedback_reason: Optional[str] = None,
    operator_id: Optional[str] = None,
    language: str = "ar"
) -> Dict:
    """
    Submit feedback on a bot response
    """
    return await feedback_service.submit_feedback(
        conversation_id=conversation_id,
        message_id=message_id,
        user_question=user_question,
        bot_response=bot_response,
        feedback_type=feedback_type,
        correct_answer=correct_answer,
        feedback_reason=feedback_reason,
        operator_id=operator_id,
        language=language
    )
