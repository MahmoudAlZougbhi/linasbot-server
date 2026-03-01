#!/usr/bin/env python3
"""
Q&A Database Service - Uses Backend Database API
Replaces the deprecated JSON file approach with real database integration
"""

import os
import httpx
from typing import List, Dict, Optional
from dotenv import load_dotenv
from difflib import SequenceMatcher
import re
import api_config
from services.language_detection_service import language_detection_service

# Load environment variables (.env then .env.local via core; load_dotenv for standalone scripts)
load_dotenv()


class QADatabaseService:
    """
    Service to manage Q&A pairs using the backend database API
    Replaces qa_manager_service.py which used JSON files
    """
    
    def __init__(self):
        self.base_url = api_config.LINASLASER_API_BASE_URL
        self.token = api_config.LINASLASER_API_TOKEN
        self.match_threshold = 0.7  # 70% similarity threshold
        
        if not self.base_url or not self.token:
            raise ValueError("Missing API credentials: LINASLASER_API_BASE_URL or LINASLASER_API_TOKEN")
        
        print(f"🤖 QADatabaseService initialized with API: {self.base_url}")

    @staticmethod
    def _normalize_language(language: Optional[str], default: str = "ar") -> str:
        return language_detection_service.normalize_training_language(language, default=default)

    def _extract_question_for_language(self, qa: dict, language: str) -> str:
        """
        Support both backend response formats:
        1) Flat: {question, answer, language}
        2) Multilingual row: {question_ar, question_en, ...}
        """
        requested_language = self._normalize_language(language)
        question_key = f"question_{requested_language}"
        if qa.get(question_key):
            return qa.get(question_key, "")

        qa_language = self._normalize_language(qa.get("language"), default="")
        if qa_language:
            if qa_language != requested_language:
                return ""
            return qa.get("question", "")

        return qa.get("question", "")

    def _extract_answer_for_language(self, qa: dict, language: str) -> str:
        requested_language = self._normalize_language(language)
        answer_key = f"answer_{requested_language}"
        if qa.get(answer_key):
            return qa.get(answer_key, "")

        qa_language = self._normalize_language(qa.get("language"), default="")
        if qa_language:
            if qa_language != requested_language:
                return ""
            return qa.get("answer", "")

        return qa.get("answer", "")
    
    async def _make_api_request(self, method: str, endpoint: str, data: dict = None, params: dict = None) -> dict:
        """Make authenticated API request to backend"""
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json"
        }
        
        url = f"{self.base_url}{endpoint}"
        
        print(f"🌐 API Request: {method} {url}")
        print(f"🔑 Token: {self.token[:20]}...")
        if data:
            print(f"📦 Data: {data}")
        
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=False) as client:
            try:
                if method == "GET":
                    response = await client.get(url, headers=headers, params=params)
                elif method == "POST":
                    response = await client.post(url, headers=headers, json=data)
                elif method == "PUT":
                    response = await client.put(url, headers=headers, json=data)
                elif method == "DELETE":
                    response = await client.delete(url, headers=headers)
                else:
                    raise ValueError(f"Unsupported HTTP method: {method}")
                
                print(f"📡 Response Status: {response.status_code}")
                print(f"📡 Response Headers: {dict(response.headers)}")
                
                response.raise_for_status()
                return response.json()
                
            except httpx.HTTPStatusError as e:
                print(f"❌ API Error ({e.response.status_code}): {e.response.text[:500]}")
                return {"success": False, "error": f"HTTP {e.response.status_code}", "message": e.response.text}
            except Exception as e:
                print(f"❌ Request Error: {e}")
                return {"success": False, "error": str(e)}
    
    async def create_qa_pair(self, 
                            question_ar: str, answer_ar: str,
                            question_en: str = "", answer_en: str = "",
                            question_fr: str = "", answer_fr: str = "",
                            question_franco: str = "", answer_franco: str = "",
                            category: str = "general",
                            tags: List[str] = None) -> dict:
        """
        Create a new Q&A pair in the database
        Backend expects: {question_ar, answer_ar, question_en, answer_en, ...}
        """
        # Auto-generate missing EN/FR/Franco when Arabic source is provided.
        if question_ar and answer_ar:
            missing_targets = []
            if not question_en or not answer_en:
                missing_targets.append("en")
            if not question_fr or not answer_fr:
                missing_targets.append("fr")
            if not question_franco or not answer_franco:
                missing_targets.append("franco")

            if missing_targets:
                translation_result = await language_detection_service.translate_arabic_training_pair(
                    question_ar=question_ar,
                    answer_ar=answer_ar,
                    target_languages=missing_targets,
                )
                translations = translation_result.get("translations", {})

                if "en" in translations:
                    question_en = question_en or translations["en"].get("question", "")
                    answer_en = answer_en or translations["en"].get("answer", "")
                if "fr" in translations:
                    question_fr = question_fr or translations["fr"].get("question", "")
                    answer_fr = answer_fr or translations["fr"].get("answer", "")
                if "franco" in translations:
                    question_franco = question_franco or translations["franco"].get("question", "")
                    answer_franco = answer_franco or translations["franco"].get("answer", "")

                unresolved = []
                if not question_en or not answer_en:
                    unresolved.append("en")
                if not question_fr or not answer_fr:
                    unresolved.append("fr")
                if not question_franco or not answer_franco:
                    unresolved.append("franco")

                if unresolved:
                    return {
                        "success": False,
                        "error": "Auto translation failed for required languages",
                        "missing_languages": unresolved,
                    }

        data = {
            "question_ar": question_ar or "",
            "answer_ar": answer_ar or "",
            "question_en": question_en or "",
            "answer_en": answer_en or "",
            "question_fr": question_fr or "",
            "answer_fr": answer_fr or "",
            "question_franco": question_franco or "",
            "answer_franco": answer_franco or "",
            "category": category,
            "tags": tags or []
        }
        
        print(f"📝 Creating Q&A pair in database: {question_ar or question_en or question_fr or question_franco}")
        print(f"   Data: {data}")
        response = await self._make_api_request("POST", "/qa/create", data=data)
        
        if response.get("success"):
            print(f"✅ Q&A pair created with ID: {response.get('data', {}).get('qa_id')}")
        else:
            print(f"❌ Failed to create Q&A pair: {response.get('message')}")
        
        return response
    
    async def get_qa_pairs(self, category: str = None, language: str = None, active_only: bool = True) -> dict:
        """
        Get all Q&A pairs from database with optional filtering
        
        Args:
            category: Filter by category (optional)
            language: Filter by language (optional)
            active_only: Only return active Q&A pairs (default: True)
        
        Returns:
            dict: Response with list of Q&A pairs
        """
        params = {}
        if category:
            params["category"] = category
        if language:
            params["language"] = language
        if active_only is not None:
            params["active_only"] = str(active_only).lower()
        
        print(f"📋 Fetching Q&A pairs from database (filters: {params})")
        response = await self._make_api_request("GET", "/qa/list", params=params)

        if response.get("success") and language:
            requested_language = self._normalize_language(language, default="")
            data = response.get("data", [])
            if isinstance(data, list) and data and any("language" in qa for qa in data):
                filtered = [
                    qa for qa in data
                    if self._normalize_language(qa.get("language"), default="") == requested_language
                ]
                response = {**response, "data": filtered, "count": len(filtered)}
        
        if response.get("success"):
            count = len(response.get("data", []))
            print(f"✅ Retrieved {count} Q&A pairs from database")
        else:
            print(f"❌ Failed to fetch Q&A pairs: {response.get('message')}")
        
        return response
    
    async def update_qa_pair(self, qa_id: int, updates: dict) -> dict:
        """
        Update an existing Q&A pair in database
        
        Args:
            qa_id: ID of the Q&A pair to update
            updates: Dictionary of fields to update
        
        Returns:
            dict: Response from API
        """
        print(f"✏️ Updating Q&A pair {qa_id} in database")
        print(f"📦 Update data: {updates}")
        
        # Use POST method with /qa/update endpoint (as it was working before)
        response = await self._make_api_request("POST", "/qa/update", data={"qa_id": qa_id, **updates})
        
        if response.get("success"):
            print(f"✅ Q&A pair {qa_id} updated successfully")
        else:
            print(f"❌ Failed to update Q&A pair {qa_id}: {response.get('message')}")
        
        return response
    
    async def delete_qa_pair(self, qa_id: int) -> dict:
        """
        Delete a Q&A pair from database (soft delete)
        
        Args:
            qa_id: ID of the Q&A pair to delete
        
        Returns:
            dict: Response from API
        """
        print(f"🗑️ Deleting Q&A pair {qa_id} from database")
        response = await self._make_api_request("POST", "/qa/delete", data={"qa_id": qa_id})
        
        if response.get("success"):
            print(f"✅ Q&A pair {qa_id} deleted successfully")
        else:
            print(f"❌ Failed to delete Q&A pair {qa_id}: {response.get('message')}")
        
        return response
    
    async def search_qa_pairs(self, query: str, language: str = "ar") -> dict:
        """
        Search Q&A pairs in database
        
        Args:
            query: Search query
            language: Language to search in (default: "ar")
        
        Returns:
            dict: Response with matching Q&A pairs
        """
        params = {
            "query": query,
            "language": language
        }
        
        print(f"🔍 Searching Q&A pairs: '{query}' (language: {language})")
        response = await self._make_api_request("GET", "/qa/search", params=params)

        if response.get("success") and language:
            requested_language = self._normalize_language(language, default="")
            data = response.get("data", [])
            if isinstance(data, list) and data and any("language" in qa for qa in data):
                filtered = [
                    qa for qa in data
                    if self._normalize_language(qa.get("language"), default="") == requested_language
                ]
                response = {**response, "data": filtered, "count": len(filtered)}
        
        if response.get("success"):
            count = len(response.get("data", []))
            print(f"✅ Found {count} matching Q&A pairs")
        else:
            print(f"❌ Search failed: {response.get('message')}")
        
        return response
    
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
    
    async def find_match(self, question: str, language: str = "ar") -> Optional[dict]:
        """
        Find matching Q&A pair from database with similarity threshold
        
        Args:
            question: User's question
            language: Language of the question (default: "ar")
        
        Returns:
            dict: Matched Q&A pair with score, or None if no match
        """
        print(f"🔍 Finding match for: '{question}' (language: {language})")
        requested_language = self._normalize_language(language)
        
        # Get active Q&A pairs only for the requested language view.
        response = await self.get_qa_pairs(language=requested_language, active_only=True)
        
        if not response.get("success"):
            print(f"❌ Failed to fetch Q&A pairs for matching")
            return None
        
        qa_pairs = response.get("data", [])
        
        if not qa_pairs:
            print(f"⚠️ No Q&A pairs found in database")
            return None
        
        best_match = None
        best_score = 0
        
        # Check each Q&A pair for similarity
        for qa in qa_pairs:
            qa_question = self._extract_question_for_language(qa, requested_language)

            # Skip if no question in requested language
            if not qa_question:
                continue

            # Calculate similarity
            similarity = self.calculate_similarity(question, qa_question)
            
            if similarity > best_score:
                best_score = similarity
                best_match = qa
        
        # Return match if above threshold
        if best_score >= self.match_threshold:
            print(f"✅ Q&A Match Found!")
            print(f"   Score: {best_score:.2%}")
            print(f"   Category: {best_match.get('category')}")
            print(f"   QA ID: {best_match.get('qa_id')}")
            
            # Track usage
            await self.track_usage(
                qa_id=best_match.get("qa_id"),
                customer_phone=None,  # Will be provided by caller if available
                matched=True,
                match_score=best_score
            )
            
            return {
                "qa_pair": best_match,
                "match_score": best_score,
                "matched_language": requested_language
            }
        
        print(f"ℹ️ No Q&A match found (best score: {best_score:.2%}, threshold: {self.match_threshold:.2%})")
        return None
    
    async def track_usage(self, qa_id: int, customer_phone: str = None, matched: bool = True, match_score: float = 0) -> dict:
        """
        Track Q&A usage in database
        
        Args:
            qa_id: ID of the Q&A pair
            customer_phone: Customer's phone number (optional)
            matched: Whether the Q&A was matched (default: True)
            match_score: Similarity score (default: 0)
        
        Returns:
            dict: Response from API
        """
        data = {
            "qa_id": qa_id,
            "matched": matched,
            "match_score": match_score
        }
        
        if customer_phone:
            data["customer_phone"] = customer_phone
        
        response = await self._make_api_request("POST", "/qa/track-usage", data=data)
        
        if response.get("success"):
            print(f"✅ Usage tracked for Q&A {qa_id}")
        else:
            print(f"⚠️ Failed to track usage for Q&A {qa_id}")
        
        return response
    
    async def get_statistics(self) -> dict:
        """
        Get Q&A statistics from database
        
        Returns:
            dict: Statistics including total pairs, usage, etc.
        """
        print(f"📊 Fetching Q&A statistics from database")
        response = await self._make_api_request("GET", "/qa/statistics")
        
        if response.get("success"):
            print(f"✅ Statistics retrieved successfully")
        else:
            print(f"❌ Failed to fetch statistics: {response.get('message')}")
        
        return response
    
    async def get_categories(self) -> dict:
        """
        Get list of Q&A categories from database
        
        Returns:
            dict: List of categories
        """
        print(f"📂 Fetching Q&A categories from database")
        response = await self._make_api_request("GET", "/qa/categories")
        
        if response.get("success"):
            categories = response.get("data", [])
            print(f"✅ Retrieved {len(categories)} categories")
        else:
            print(f"❌ Failed to fetch categories: {response.get('message')}")
        
        return response


# Singleton instance
qa_db_service = QADatabaseService()


# Integration function for bot (replaces get_qa_response from qa_manager_service)
async def get_qa_response(question: str, language: str = "ar") -> Optional[str]:
    """
    Get response from Q&A database if match found
    
    Args:
        question: User's question
        language: Language of the question (default: "ar")
    
    Returns:
        str: Answer if match >= 70%, None otherwise
    """
    match_result = await qa_db_service.find_match(question, language)
    
    if match_result:
        qa_pair = match_result["qa_pair"]
        match_score = match_result["match_score"]
        
        print(f"✅ Q&A Match Found!")
        print(f"   Score: {match_score:.2%}")
        print(f"   Category: {qa_pair.get('category')}")
        print(f"   Usage Count: {qa_pair.get('usage_count', 0)}")
        
        answer = qa_db_service._extract_answer_for_language(qa_pair, language)
        
        return answer
    
    return None


# Test function
async def test_qa_database_service():
    """Test the QADatabaseService"""
    print("🧪 TESTING QA DATABASE SERVICE")
    print("=" * 60)
    
    try:
        # Test 1: Get all Q&A pairs
        print("\n📋 Test 1: Get all Q&A pairs")
        response = await qa_db_service.get_qa_pairs()
        if response.get("success"):
            print(f"✅ Found {len(response.get('data', []))} Q&A pairs")
        
        # Test 2: Create a Q&A pair
        print("\n📝 Test 2: Create Q&A pair")
        create_response = await qa_db_service.create_qa_pair(
            question_ar="ما هي أسعار إزالة الشعر بالليزر؟",
            answer_ar="تختلف الأسعار حسب المنطقة المراد علاجها. يمكنك زيارتنا للحصول على استشارة مجانية.",
            question_en="What are the prices for laser hair removal?",
            answer_en="Prices vary depending on the area to be treated. You can visit us for a free consultation.",
            category="pricing",
            tags=["laser", "hair removal", "prices"]
        )
        
        if create_response.get("success"):
            qa_id = create_response.get("data", {}).get("qa_id")
            print(f"✅ Created Q&A pair with ID: {qa_id}")
            
            # Test 3: Find match
            print("\n🔍 Test 3: Find match")
            match = await qa_db_service.find_match("كم سعر إزالة الشعر؟", "ar")
            if match:
                print(f"✅ Match found with score: {match['match_score']:.2%}")
            else:
                print(f"❌ No match found")
            
            # Test 4: Get statistics
            print("\n📊 Test 4: Get statistics")
            stats_response = await qa_db_service.get_statistics()
            if stats_response.get("success"):
                print(f"✅ Statistics: {stats_response.get('data')}")
        
    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    import asyncio
    asyncio.run(test_qa_database_service())
