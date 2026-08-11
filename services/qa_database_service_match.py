"""QADatabaseService match/usage/stats helpers (LOC split)."""

from __future__ import annotations

import re
from difflib import SequenceMatcher
from typing import Any


class QADatabaseServiceMatchMixin:
    """Similarity matching, usage tracking, and statistics for QADatabaseService."""

    def normalize_text(self, text: str) -> str:
        """Normalize text for better matching"""
        # Remove extra spaces
        text = re.sub(r"\s+", " ", text.strip())
        # Remove punctuation for matching
        text = re.sub(r"[؟?!.،,;:]", "", text)
        # Normalize Arabic characters
        text = text.replace("أ", "ا").replace("إ", "ا").replace("آ", "ا")
        text = text.replace("ة", "ه").replace("ى", "ي")
        return text.lower()

    def calculate_similarity(self, text1: str, text2: str) -> float:
        """Calculate similarity between two texts"""
        text1_norm = self.normalize_text(text1)
        text2_norm = self.normalize_text(text2)
        return SequenceMatcher(None, text1_norm, text2_norm).ratio()

    @staticmethod
    def _usable_customer_phone(phone: str | None) -> bool:
        if phone is None:
            return False
        p = str(phone).replace("+", "").replace(" ", "").replace("-", "").strip()
        return len(p) >= 7

    async def find_match(self, question: str, language: str = "ar", customer_phone: str | None = None) -> dict | None:
        """
        Find matching Q&A pair from database with similarity threshold

        Args:
            question: User's question
            language: Language of the question (default: "ar")
            customer_phone: If set, passed to track_usage; otherwise usage tracking is skipped

        Returns:
            dict: Matched Q&A pair with score, or None if no match
        """
        print(f"🔍 Finding match for: '{question}' (language: {language})")
        requested_language = self._normalize_language(language)

        # Get active Q&A pairs only for the requested language view.
        response = await self.get_qa_pairs(language=requested_language, active_only=True)

        if not response.get("success"):
            print("❌ Failed to fetch Q&A pairs for matching")
            return None

        qa_pairs = response.get("data", [])

        if not qa_pairs:
            print("⚠️ No Q&A pairs found in database")
            return None

        best_match = None
        best_score: float = 0.0

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
        if best_score >= self.match_threshold and best_match is not None:
            print("✅ Q&A Match Found!")
            print(f"   Score: {best_score:.2%}")
            print(f"   Category: {best_match.get('category')}")
            print(f"   QA ID: {best_match.get('qa_id')}")

            # Track usage (POST /qa/track-usage only when phone is present)
            await self.track_usage(
                qa_id=best_match.get("qa_id"),
                customer_phone=customer_phone,
                matched=True,
                match_score=best_score,
            )

            return {"qa_pair": best_match, "match_score": best_score, "matched_language": requested_language}

        print(f"ℹ️ No Q&A match found (best score: {best_score:.2%}, threshold: {self.match_threshold:.2%})")
        return None

    async def track_usage(
        self, qa_id: int, customer_phone: str | None = None, matched: bool = True, match_score: float = 0
    ) -> dict:
        """
        Track Q&A usage in database (POST .../qa/track-usage).

        If customer_phone is missing or not a plausible phone string, no HTTP request
        is sent (avoids incomplete payloads when the backend requires phone).
        """
        if not self._usable_customer_phone(customer_phone):
            print(f"ℹ️ track_usage skipped for qa_id={qa_id}: customer_phone missing or too short")
            return {
                "success": True,
                "skipped": True,
                "message": "track_usage skipped: customer_phone required for this metric",
            }

        data: dict[str, Any] = {
            "qa_id": qa_id,
            "customer_phone": str(customer_phone).replace("+", "").replace(" ", "").replace("-", "").strip(),
            "matched": matched,
            "match_score": match_score,
        }

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
        print("📊 Fetching Q&A statistics from database")
        response = await self._make_api_request("GET", "/qa/statistics")

        if response.get("success"):
            print("✅ Statistics retrieved successfully")
        else:
            print(f"❌ Failed to fetch statistics: {response.get('message')}")

        return response

    async def get_categories(self) -> dict:
        """
        Get list of Q&A categories from database

        Returns:
            dict: List of categories
        """
        print("📂 Fetching Q&A categories from database")
        response = await self._make_api_request("GET", "/qa/categories")

        if response.get("success"):
            categories = response.get("data", [])
            print(f"✅ Retrieved {len(categories)} categories")
        else:
            print(f"❌ Failed to fetch categories: {response.get('message')}")

        return response
