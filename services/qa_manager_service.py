# -*- coding: utf-8 -*-
"""
Q&A Manager Service
Handles all Q&A pair operations with 90% match logic
"""

import json
import os
from typing import List, Dict, Optional, Tuple
from datetime import datetime
import hashlib
from difflib import SequenceMatcher
import re
from services.language_detection_service import language_detection_service
from storage.persistent_storage import QA_DATABASE_FILE, ensure_dirs


class QAManager:
    """Manages Q&A pairs with multi-language support and fuzzy matching"""
    
    def __init__(self, data_path: str = None):
        if data_path is None:
            ensure_dirs()
            data_path = str(QA_DATABASE_FILE)
        self.data_path = data_path
        self.qa_database = self.load_database()
        self.match_threshold = 0.7  # 70% similarity threshold (more practical)
        
    def load_database(self) -> Dict:
        """Load Q&A database from file"""
        if os.path.exists(self.data_path):
            with open(self.data_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {
            "qa_pairs": [],
            "categories": ["general", "pricing", "services", "appointments", "medical"],
            "last_updated": None
        }
    
    def save_database(self):
        """Save Q&A database to file"""
        self.qa_database["last_updated"] = datetime.now().isoformat()
        os.makedirs(os.path.dirname(self.data_path), exist_ok=True)
        with open(self.data_path, 'w', encoding='utf-8') as f:
            json.dump(self.qa_database, f, ensure_ascii=False, indent=2)

    @staticmethod
    def _normalize_language(language: Optional[str], default: str = "ar") -> str:
        return language_detection_service.normalize_training_language(language, default=default)
    
    def create_qa_pair(self, 
                       question_ar: str, answer_ar: str,
                       question_en: str = "", answer_en: str = "",
                       question_fr: str = "", answer_fr: str = "",
                       question_franco: str = "", answer_franco: str = "",
                       category: str = "general",
                       tags: List[str] = None) -> str:
        """
        Create a new Q&A pair in all 4 languages
        Returns: QA pair ID
        """
        qa_id = hashlib.md5(f"{question_ar}{datetime.now()}".encode()).hexdigest()[:12]
        
        qa_pair = {
            "id": qa_id,
            "ar": {"question": question_ar, "answer": answer_ar},
            "en": {"question": question_en, "answer": answer_en},
            "fr": {"question": question_fr, "answer": answer_fr},
            "franco": {"question": question_franco, "answer": answer_franco},
            "category": category,
            "tags": tags or [],
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
            "usage_count": 0,
            "match_count": 0,
            "is_active": True
        }
        
        self.qa_database["qa_pairs"].append(qa_pair)
        self.save_database()
        return qa_id
    
    def update_qa_pair(self, qa_id: str, updates: Dict) -> bool:
        """Update an existing Q&A pair"""
        for qa in self.qa_database["qa_pairs"]:
            if qa["id"] == qa_id:
                for key, value in updates.items():
                    if key in qa:
                        qa[key] = value
                qa["updated_at"] = datetime.now().isoformat()
                self.save_database()
                return True
        return False
    
    def delete_qa_pair(self, qa_id: str) -> bool:
        """Delete a Q&A pair (soft delete by marking inactive)"""
        for qa in self.qa_database["qa_pairs"]:
            if qa["id"] == qa_id:
                qa["is_active"] = False
                qa["deleted_at"] = datetime.now().isoformat()
                self.save_database()
                return True
        return False
    
    def normalize_text(self, text: str) -> str:
        """Normalize text for better matching"""
        # Remove extra spaces
        text = re.sub(r'\s+', ' ', text.strip())
        # Remove punctuation for matching
        text = re.sub(r'[؟?!.،,;:]', '', text)
        # Normalize Arabic characters
        text = text.replace('أ', 'ا').replace('إ', 'ا').replace('آ', 'ا')
        text = text.replace('ة', 'ه').replace('ى', 'ي')
        return text.lower()
    
    def calculate_similarity(self, text1: str, text2: str) -> float:
        """Calculate similarity between two texts"""
        text1_norm = self.normalize_text(text1)
        text2_norm = self.normalize_text(text2)
        return SequenceMatcher(None, text1_norm, text2_norm).ratio()
    
    def find_match(self, question: str, language: str = "ar") -> Optional[Dict]:
        """
        Find matching Q&A pair with 90% similarity threshold
        Returns: Matched Q&A pair or None
        """
        best_match = None
        best_score = 0
        requested_language = self._normalize_language(language)
        
        for qa in self.qa_database["qa_pairs"]:
            if not qa.get("is_active", True):
                continue
                
            # Check in specified language
            if requested_language in qa:
                qa_question = qa[requested_language]["question"]
                similarity = self.calculate_similarity(question, qa_question)
                
                if similarity > best_score:
                    best_score = similarity
                    best_match = qa
        
        # Return match if above threshold
        if best_score >= self.match_threshold:
            if best_match:
                best_match["match_count"] += 1
                best_match["usage_count"] += 1
                self.save_database()
            return {
                "qa_pair": best_match,
                "match_score": best_score,
                "matched_language": requested_language
            }
        
        return None
    
    def search_qa_pairs(self, 
                        query: str = None,
                        category: str = None,
                        language: str = None,
                        active_only: bool = True) -> List[Dict]:
        """Search Q&A pairs with filters"""
        results = []
        
        for qa in self.qa_database["qa_pairs"]:
            # Filter by active status
            if active_only and not qa.get("is_active", True):
                continue
            
            # Filter by category
            if category and qa.get("category") != category:
                continue

            # Keep language view isolated when requested.
            if language:
                requested_language = self._normalize_language(language, default="")
                localized = qa.get(requested_language, {})
                if not localized.get("question") and not localized.get("answer"):
                    continue
            
            # Filter by search query
            if query:
                query_lower = query.lower()
                match_found = False
                requested_language = self._normalize_language(language, default="")
                
                # Search in selected language only, or all languages if not specified.
                languages_to_search = [requested_language] if requested_language else ["ar", "en", "fr", "franco"]
                for lang in languages_to_search:
                    if lang in qa:
                        if query_lower in qa[lang]["question"].lower() or \
                           query_lower in qa[lang]["answer"].lower():
                            match_found = True
                            break
                
                # Search in tags
                if not match_found and qa.get("tags"):
                    for tag in qa["tags"]:
                        if query_lower in tag.lower():
                            match_found = True
                            break
                
                if not match_found:
                    continue
            
            results.append(qa)
        
        # Sort by usage count (most used first)
        results.sort(key=lambda x: x.get("usage_count", 0), reverse=True)
        return results
    
    def sync_languages(self, qa_id: str, base_language: str = "ar") -> bool:
        """
        Ensure all language versions are in sync
        Uses translation if needed
        """
        for qa in self.qa_database["qa_pairs"]:
            if qa["id"] == qa_id:
                base_q = qa[base_language]["question"]
                base_a = qa[base_language]["answer"]
                
                # Here you would call translation API if needed
                # For now, just mark as synced
                qa["synced_at"] = datetime.now().isoformat()
                qa["sync_base"] = base_language
                self.save_database()
                return True
        return False
    
    def get_statistics(self) -> Dict:
        """Get Q&A database statistics"""
        total = len(self.qa_database["qa_pairs"])
        active = sum(1 for qa in self.qa_database["qa_pairs"] if qa.get("is_active", True))
        
        category_counts = {}
        for qa in self.qa_database["qa_pairs"]:
            if qa.get("is_active", True):
                cat = qa.get("category", "general")
                category_counts[cat] = category_counts.get(cat, 0) + 1
        
        total_usage = sum(qa.get("usage_count", 0) for qa in self.qa_database["qa_pairs"])
        total_matches = sum(qa.get("match_count", 0) for qa in self.qa_database["qa_pairs"])
        
        return {
            "total_qa_pairs": total,
            "active_qa_pairs": active,
            "inactive_qa_pairs": total - active,
            "categories": category_counts,
            "total_usage": total_usage,
            "total_matches": total_matches,
            "match_rate": (total_matches / total_usage * 100) if total_usage > 0 else 0,
            "last_updated": self.qa_database.get("last_updated")
        }
    
    def export_qa_pairs(self, format: str = "json") -> str:
        """Export Q&A pairs in specified format"""
        if format == "json":
            return json.dumps(self.qa_database, ensure_ascii=False, indent=2)
        elif format == "csv":
            # CSV export logic here
            pass
        return ""
    
    def import_qa_pairs(self, data: str, format: str = "json") -> int:
        """Import Q&A pairs from specified format"""
        imported = 0
        if format == "json":
            import_data = json.loads(data)
            if "qa_pairs" in import_data:
                for qa in import_data["qa_pairs"]:
                    # Check for duplicates
                    exists = any(
                        existing["ar"]["question"] == qa["ar"]["question"] 
                        for existing in self.qa_database["qa_pairs"]
                    )
                    if not exists:
                        self.qa_database["qa_pairs"].append(qa)
                        imported += 1
                self.save_database()
        return imported


# Singleton instance
qa_manager = QAManager()


# Integration with main bot
async def get_qa_response(question: str, language: str = "ar") -> Optional[str]:
    """
    Get response from Q&A database if match found
    Returns: Answer if match >= 90%, None otherwise
    """
    match_result = qa_manager.find_match(question, language)
    
    if match_result:
        qa_pair = match_result["qa_pair"]
        match_score = match_result["match_score"]
        
        print(f"✅ Q&A Match Found!")
        print(f"   Score: {match_score:.2%}")
        print(f"   Category: {qa_pair.get('category')}")
        print(f"   Usage Count: {qa_pair.get('usage_count')}")
        
        # Return answer in requested language
        requested_language = qa_manager._normalize_language(language)
        if requested_language in qa_pair:
            return qa_pair[requested_language]["answer"]
        # Fallback to Arabic if language not found
        elif "ar" in qa_pair:
            return qa_pair["ar"]["answer"]
    
    return None


if __name__ == "__main__":
    # Test the Q&A manager
    
    # Create sample Q&A pairs
    qa_id = qa_manager.create_qa_pair(
        question_ar="ما هي أسعار إزالة الشعر بالليزر؟",
        answer_ar="تختلف الأسعار حسب المنطقة المراد علاجها. يمكنك زيارتنا للحصول على استشارة مجانية وتقدير دقيق للتكلفة.",
        question_en="What are the prices for laser hair removal?",
        answer_en="Prices vary depending on the area to be treated. You can visit us for a free consultation and accurate cost estimate.",
        question_fr="Quels sont les prix pour l'épilation au laser?",
        answer_fr="Les prix varient selon la zone à traiter. Vous pouvez nous rendre visite pour une consultation gratuite et une estimation précise des coûts.",
        question_franco="Shou el as3ar la izalit el sha3er bel laser?",
        answer_franco="El as3ar btekhtalef 7asab el manta2a. Fik tzourna la consultation majene w ta2dir da2i2 lal taklfe.",
        category="pricing",
        tags=["laser", "hair removal", "prices"]
    )
    
    print(f"Created Q&A pair: {qa_id}")
    
    # Test matching
    test_questions = [
        "كم سعر إزالة الشعر؟",  # Should match
        "أريد أن أعرف الأسعار",  # Should match
        "مرحبا",  # Should not match
    ]
    
    for q in test_questions:
        result = qa_manager.find_match(q, "ar")
        if result:
            print(f"Question: {q}")
            print(f"Match Score: {result['match_score']:.2%}")
            print(f"Answer: {result['qa_pair']['ar']['answer']}\n")
        else:
            print(f"Question: {q} - No match found\n")
    
    # Get statistics
    stats = qa_manager.get_statistics()
    print("Q&A Database Statistics:")
    print(json.dumps(stats, indent=2))