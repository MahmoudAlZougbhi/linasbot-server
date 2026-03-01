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
        Answer: always stored in Arabic (Franco → auto-translate to Arabic) in both Arabic and Franco sections.
        Question in Arabic section: always Arabic script; if question was Franco → translate to Arabic for ar.
        """
        def _looks_franco(text: str) -> bool:
            if not text or not isinstance(text, str):
                return False
            arabic_range = range(0x0600, 0x06FF + 1)
            has_arabic = any(ord(c) in arabic_range for c in text)
            return not has_arabic and any(c.isalpha() for c in text)

        try:
            norm_source = language_detection_service.normalize_training_language(source_language, default="ar")

            # 1) Answer always Arabic: if answer is Franco, translate to Arabic first
            answer_ar_canonical = (correct_answer or "").strip()
            if _looks_franco(answer_ar_canonical):
                ar_ans = await language_detection_service.translate_training_pair(
                    question=answer_ar_canonical, answer=answer_ar_canonical,
                    source_language="franco" if _looks_franco(answer_ar_canonical) else norm_source,
                    target_languages=["ar"],
                )
                ar_ans_trans = ar_ans.get("translations", {}).get("ar", {})
                if ar_ans_trans.get("answer"):
                    answer_ar_canonical = ar_ans_trans["answer"]
                elif ar_ans_trans.get("question"):
                    answer_ar_canonical = ar_ans_trans["question"]

            # 2) Translate Q&A to all languages (answer passed as Arabic so ar/franco both get Arabic answer)
            result = await language_detection_service.translate_training_pair(
                question=user_question,
                answer=answer_ar_canonical,
                source_language=norm_source,
                target_languages=["ar", "en", "fr", "franco"],
            )
            translations = result.get("translations", {})

            qa_data = {
                "question_ar": translations.get("ar", {}).get("question", ""),
                "answer_ar": answer_ar_canonical,
                "question_en": translations.get("en", {}).get("question", user_question if norm_source == "en" else ""),
                "answer_en": translations.get("en", {}).get("answer", ""),
                "question_fr": translations.get("fr", {}).get("question", user_question if norm_source == "fr" else ""),
                "answer_fr": translations.get("fr", {}).get("answer", ""),
                "question_franco": translations.get("franco", {}).get("question", user_question if norm_source == "franco" else ""),
                "answer_franco": answer_ar_canonical,
                "category": category,
                "tags": ["operator_trained", "save_to_faq", "live_chat"]
            }

            # 3) Arabic section question MUST be Arabic script: if missing or Franco, translate
            if not qa_data["question_ar"] or _looks_franco(qa_data["question_ar"]):
                q_ar_result = await language_detection_service.translate_training_pair(
                    question=user_question, answer=answer_ar_canonical,
                    source_language=norm_source if _looks_franco(user_question) else "ar",
                    target_languages=["ar"],
                )
                ar_q = q_ar_result.get("translations", {}).get("ar", {})
                if ar_q.get("question"):
                    qa_data["question_ar"] = ar_q["question"]
                elif not qa_data["question_ar"] and not _looks_franco(user_question):
                    qa_data["question_ar"] = user_question

            # Never put Franco in Arabic section
            if _looks_franco(qa_data["question_ar"]):
                qa_data["question_ar"] = ""
            if not qa_data["question_ar"] and not qa_data["question_en"]:
                return {"success": False, "error": "Could not produce Arabic question for FAQ (ar section must be Arabic script)"}

            qa_data["answer_franco"] = qa_data["answer_ar"]

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
