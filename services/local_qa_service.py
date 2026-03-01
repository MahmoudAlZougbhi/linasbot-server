#!/usr/bin/env python3
"""
Local Q&A Service - Replace Backend API with JSONL File Storage
Uses conversation_log.jsonl structure with added 'category' field
"""

import json
import os
from typing import List, Dict, Optional
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
        self.match_threshold = 0.9  # 90% similarity threshold
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
            print(f"❌ Error creating Q&A pair: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
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
    
    def normalize_text(self, text: str) -> str:
        """Normalize text for better matching"""
        text = re.sub(r'\s+', ' ', text.strip())
        text = re.sub(r'[؟?!.،,;:]', '', text)
        text = text.replace('أ', 'ا').replace('إ', 'ا').replace('آ', 'ا')
        text = text.replace('ة', 'ه').replace('ى', 'ي')
        return text.lower()
    
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
        Returns top matching Q&A pairs regardless of threshold (for context enrichment).

        Args:
            question: The user's question
            language: Optional language filter
            limit: Maximum number of Q&A pairs to return (default: 3)

        Returns:
            List of dicts with question, answer, and similarity score
        """
        results = []

        for qa in self.qa_pairs:
            # Filter by language if specified
            if language:
                requested_language = self._normalize_language(language, default="")
                qa_language = self._normalize_language(qa.get("language"), default="")
                if qa_language != requested_language:
                    continue

            similarity = self.calculate_similarity(question, qa.get("question", ""))

            # Include anything moderately relevant (30%+ similarity)
            if similarity >= 0.3:
                results.append({
                    "question": qa.get("question"),
                    "answer": qa.get("answer"),
                    "similarity": similarity,
                    "language": self._normalize_language(qa.get("language"))
                })

        # Sort by similarity descending
        results.sort(key=lambda x: x["similarity"], reverse=True)

        print(f"📚 Found {len(results)} relevant Q&A pairs for context (returning top {limit})")
        return results[:limit]

    async def find_match_with_tier(self, question: str, language: str = "ar") -> Optional[dict]:
        """
        Find match with simplified matching logic.

        Matching:
        - 90%+ : Return Q&A directly (direct tier)
        - <90% : Returns None - GPT handles with top 3 relevant Q&A pairs in context

        Args:
            question: The user's question
            language: Language preference (default: "ar")

        Returns:
            Dict with qa_pair, match_score, and tier, or None if below 90%
        """
        best_match = None
        best_score = 0
        requested_language = self._normalize_language(language)

        if not self.qa_pairs:
            print(f"❌ DEBUG: NO Q&A PAIRS LOADED!")
            return None

        for qa in self.qa_pairs:
            qa_language = self._normalize_language(qa.get("language"))
            if qa_language != requested_language:
                continue

            similarity = self.calculate_similarity(question, qa.get("question", ""))

            if similarity > best_score:
                best_score = similarity
                best_match = qa

        # 90%+ threshold for direct Q&A response
        if best_score >= 0.90:
            print(f"✅ Q&A Match Found! Score: {best_score:.2%}, Tier: direct")
            return {
                "qa_pair": best_match,
                "match_score": best_score,
                "tier": "direct",
                "matched_language": self._normalize_language(best_match.get("language"), default=requested_language)
            }

        print(f"ℹ️ No Q&A match found (best score: {best_score:.2%}, needs ≥90%)")
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
