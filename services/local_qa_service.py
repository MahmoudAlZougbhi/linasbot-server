#!/usr/bin/env python3
"""
Local Q&A Service - Replace Backend API with JSONL File Storage
Uses conversation_log.jsonl structure with added 'category' field
"""

from __future__ import annotations

import json
import os
import re
from datetime import datetime
from difflib import SequenceMatcher
from typing import Any, cast

from services.language_detection_service import language_detection_service
from storage.persistent_storage import QA_PAIRS_FILE, ensure_dirs


from services.local_qa_service_match import LocalQAServiceMatchMixin

class LocalQAService(LocalQAServiceMatchMixin):
    """Manages Q&A pairs using local JSONL file (no backend dependency)"""

    def __init__(self, data_path: str | None = None) -> None:
        # Use persistent storage (survives deploy/rebuild)
        if data_path is None:
            ensure_dirs()
            data_path = str(QA_PAIRS_FILE)

        self.data_path = data_path
        self.match_threshold = 0.9  # 90% similarity threshold
        self.qa_pairs = self.load_from_jsonl()
        print(f"✅ LocalQAService initialized with {len(self.qa_pairs)} Q&A pairs from {self.data_path}")

    def load_from_jsonl(self) -> list[dict]:
        """Load Q&A pairs from JSONL file"""
        qa_pairs: list[Any] = []

        if not os.path.exists(self.data_path):
            print(f"❌ Q&A file NOT FOUND at: {self.data_path}")
            return qa_pairs

        try:
            with open(self.data_path, encoding="utf-8") as f:
                for line_num, line in enumerate(f, 1):
                    if line.strip():
                        try:
                            qa_pair = json.loads(line)
                            # Stable 1-based line number as faq_id (matches local_qa_api update/delete)
                            qa_pair["id"] = line_num
                            qa_pairs.append(qa_pair)
                        except json.JSONDecodeError as e:
                            print(f"❌ Error parsing line {line_num}: {e}")
                            continue

            print(f"✅ Loaded {len(qa_pairs)} Q&A pairs from JSONL")
            return qa_pairs
        except Exception as e:
            print(f"❌ Error loading Q&A file: {e}")
            return qa_pairs

    def save_to_jsonl(self) -> Any:
        """Save Q&A pairs to JSONL file"""
        try:
            # Ensure directory exists
            data_dir = os.path.dirname(self.data_path)
            if data_dir:
                os.makedirs(data_dir, exist_ok=True)

            with open(self.data_path, "w", encoding="utf-8") as f:
                for qa_pair in self.qa_pairs:
                    # Remove 'id' before saving (will be regenerated on load)
                    qa_to_save = {k: v for k, v in qa_pair.items() if k != "id"}
                    f.write(json.dumps(qa_to_save, ensure_ascii=False) + "\n")

            print(f"✅ Saved {len(self.qa_pairs)} Q&A pairs to JSONL at: {self.data_path}")
            return True
        except PermissionError as e:
            print(f"❌ Permission denied writing to {self.data_path}: {e}")
            return False
        except Exception as e:
            print(f"❌ Error saving Q&A file: {e}")
            return False

    @staticmethod
    def _normalize_language(language: str | None, default: str = "ar") -> str:
        return language_detection_service.normalize_training_language(language, default=default)

    async def get_qa_pairs(
        self, category: str | None = None, language: str | None = None, active_only: bool = True
    ) -> dict:
        """Get Q&A pairs with optional filtering"""
        filtered = self.qa_pairs

        if language:
            normalized_language = self._normalize_language(language, default="")
            filtered = [
                qa for qa in filtered if self._normalize_language(qa.get("language"), default="") == normalized_language
            ]

        if category:
            filtered = [qa for qa in filtered if qa.get("category") == category]

        print(f"📋 Retrieved {len(filtered)} Q&A pairs (filters: language={language}, category={category})")

        return {"success": True, "data": filtered, "count": len(filtered)}

    async def create_qa_pair(self, question: str, answer: str, language: str = "ar", category: str = "general") -> dict:
        """Create a new Q&A pair in JSONL"""

        try:
            # Ensure all required fields
            qa_pair = {
                "question": question,
                "answer": answer,
                "language": self._normalize_language(language),
                "category": category,
                "timestamp": datetime.now().isoformat(),
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
                    "error": f"Failed to save Q&A pair to {self.data_path}. Check file permissions.",
                }

            print(f"✅ Created Q&A pair: '{question}' ({language}/{category})")

            return {"success": True, "message": "Q&A pair created successfully", "data": qa_pair}
        except Exception as e:
            import traceback

            print(f"❌ Error creating Q&A pair: {e}")
            print(traceback.format_exc())
            return {"success": False, "error": str(e)}
            print(f"❌ Error creating Q&A pair: {e}")
            return {"success": False, "error": str(e)}

    async def update_qa_pair(self, qa_identifier: Any, updates: dict) -> dict:
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
                    return {"success": False, "error": "Must provide question and language for search"}

                # Find matching entry
                for idx, qa in enumerate(self.qa_pairs):
                    if qa.get("question") == search_question and qa.get("language") == search_language:
                        qa_index = idx
                        break

                if qa_index is None:
                    return {"success": False, "error": f"Q&A pair not found: '{search_question}' ({search_language})"}
            else:
                # Handle int identifier (index)
                qa_index = int(qa_identifier)
                if qa_index < 0 or qa_index >= len(self.qa_pairs):
                    return {"success": False, "error": "Invalid Q&A index"}

            # Update fields
            self.qa_pairs[qa_index].update(updates)
            self.qa_pairs[qa_index]["timestamp"] = datetime.now().isoformat()

            # Save to file
            save_success = self.save_to_jsonl()

            if not save_success:
                return {"success": False, "error": f"Failed to save Q&A pair to {self.data_path}"}

            print(f"✅ Updated Q&A pair at index {qa_index}: '{self.qa_pairs[qa_index].get('question')}'")

            return {"success": True, "message": "Q&A pair updated successfully", "data": self.qa_pairs[qa_index]}
        except Exception as e:
            import traceback

            print(f"❌ Error updating Q&A pair: {e}")
            print(traceback.format_exc())
            return {"success": False, "error": str(e)}

    async def delete_qa_pair(self, qa_identifier: Any) -> dict:
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
                    return {"success": False, "error": "Must provide question and language for search"}

                # Find matching entry
                for idx, qa in enumerate(self.qa_pairs):
                    if qa.get("question") == search_question and qa.get("language") == search_language:
                        qa_index = idx
                        break

                if qa_index is None:
                    return {"success": False, "error": f"Q&A pair not found: '{search_question}' ({search_language})"}
            else:
                # Handle int identifier (index)
                qa_index = int(qa_identifier)
                if qa_index < 0 or qa_index >= len(self.qa_pairs):
                    return {"success": False, "error": "Invalid Q&A index"}

            deleted = self.qa_pairs.pop(qa_index)

            # Save to file
            save_success = self.save_to_jsonl()

            if not save_success:
                # Restore the deleted item if save failed
                self.qa_pairs.insert(qa_index, deleted)
                return {
                    "success": False,
                    "error": f"Failed to save Q&A pair to {self.data_path}. Check file permissions.",
                }

            print(f"✅ Deleted Q&A pair: '{deleted.get('question')}'")

            return {"success": True, "message": "Q&A pair deleted successfully", "data": deleted}
        except Exception as e:
            import traceback

            print(f"❌ Error deleting Q&A pair: {e}")
            print(traceback.format_exc())
            return {"success": False, "error": str(e)}


# Singleton instance
local_qa_service = LocalQAService()


# Integration function for bot (replaces backend call)
async def get_qa_response(question: str, language: str = "ar") -> str | None:
    """Get response from local Q&A database"""
    match_result = await local_qa_service.find_match(question, language)

    if match_result:
        qa_pair = match_result["qa_pair"]
        match_score = match_result["match_score"]

        print("✅ Q&A Match Found!")
        print(f"   Score: {match_score:.2%}")
        print(f"   Category: {qa_pair.get('category')}")

        answer = qa_pair.get("answer", "")
        return cast(str | None, answer)

    return None
