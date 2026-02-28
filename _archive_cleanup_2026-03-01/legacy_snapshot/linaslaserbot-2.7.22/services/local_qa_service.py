#!/usr/bin/env python3
"""
Local Q&A Service - Replace Backend API with JSONL File Storage
Uses conversation_log.jsonl structure with added 'category' field
"""

import json
import os
from typing import List, Dict, Optional, Tuple
from datetime import datetime
from difflib import SequenceMatcher
import re
from pathlib import Path
from services.language_detection_service import language_detection_service


class LocalQAService:
    """Manages Q&A pairs using local JSONL file (no backend dependency)"""
    
    def __init__(self, data_path: str = None):
        # Use absolute path for production compatibility
        if data_path is None:
            # Try to use absolute path first, fallback to relative
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            data_path = os.path.join(base_dir, "data", "qa_pairs.jsonl")
        
        self.data_path = data_path
        self.match_threshold = 0.7  # 70% similarity threshold
        self.qa_pairs = self.load_from_jsonl()
        print(f"✅ LocalQAService initialized with {len(self.qa_pairs)} Q&A pairs from {self.data_path}")
    
    def load_from_jsonl(self) -> List[Dict]:
        """Load Q&A pairs from JSONL file"""
        qa_pairs = []
        
        if not os.path.exists(self.data_path):
            print(f"❌ Q&A file NOT FOUND at: {self.data_path}")
            print(f"   Current working directory: {os.getcwd()}")
            print(f"   Script directory: {os.path.dirname(os.path.abspath(__file__))}")
            # Try alternative path as fallback
            alt_path = "data/qa_pairs.jsonl"
            if os.path.exists(alt_path):
                print(f"   ⚠️ Found alternative at: {alt_path}, using that instead")
                self.data_path = alt_path
            else:
                return qa_pairs
        
        try:
            with open(self.data_path, 'r', encoding='utf-8') as f:
                for line_num, line in enumerate(f, 1):
                    if line.strip():
                        try:
                            qa_pair = json.loads(line)
                            # Add ID if not present
                            if 'id' not in qa_pair:
                                qa_pair['id'] = f"{qa_pair.get('question', '')}_{qa_pair.get('language', 'ar')}_{line_num}"
                            qa_pairs.append(qa_pair)
                        except json.JSONDecodeError as e:
                            print(f"❌ Error parsing line {line_num}: {e}")
                            continue
            
            print(f"✅ Loaded {len(qa_pairs)} Q&A pairs from JSONL")
            return qa_pairs
        except Exception as e:
            print(f"❌ Error loading Q&A file: {e}")
            return qa_pairs
    
    def save_to_jsonl(self):
        """Save Q&A pairs to JSONL file"""
        try:
            # Ensure directory exists
            data_dir = os.path.dirname(self.data_path)
            if data_dir:
                os.makedirs(data_dir, exist_ok=True)
            
            with open(self.data_path, 'w', encoding='utf-8') as f:
                for qa_pair in self.qa_pairs:
                    # Remove 'id' before saving (will be regenerated on load)
                    qa_to_save = {k: v for k, v in qa_pair.items() if k != 'id'}
                    f.write(json.dumps(qa_to_save, ensure_ascii=False) + '\n')
            
            print(f"✅ Saved {len(self.qa_pairs)} Q&A pairs to JSONL at: {self.data_path}")
            return True
        except PermissionError as e:
            print(f"❌ Permission denied writing to {self.data_path}: {e}")
            return False
        except Exception as e:
            print(f"❌ Error saving Q&A file: {e}")
            return False

    @staticmethod
    def _normalize_language(language: Optional[str], default: str = "ar") -> str:
        return language_detection_service.normalize_training_language(language, default=default)
    
    async def get_qa_pairs(self, category: str = None, language: str = None, active_only: bool = True) -> dict:
        """Get Q&A pairs with optional filtering"""
        filtered = self.qa_pairs

        if language:
            normalized_language = self._normalize_language(language, default="")
            filtered = [
                qa for qa in filtered
                if self._normalize_language(qa.get("language"), default="") == normalized_language
            ]
        
        if category:
            filtered = [qa for qa in filtered if qa.get("category") == category]
        
        print(f"📋 Retrieved {len(filtered)} Q&A pairs (filters: language={language}, category={category})")
        
        return {
            "success": True,
            "data": filtered,
            "count": len(filtered)
        }
    
    async def create_qa_pair(self, 
                            question: str, 
                            answer: str,
                            language: str = "ar",
                            category: str = "general") -> dict:
        """Create a new Q&A pair in JSONL"""
        
        try:
            # Ensure all required fields
            qa_pair = {
                "question": question,
                "answer": answer,
                "language": self._normalize_language(language),
                "category": category,
                "timestamp": datetime.now().isoformat()
            }
            
            # Add to in-memory list
            self.qa_pairs.append(qa_pair)
            
            # Save to file
            save_success = self.save_to_jsonl()
            
            if not save_success:
                # Remove from memory if save failed
                self.qa_pairs.pop()
                return {
                    "success": False,
                    "error": f"Failed to save Q&A pair to {self.data_path}. Check file permissions."
                }
            
            print(f"✅ Created Q&A pair: '{question}' ({language}/{category})")
            
            return {
                "success": True,
                "message": "Q&A pair created successfully",
                "data": qa_pair
            }
        except Exception as e:
            import traceback
            print(f"❌ Error creating Q&A pair: {e}")
            print(traceback.format_exc())
            return {
                "success": False,
                "error": str(e)
            }

    async def create_qa_pair_structured(
        self,
        question: str,
        answer: str,
        category: str = "general",
        auto_translate: bool = True,
    ) -> dict:
        """
        Create a new Q&A pair with structured multi-language storage.
        question_ar, answer_ar, question_en, answer_en, question_fr, answer_fr.
        If auto_translate=True, translates from input language to the other two.
        """
        try:
            trans = {}
            if auto_translate:
                try:
                    from services.faq_translation_service import translate_faq_pair
                    trans = translate_faq_pair(question, answer)
                except Exception as tr_e:
                    print(f"⚠️ FAQ translation failed, using source for all: {tr_e}")
            if not trans or not trans.get("question_ar"):
                trans = {
                    "question_ar": question,
                    "answer_ar": answer,
                    "question_en": question,
                    "answer_en": answer,
                    "question_fr": question,
                    "answer_fr": answer,
                }
            qa_pair = {
                "question_ar": trans.get("question_ar", question),
                "answer_ar": trans.get("answer_ar", answer),
                "question_en": trans.get("question_en", question),
                "answer_en": trans.get("answer_en", answer),
                "question_fr": trans.get("question_fr", question),
                "answer_fr": trans.get("answer_fr", answer),
                "category": category,
                "timestamp": datetime.now().isoformat(),
            }
            # Add extra languages (e.g. question_de, answer_de from TRAINING_EXTRA_LANGUAGES)
            for k, v in trans.items():
                if k.startswith("question_") or k.startswith("answer_"):
                    lang = k.split("_", 1)[1]
                    if lang not in ("ar", "en", "fr") and v:
                        qa_pair[k] = v
            self.qa_pairs.append(qa_pair)
            if not self.save_to_jsonl():
                self.qa_pairs.pop()
                return {"success": False, "error": "Failed to save"}
            print(f"✅ Created structured Q&A pair (AR/EN/FR): '{question[:50]}...'")
            return {"success": True, "message": "Q&A pair created", "data": qa_pair}
        except Exception as e:
            import traceback
            print(f"❌ Error creating structured Q&A pair: {e}")
            traceback.print_exc()
            return {"success": False, "error": str(e)}
    
    async def update_qa_pair(self, qa_identifier: any, updates: dict) -> dict:
        """Update an existing Q&A pair
        
        Args:
            qa_identifier: Can be:
                - int: array index (for backward compatibility)
                - dict: {question, language} to find and update matching entry
            updates: Fields to update {question, answer, language, category}
        """
        try:
            qa_index = None
            
            # Handle dict identifier (find by question + language)
            if isinstance(qa_identifier, dict):
                search_question = qa_identifier.get("question")
                search_language = qa_identifier.get("language")
                
                if not search_question or not search_language:
                    return {
                        "success": False,
                        "error": "Must provide question and language for search"
                    }
                
                # Find matching entry
                for idx, qa in enumerate(self.qa_pairs):
                    if (qa.get("question") == search_question and 
                        qa.get("language") == search_language):
                        qa_index = idx
                        break
                
                if qa_index is None:
                    return {
                        "success": False,
                        "error": f"Q&A pair not found: '{search_question}' ({search_language})"
                    }
            else:
                # Handle int identifier (index)
                qa_index = int(qa_identifier)
                if qa_index < 0 or qa_index >= len(self.qa_pairs):
                    return {
                        "success": False,
                        "error": "Invalid Q&A index"
                    }
            
            # Update fields
            self.qa_pairs[qa_index].update(updates)
            self.qa_pairs[qa_index]["timestamp"] = datetime.now().isoformat()
            
            # Save to file
            save_success = self.save_to_jsonl()
            
            if not save_success:
                return {
                    "success": False,
                    "error": f"Failed to save Q&A pair to {self.data_path}"
                }
            
            print(f"✅ Updated Q&A pair at index {qa_index}: '{self.qa_pairs[qa_index].get('question')}'")
            
            return {
                "success": True,
                "message": "Q&A pair updated successfully",
                "data": self.qa_pairs[qa_index]
            }
        except Exception as e:
            import traceback
            print(f"❌ Error updating Q&A pair: {e}")
            print(traceback.format_exc())
            return {
                "success": False,
                "error": str(e)
            }
    
    async def delete_qa_pair(self, qa_identifier: any) -> dict:
        """Delete a Q&A pair
        
        Args:
            qa_identifier: Can be:
                - int: array index (for backward compatibility)
                - dict: {question, language} to find and delete matching entry
        """
        try:
            qa_index = None
            
            # Handle dict identifier (find by question + language)
            if isinstance(qa_identifier, dict):
                search_question = qa_identifier.get("question")
                search_language = qa_identifier.get("language")
                
                if not search_question or not search_language:
                    return {
                        "success": False,
                        "error": "Must provide question and language for search"
                    }
                
                # Find matching entry
                for idx, qa in enumerate(self.qa_pairs):
                    if (qa.get("question") == search_question and 
                        qa.get("language") == search_language):
                        qa_index = idx
                        break
                
                if qa_index is None:
                    return {
                        "success": False,
                        "error": f"Q&A pair not found: '{search_question}' ({search_language})"
                    }
            else:
                # Handle int identifier (index)
                qa_index = int(qa_identifier)
                if qa_index < 0 or qa_index >= len(self.qa_pairs):
                    return {
                        "success": False,
                        "error": "Invalid Q&A index"
                    }
            
            deleted = self.qa_pairs.pop(qa_index)
            
            # Save to file
            save_success = self.save_to_jsonl()
            
            if not save_success:
                # Restore the deleted item if save failed
                self.qa_pairs.insert(qa_index, deleted)
                return {
                    "success": False,
                    "error": f"Failed to save Q&A pair to {self.data_path}. Check file permissions."
                }
            
            print(f"✅ Deleted Q&A pair: '{deleted.get('question')}'")
            
            return {
                "success": True,
                "message": "Q&A pair deleted successfully",
                "data": deleted
            }
        except Exception as e:
            import traceback
            print(f"❌ Error deleting Q&A pair: {e}")
            print(traceback.format_exc())
            return {
                "success": False,
                "error": str(e)
            }
    
    # Keywords for intent alignment (hybrid matching)
    PRICE_KEYWORDS = [
        "price", "cost", "how much", "pricing", "سعر", "اسعار", "كم", "قديش", "أديش", "تكلفة",
        "prix", "coût", "combien", "tarif", "adesh", "adde", "kam", "sa3er",
    ]
    PRICING_IN_ANSWER_KEYWORDS = [
        "$", "ليرة", "ل.ل", "lira", "usd", "price", "سعر", "اسعار", "كم", "قديش",
        "prix", "combien", "cost", "ل.ل", "ل.ل.", "دولار",
    ]

    def normalize_text(self, text: str) -> str:
        """Normalize text for better matching"""
        text = re.sub(r'\s+', ' ', text.strip())
        text = re.sub(r'[؟?!.،,;:]', '', text)
        text = text.replace('أ', 'ا').replace('إ', 'ا').replace('آ', 'ا')
        text = text.replace('ة', 'ه').replace('ى', 'ي')
        return text.lower()

    def _keyword_intent_alignment(self, user_question: str, qa: dict) -> bool:
        """
        Hybrid validation: if user asks about price, FAQ must contain pricing-related content.
        Returns True if match is valid, False if we should reject (e.g. user asks price but FAQ has no price info).
        """
        q_norm = self.normalize_text(user_question)
        user_asks_price = any(kw in q_norm for kw in self.PRICE_KEYWORDS)
        if not user_asks_price:
            return True

        answer_text = (
            qa.get("answer", "")
            or qa.get("answer_ar", "")
            or qa.get("answer_en", "")
            or qa.get("answer_fr", "")
        )
        question_text = (
            qa.get("question", "")
            or qa.get("question_ar", "")
            or qa.get("question_en", "")
            or qa.get("question_fr", "")
        )
        combined = self.normalize_text(answer_text + " " + question_text)
        has_pricing = any(kw in combined for kw in self.PRICING_IN_ANSWER_KEYWORDS)
        return has_pricing
    
    def calculate_similarity(self, text1: str, text2: str) -> float:
        """Calculate similarity between two texts"""
        text1_norm = self.normalize_text(text1)
        text2_norm = self.normalize_text(text2)
        return SequenceMatcher(None, text1_norm, text2_norm).ratio()
    
    async def search_qa_pairs(self, query: str, language: str = None) -> dict:
        """Search Q&A pairs by question/answer content"""
        try:
            results = []
            
            for qa in self.qa_pairs:
                # Filter by language if specified
                if language:
                    requested_language = self._normalize_language(language, default="")
                    qa_language = self._normalize_language(qa.get("language"), default="")
                    if qa_language != requested_language:
                        continue

                if not qa.get("question") and not qa.get("answer"):
                    continue
                
                # Calculate similarity for question
                question_sim = self.calculate_similarity(query, qa.get("question", ""))
                answer_sim = self.calculate_similarity(query, qa.get("answer", ""))
                
                # Use max similarity
                max_sim = max(question_sim, answer_sim)
                
                if max_sim >= 0.3:  # Lower threshold for search results
                    results.append({
                        **qa,
                        "match_score": max_sim
                    })
            
            # Sort by score
            results.sort(key=lambda x: x["match_score"], reverse=True)
            
            print(f"🔍 Search found {len(results)} matches for: '{query}'")
            
            return {
                "success": True,
                "data": results,
                "count": len(results)
            }
        except Exception as e:
            print(f"❌ Error searching Q&A pairs: {e}")
            return {
                "success": False,
                "error": str(e),
                "data": []
            }
    
    async def find_match(self, question: str, language: str = "ar") -> Optional[dict]:
        """Find best matching Q&A pair"""
        best_match = None
        best_score = 0
        requested_language = self._normalize_language(language)
        
        # DEBUG: Check if Q&A pairs are loaded
        if not self.qa_pairs:
            print(f"❌ DEBUG: NO Q&A PAIRS LOADED! self.qa_pairs is empty or None")
            print(f"ℹ️ No Q&A match found (best score: 0.00%, threshold: {self.match_threshold:.2%})")
            return None
        
        for qa in self.qa_pairs:
            qa_language = self._normalize_language(qa.get("language"))
            # Never mix language datasets during matching.
            if qa_language != requested_language:
                continue

            similarity = self.calculate_similarity(question, qa.get("question", ""))
            
            if similarity > best_score:
                best_score = similarity
                best_match = qa
        
        if best_score >= self.match_threshold:
            print(f"✅ Q&A Match Found! Score: {best_score:.2%}")
            return {
                "qa_pair": best_match,
                "match_score": best_score,
                "matched_language": language
            }
        
        print(f"ℹ️ No Q&A match found (best score: {best_score:.2%}, threshold: {self.match_threshold:.2%})")
        return None

    async def get_relevant_qa_pairs(self, question: str, language: str = None, limit: int = 3) -> List[Dict]:
        """
        Get most relevant Q&A pairs for GPT context injection.
        Matches against all question variants; returns answer in user's language.

        Args:
            question: The user's question
            language: Optional language filter
            limit: Maximum number of Q&A pairs to return (default: 3)

        Returns:
            List of dicts with question, answer, and similarity score
        """
        results = []

        for qa in self.qa_pairs:
            best_sim = 0.0
            variants = self._get_question_variants(qa)
            for q_text, _ in variants:
                if language:
                    requested = self._normalize_language(language, default="")
                    qa_lang = self._normalize_language(qa.get("language", ""), default="")
                    if requested and qa_lang and qa_lang != requested and not (qa.get("question_ar") or qa.get("question_en") or qa.get("question_fr")):
                        continue
                sim = self.calculate_similarity(question, q_text)
                best_sim = max(best_sim, sim)

            if best_sim >= 0.3:
                answer = self._get_answer_for_language(qa, language or "ar")
                q_display = qa.get("question") or qa.get("question_ar") or qa.get("question_en") or qa.get("question_fr")
                results.append({
                    "question": q_display,
                    "answer": answer,
                    "similarity": best_sim,
                    "language": language or "ar",
                })

        results.sort(key=lambda x: x["similarity"], reverse=True)
        print(f"📚 Found {len(results)} relevant Q&A pairs for context (returning top {limit})")
        return results[:limit]

    def _get_question_variants(self, qa: dict) -> List[Tuple[str, str]]:
        """Get all question variants for matching (supports both legacy and structured schema)."""
        variants = []
        if qa.get("question_ar"):
            variants.append((qa["question_ar"], "ar"))
        if qa.get("question_en"):
            variants.append((qa["question_en"], "en"))
        if qa.get("question_fr"):
            variants.append((qa["question_fr"], "fr"))
        if not variants and qa.get("question"):
            lang = qa.get("language", "ar")
            variants.append((qa["question"], self._normalize_language(lang)))
        return variants

    def _get_answer_for_language(self, qa: dict, language: str) -> str:
        """Get answer in user's language (supports both legacy and structured schema)."""
        requested = self._normalize_language(language)
        if requested == "franco":
            requested = "ar"
        if requested == "ar" and qa.get("answer_ar"):
            return qa["answer_ar"]
        if requested == "en" and qa.get("answer_en"):
            return qa["answer_en"]
        if requested == "fr" and qa.get("answer_fr"):
            return qa["answer_fr"]
        if qa.get("answer"):
            return qa["answer"]
        return qa.get("answer_ar") or qa.get("answer_en") or qa.get("answer_fr") or ""

    async def find_match_with_tier(self, question: str, language: str = "ar") -> Optional[dict]:
        """
        Find match with simplified matching logic.
        Matches against ALL language variants (question_ar, question_en, question_fr, or legacy question).
        Returns answer in user's language.

        Matching:
        - 70%+ : Return Q&A directly (direct tier) - NO AI call
        - <70% : Returns None - GPT handles with top 3 relevant Q&A pairs in context

        Args:
            question: The user's question
            language: Language preference (default: "ar")

        Returns:
            Dict with qa_pair, match_score, tier, matched_language; answer in user's lang
        """
        best_match = None
        best_score = 0

        if not self.qa_pairs:
            print(f"❌ DEBUG: NO Q&A PAIRS LOADED!")
            return None

        for qa in self.qa_pairs:
            variants = self._get_question_variants(qa)
            for q_text, _ in variants:
                similarity = self.calculate_similarity(question, q_text)
                if similarity > best_score:
                    if not self._keyword_intent_alignment(question, qa):
                        continue
                    best_score = similarity
                    best_match = qa

        # 70%+ threshold for direct Q&A response - bypass AI (configurable)
        threshold = getattr(self, "match_threshold", 0.7)
        if best_match and best_score >= threshold:
            answer = self._get_answer_for_language(best_match, language)
            print(f"✅ Q&A Match Found! Score: {best_score:.2%}, Tier: direct (FAQ bypass)")
            return {
                "qa_pair": {**best_match, "answer": answer},
                "match_score": best_score,
                "tier": "direct",
                "matched_language": language,
            }

        print(f"ℹ️ No Q&A match found (best score: {best_score:.2%}, needs ≥{threshold:.0%})")
        return None

    async def get_statistics(self) -> dict:
        """Get Q&A statistics"""
        try:
            total = len(self.qa_pairs)
            
            # Count by language
            language_counts = {}
            for qa in self.qa_pairs:
                lang = self._normalize_language(qa.get("language"), default="unknown")
                language_counts[lang] = language_counts.get(lang, 0) + 1
            
            # Count by category
            category_counts = {}
            for qa in self.qa_pairs:
                cat = qa.get("category", "unknown")
                category_counts[cat] = category_counts.get(cat, 0) + 1
            
            stats = {
                "total_qa_pairs": total,
                "language_distribution": language_counts,
                "category_distribution": category_counts,
                "last_updated": self.qa_pairs[-1].get("timestamp") if self.qa_pairs else None
            }
            
            print(f"📊 Statistics: {total} total pairs")
            
            return {
                "success": True,
                "data": stats
            }
        except Exception as e:
            print(f"❌ Error getting statistics: {e}")
            return {
                "success": False,
                "error": str(e),
                "data": {}
            }
    
    async def get_categories(self) -> dict:
        """Get all categories used"""
        try:
            categories = sorted(list(set(qa.get("category", "general") for qa in self.qa_pairs)))
            
            return {
                "success": True,
                "data": categories,
                "count": len(categories)
            }
        except Exception as e:
            print(f"❌ Error getting categories: {e}")
            return {
                "success": False,
                "error": str(e),
                "data": []
            }


# Singleton instance
local_qa_service = LocalQAService()


# Integration function for bot (replaces backend call)
async def get_qa_response(question: str, language: str = "ar") -> Optional[str]:
    """Get response from local Q&A database"""
    match_result = await local_qa_service.find_match(question, language)
    
    if match_result:
        qa_pair = match_result["qa_pair"]
        match_score = match_result["match_score"]
        
        print(f"✅ Q&A Match Found!")
        print(f"   Score: {match_score:.2%}")
        print(f"   Category: {qa_pair.get('category')}")
        
        answer = qa_pair.get("answer", "")
        return answer
    
    return None
