"""LocalQAService matching/search/stats helpers (LOC split)."""

from __future__ import annotations

import re
from difflib import SequenceMatcher
from typing import Any


class LocalQAServiceMatchMixin:
    """Text normalization, search, and tiered matching for LocalQAService."""

    def normalize_text(self, text: str) -> str:
        """Normalize text for better matching"""
        text = re.sub(r"\s+", " ", text.strip())
        text = re.sub(r"[؟?!.،,;:]", "", text)
        text = text.replace("أ", "ا").replace("إ", "ا").replace("آ", "ا")
        text = text.replace("ة", "ه").replace("ى", "ي")
        return text.lower()

    def calculate_similarity(self, text1: str, text2: str) -> float:
        """Calculate similarity between two texts"""
        text1_norm = self.normalize_text(text1)
        text2_norm = self.normalize_text(text2)
        return SequenceMatcher(None, text1_norm, text2_norm).ratio()

    async def search_qa_pairs(self, query: str, language: str | None = None) -> dict:
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
                    results.append({**qa, "match_score": max_sim})

            # Sort by score
            results.sort(key=lambda x: x["match_score"], reverse=True)

            print(f"🔍 Search found {len(results)} matches for: '{query}'")

            return {"success": True, "data": results, "count": len(results)}
        except Exception as e:
            print(f"❌ Error searching Q&A pairs: {e}")
            return {"success": False, "error": str(e), "data": []}

    async def find_match(self, question: str, language: str = "ar") -> dict | None:
        """Find best matching Q&A pair"""
        best_match = None
        best_score: float = 0.0
        requested_language = self._normalize_language(language)

        # DEBUG: Check if Q&A pairs are loaded
        if not self.qa_pairs:
            print("❌ DEBUG: NO Q&A PAIRS LOADED! self.qa_pairs is empty or None")
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
            return {"qa_pair": best_match, "match_score": best_score, "matched_language": language}

        print(f"ℹ️ No Q&A match found (best score: {best_score:.2%}, threshold: {self.match_threshold:.2%})")
        return None

    async def find_exact_match(self, question: str, language: str = "ar") -> dict | None:
        """
        Find an exact normalized question match.
        Tries requested language first, then falls back to other languages.
        """
        requested_language = self._normalize_language(language)
        normalized_question = self.normalize_text(question or "")

        if not normalized_question:
            return None

        if not self.qa_pairs:
            print("❌ DEBUG: NO Q&A PAIRS LOADED for exact matching!")
            return None

        same_language_match = None
        cross_language_match = None

        for qa in self.qa_pairs:
            stored_question = qa.get("question", "")
            if not stored_question:
                continue

            if self.normalize_text(stored_question) != normalized_question:
                continue

            matched_language = self._normalize_language(
                qa.get("language"),
                default=requested_language,
            )
            candidate = {
                "qa_pair": qa,
                "match_score": 1.0,
                "tier": "exact",
                "matched_language": matched_language,
            }

            if matched_language == requested_language:
                same_language_match = candidate
                break

            if cross_language_match is None:
                cross_language_match = candidate

        if same_language_match:
            print(f"✅ Exact Q&A match found in requested language ({requested_language}).")
            return same_language_match

        if cross_language_match:
            print(
                "✅ Exact Q&A match found via cross-language fallback "
                f"(requested={requested_language}, matched={cross_language_match.get('matched_language')})."
            )
            return cross_language_match

        return None

    async def get_relevant_qa_pairs(self, question: str, language: str | None = None, limit: int = 3) -> list[dict]:
        """
        Get most relevant Q&A pairs for GPT context injection.
        Returns top matching Q&A pairs regardless of threshold (for context enrichment).

        Args:
            question: The user's question
            language:  language filter
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
                results.append(
                    {
                        "question": qa.get("question"),
                        "answer": qa.get("answer"),
                        "similarity": similarity,
                        "language": self._normalize_language(qa.get("language")),
                    }
                )

        # Sort by similarity descending
        results.sort(key=lambda x: float(x.get("similarity") or 0), reverse=True)

        print(f"📚 Found {len(results)} relevant Q&A pairs for context (returning top {limit})")
        return results[:limit]

    async def find_match_with_tier(self, question: str, language: str = "ar") -> dict | None:
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
        requested_language = self._normalize_language(language)

        if not self.qa_pairs:
            print("❌ DEBUG: NO Q&A PAIRS LOADED!")
            return None

        # Exact normalized match first (requested language first, then cross-language fallback).
        exact_match = await self.find_exact_match(question, requested_language)
        if exact_match:
            return exact_match

        best_same_language_match = None
        best_same_language_score: float = 0.0
        best_cross_language_match = None
        best_cross_language_score: float = 0.0

        for qa in self.qa_pairs:
            qa_language = self._normalize_language(qa.get("language"))
            qa_question = qa.get("question", "")
            if not qa_question:
                continue

            similarity = self.calculate_similarity(question, qa_question)

            if qa_language == requested_language:
                if similarity > best_same_language_score:
                    best_same_language_score = similarity
                    best_same_language_match = qa
            else:
                if similarity > best_cross_language_score:
                    best_cross_language_score = similarity
                    best_cross_language_match = qa

        if best_same_language_score >= 0.90:
            print(
                "✅ Q&A Match Found! "
                f"Score: {best_same_language_score:.2%}, Tier: direct, Language: {requested_language}"
            )
            return {
                "qa_pair": best_same_language_match,
                "match_score": best_same_language_score,
                "tier": "direct",
                "matched_language": requested_language,
            }

        if best_cross_language_score >= 0.90 and best_cross_language_match is not None:
            matched_language = self._normalize_language(
                best_cross_language_match.get("language"),
                default=requested_language,
            )
            print(
                "✅ Q&A Match Found via cross-language fallback! "
                f"Score: {best_cross_language_score:.2%}, Tier: direct, "
                f"Requested: {requested_language}, Matched: {matched_language}"
            )
            return {
                "qa_pair": best_cross_language_match,
                "match_score": best_cross_language_score,
                "tier": "direct",
                "matched_language": matched_language,
            }

        best_score = max(best_same_language_score, best_cross_language_score)
        print(f"ℹ️ No Q&A match found (best score: {best_score:.2%}, needs ≥90%)")
        return None

    async def get_statistics(self) -> dict:
        """Get Q&A statistics"""
        try:
            total = len(self.qa_pairs)

            # Count by language
            language_counts: dict[str, Any] = {}
            for qa in self.qa_pairs:
                lang = self._normalize_language(qa.get("language"), default="unknown")
                language_counts[lang] = language_counts.get(lang, 0) + 1

            # Count by category
            category_counts: dict[str, Any] = {}
            for qa in self.qa_pairs:
                cat = qa.get("category", "unknown")
                category_counts[cat] = category_counts.get(cat, 0) + 1

            stats: dict[str, Any] = {
                "total_qa_pairs": total,
                "language_distribution": language_counts,
                "category_distribution": category_counts,
                "last_updated": self.qa_pairs[-1].get("timestamp") if self.qa_pairs else None,
            }

            print(f"📊 Statistics: {total} total pairs")

            return {"success": True, "data": stats}
        except Exception as e:
            print(f"❌ Error getting statistics: {e}")
            return {"success": False, "error": str(e), "data": {}}

    async def get_categories(self) -> dict:
        """Get all categories used"""
        try:
            categories = sorted(list(set(qa.get("category", "general") for qa in self.qa_pairs)))

            return {"success": True, "data": categories, "count": len(categories)}
        except Exception as e:
            print(f"❌ Error getting categories: {e}")
            return {"success": False, "error": str(e), "data": []}
