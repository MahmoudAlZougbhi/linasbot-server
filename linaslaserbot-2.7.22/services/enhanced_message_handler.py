# Enhanced Message Handler
# Integrates all features: training mode, gender detection, message buffering

from typing import Dict, Optional, Tuple
from datetime import datetime
import asyncio

from services.training_mode import training_manager
from services.message_buffer import message_buffer
from services.gender_detection import gender_service
from services.qa_manager_service import qa_manager, get_qa_response

class EnhancedMessageHandler:
    """
    Handles all message processing with enhanced features
    """
    
    def __init__(self):
        self.user_states = {}  # Track user conversation states
    
    async def process_message(
        self, 
        user_id: str, 
        message: str, 
        message_type: str = "text",
        get_bot_response_func = None,
        is_voice: bool = False
    ) -> Dict:
        """
        Process incoming message with all features
        Returns response dict with message and metadata
        """
        
        # 1. Check if admin is in training mode
        if training_manager.is_admin(user_id):
            # Check for training activation
            if message.lower() in ["training", "تدريب", "entrainement"]:
                result = training_manager.activate_training(user_id)
                return {
                    "response": result["message"],
                    "mode": "training_activated",
                    "success": result["success"]
                }
            
            # Check if already in training session
            if user_id in training_manager.training_sessions:
                result = await training_manager.process_training_input(user_id, message)
                
                # If Q&A was saved, add it to qa_manager
                if result.get("qa_saved"):
                    qa_entry = result["qa_saved"]
                    qa_manager.create_qa_pair(
                        question_ar=qa_entry["ar"]["question"],
                        answer_ar=qa_entry["ar"]["answer"],
                        question_en=qa_entry.get("en", {}).get("question"),
                        answer_en=qa_entry.get("en", {}).get("answer"),
                        question_fr=qa_entry.get("fr", {}).get("question"),
                        answer_fr=qa_entry.get("fr", {}).get("answer"),
                        question_franco=qa_entry.get("franco", {}).get("question"),
                        answer_franco=qa_entry.get("franco", {}).get("answer"),
                        category="training"
                    )
                
                return {
                    "response": result["message"],
                    "mode": "training",
                    "success": result["success"]
                }
        
        # 2. Check gender detection
        user_gender = await gender_service.check_user_gender(user_id)
        
        # If waiting for gender response
        if gender_service.is_waiting_for_gender(user_id):
            detected_gender = gender_service.process_gender_response(user_id, message)
            if detected_gender:
                confirmation = gender_service.get_gender_confirmation_message(
                    detected_gender, 
                    self._detect_language(message)
                )
                return {
                    "response": confirmation,
                    "mode": "gender_detected",
                    "gender": detected_gender,
                    "success": True
                }
            else:
                # Still waiting for valid gender
                return {
                    "response": "الرجاء الرد بـ 'رجل' أو 'امرأة'\nPlease reply with 'male' or 'female'",
                    "mode": "waiting_gender",
                    "success": False
                }
        
        # If new user without gender
        if not user_gender:
            gender_request = gender_service.create_gender_request(
                user_id, 
                self._detect_language(message)
            )
            return {
                "response": gender_request["message"],
                "mode": "requesting_gender",
                "success": True
            }
        
        # 3. Handle voice messages with confirmation
        if is_voice:
            # Add confirmation prefix
            lang = self._detect_language(message)
            confirmations = {
                "ar": f"سمعتك تقول: '{message}'\n\n",
                "en": f"I heard you say: '{message}'\n\n",
                "fr": f"Je vous ai entendu dire: '{message}'\n\n"
            }
            prefix = confirmations.get(lang, confirmations["ar"])
            
            # Get response
            if get_bot_response_func:
                bot_response = await get_bot_response_func(message)
                final_response = prefix + bot_response
            else:
                final_response = prefix + "شكراً لرسالتك الصوتية."
            
            # Adapt for gender
            final_response = gender_service.adapt_response_style(
                final_response, 
                user_gender, 
                lang
            )
            
            return {
                "response": final_response,
                "mode": "voice_confirmed",
                "gender": user_gender,
                "success": True
            }
        
        # 4. Regular message processing with buffering
        # For text messages, use buffering
        if message_type == "text" and not is_voice:
            # Define callback for when buffer is ready
            async def process_buffered_message(uid, combined_msg):
                # Process the combined message
                if get_bot_response_func:
                    response = await get_bot_response_func(combined_msg)
                else:
                    # Check Q&A first
                    qa_response = get_qa_response(combined_msg, self._detect_language(combined_msg))
                    response = qa_response if qa_response else "شكراً لرسالتك"
                
                # Adapt for gender
                response = gender_service.adapt_response_style(
                    response,
                    user_gender,
                    self._detect_language(combined_msg)
                )
                
                # Store for retrieval
                self.user_states[uid] = {
                    "last_response": response,
                    "timestamp": datetime.now()
                }
            
            # Add to buffer
            buffered = await message_buffer.add_message(
                user_id,
                message,
                message_type,
                process_buffered_message
            )
            
            if buffered:
                # Message is buffered, wait for more
                return {
                    "response": None,  # Don't respond yet
                    "mode": "buffering",
                    "buffered": True,
                    "success": True
                }
        
        # 5. Process immediately (no buffering)
        if get_bot_response_func:
            response = await get_bot_response_func(message)
        else:
            # Check Q&A first
            qa_response = get_qa_response(message, self._detect_language(message))
            response = qa_response if qa_response else "شكراً لرسالتك"
        
        # Adapt for gender
        response = gender_service.adapt_response_style(
            response,
            user_gender,
            self._detect_language(message)
        )
        
        return {
            "response": response,
            "mode": "normal",
            "gender": user_gender,
            "success": True
        }
    
    def get_buffered_response(self, user_id: str) -> Optional[str]:
        """Get buffered response if ready"""
        if user_id in self.user_states:
            state = self.user_states[user_id]
            # Return and clear
            response = state.get("last_response")
            del self.user_states[user_id]
            return response
        return None
    
    def _detect_language(self, text: str) -> str:
        """Simple language detection"""
        text_lower = text.lower()
        
        # Arabic detection
        arabic_chars = sum(1 for char in text if '\u0600' <= char <= '\u06FF')
        if arabic_chars > len(text) * 0.3:
            return "ar"
        
        # French detection
        french_words = ['bonjour', 'merci', 'comment', 'vous']
        if any(word in text_lower for word in french_words):
            return "fr"
        
        # Default to English
        return "en"

# Global instance
enhanced_handler = EnhancedMessageHandler()