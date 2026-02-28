# Training Mode Service
# Implements requirement #2 from project specifications

import json
from typing import Dict, Optional, Tuple
from datetime import datetime
from openai import AsyncOpenAI
import os
from dotenv import load_dotenv

load_dotenv()

class TrainingModeManager:
    """
    Manages training mode for admin users
    - Activated by sending 'training' from admin
    - Asks for Q&A, rewrites professionally, saves in 4 languages
    """
    
    def __init__(self):
        self.client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        self.training_sessions = {}  # user_id -> training state
        self.admin_numbers = [
            os.getenv("TRAINER_WHATSAPP_NUMBER", "9613956607"),
            # Add more admin numbers here
        ]
    
    def is_admin(self, phone: str) -> bool:
        """Check if user is admin"""
        # Remove country code variations
        clean_phone = phone.replace("+", "").replace("-", "").replace(" ", "")
        for admin in self.admin_numbers:
            if admin in clean_phone or clean_phone in admin:
                return True
        return False
    
    def activate_training(self, user_id: str) -> Dict:
        """Activate training mode for admin"""
        if not self.is_admin(user_id):
            return {
                "success": False,
                "message": "عذراً، هذه الميزة متاحة للمسؤولين فقط.\nSorry, this feature is only for admins."
            }
        
        self.training_sessions[user_id] = {
            "state": "waiting_qa",
            "started_at": datetime.now().isoformat()
        }
        
        return {
            "success": True,
            "message": "🎓 **وضع التدريب مفعّل**\n\nما الذي تريد أن تعلمني إياه؟ اكتب السؤال والجواب الصحيح.\n\n**Training Mode Activated**\n\nWhat do you want to teach me? Write the question and the correct answer.\n\nمثال/Example:\nQ: ما هي ساعات العمل؟\nA: نعمل من 9 صباحاً حتى 6 مساءً"
        }
    
    async def process_training_input(self, user_id: str, message: str) -> Dict:
        """Process training input from admin"""
        
        if user_id not in self.training_sessions:
            return {"success": False, "message": "Training mode not active"}
        
        session = self.training_sessions[user_id]
        
        if session["state"] == "waiting_qa":
            # Parse Q&A from message
            qa_parsed = self._parse_qa(message)
            if not qa_parsed:
                return {
                    "success": False,
                    "message": "❌ الرجاء كتابة السؤال والجواب بالشكل الصحيح:\nQ: السؤال\nA: الجواب\n\nPlease write in correct format:\nQ: Question\nA: Answer"
                }
            
            question, answer = qa_parsed
            
            # Rewrite answer professionally using AI
            rewritten = await self._rewrite_professionally(question, answer)
            
            # Generate translations
            translations = await self._generate_translations(question, rewritten)
            
            # Store in session for confirmation
            session["state"] = "waiting_confirmation"
            session["original_q"] = question
            session["original_a"] = answer
            session["rewritten_a"] = rewritten
            session["translations"] = translations
            
            self.training_sessions[user_id] = session
            
            return {
                "success": True,
                "message": f"""✨ **تمت إعادة الصياغة بشكل احترافي:**

**السؤال:** {question}

**الجواب الأصلي:** {answer}

**الجواب المحسّن:** {rewritten}

**الترجمات:**
🇬🇧 EN: {translations.get('en', {}).get('answer', 'N/A')}
🇫🇷 FR: {translations.get('fr', {}).get('answer', 'N/A')}

للحفظ اكتب: **تأكيد** أو **Confirm**
للإلغاء اكتب: **إلغاء** أو **Cancel**"""
            }
        
        elif session["state"] == "waiting_confirmation":
            if message.lower() in ["تأكيد", "confirm", "yes", "نعم"]:
                # Save Q&A (will be saved to API when available)
                qa_entry = {
                    "id": f"qa_{datetime.now().timestamp()}",
                    "ar": {
                        "question": session["original_q"],
                        "answer": session["rewritten_a"]
                    },
                    "en": session["translations"].get("en", {}),
                    "fr": session["translations"].get("fr", {}),
                    "franco": session["translations"].get("franco", {}),
                    "created_by": user_id,
                    "created_at": datetime.now().isoformat()
                }
                
                # Clear session
                del self.training_sessions[user_id]
                
                return {
                    "success": True,
                    "message": "✅ تم حفظ المعلومة بنجاح في جميع اللغات!\n\nSuccessfully saved in all languages!\n\nيمكنك إضافة معلومة جديدة بكتابة 'training' مرة أخرى.",
                    "qa_saved": qa_entry
                }
            
            elif message.lower() in ["إلغاء", "cancel", "no", "لا"]:
                del self.training_sessions[user_id]
                return {
                    "success": True,
                    "message": "❌ تم إلغاء التدريب.\n\nTraining cancelled."
                }
            
            else:
                return {
                    "success": False,
                    "message": "الرجاء كتابة 'تأكيد' للحفظ أو 'إلغاء' للإلغاء.\n\nPlease type 'Confirm' to save or 'Cancel' to cancel."
                }
        
        return {"success": False, "message": "Unknown training state"}
    
    def _parse_qa(self, message: str) -> Optional[Tuple[str, str]]:
        """Parse Q&A from message"""
        lines = message.strip().split('\n')
        question = None
        answer = None
        
        for i, line in enumerate(lines):
            line = line.strip()
            if line.lower().startswith('q:') or line.lower().startswith('س:'):
                question = line[2:].strip()
            elif line.lower().startswith('a:') or line.lower().startswith('ج:'):
                answer = line[2:].strip()
            elif question and not answer:
                # If question found but no A: prefix, treat next line as answer
                answer = line
        
        if question and answer:
            return (question, answer)
        return None
    
    async def _rewrite_professionally(self, question: str, answer: str) -> str:
        """Rewrite answer professionally using AI"""
        try:
            response = await self.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {
                        "role": "system",
                        "content": """You are a professional content writer for Lina's Laser Center.
                        Rewrite the given answer to be more professional, friendly, and informative.
                        Keep the same language as the input. Add relevant emojis.
                        Be concise but complete. Maximum 2-3 sentences."""
                    },
                    {
                        "role": "user",
                        "content": f"Question: {question}\nAnswer to rewrite: {answer}"
                    }
                ],
                temperature=0.7,
                max_tokens=200
            )
            if not response.choices:
                return answer
            return response.choices[0].message.content.strip()
        except Exception as e:
            print(f"Error rewriting: {e}")
            return answer  # Return original if error
    
    async def _generate_translations(self, question: str, answer: str) -> Dict:
        """Generate translations for all languages"""
        try:
            response = await self.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {
                        "role": "system",
                        "content": """Translate the Q&A to English, French, and Franco-Arabic.
                        Return as JSON with keys: en, fr, franco
                        Each should have 'question' and 'answer' fields."""
                    },
                    {
                        "role": "user",
                        "content": f"Question: {question}\nAnswer: {answer}"
                    }
                ],
                temperature=0.3,
                max_tokens=500,
                response_format={"type": "json_object"}
            )
            if not response.choices:
                raise ValueError("GPT returned no choices")
            result = json.loads(response.choices[0].message.content)
            return result
        except Exception as e:
            print(f"Error translating: {e}")
            return {
                "en": {"question": question, "answer": answer},
                "fr": {"question": question, "answer": answer},
                "franco": {"question": question, "answer": answer}
            }

# Global instance
training_manager = TrainingModeManager()