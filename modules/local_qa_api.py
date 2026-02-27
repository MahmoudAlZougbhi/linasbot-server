# -*- coding: utf-8 -*-
"""
Local Q&A API module: Simple JSON file-based Q&A management
Handles CRUD operations for local qa_pairs.jsonl file
"""

import json
import os
from datetime import datetime
from typing import Optional
import uuid
from fastapi import HTTPException

from modules.core import app
from services.language_detection_service import language_detection_service

# Path to local Q&A file
QA_FILE_PATH = "data/qa_pairs.jsonl"


def ensure_qa_file_exists():
    """Ensure the Q&A file exists"""
    os.makedirs("data", exist_ok=True)
    if not os.path.exists(QA_FILE_PATH):
        with open(QA_FILE_PATH, 'w', encoding='utf-8') as f:
            pass  # Create empty file


def read_qa_pairs():
    """Read all Q&A pairs from JSONL file"""
    ensure_qa_file_exists()
    qa_pairs = []
    
    try:
        with open(QA_FILE_PATH, 'r', encoding='utf-8') as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if line:
                    try:
                        qa_pair = json.loads(line)
                        qa_pair['id'] = line_num  # Use line number as ID
                        qa_pairs.append(qa_pair)
                    except json.JSONDecodeError as e:
                        print(f"⚠️ Error parsing line {line_num}: {e}")
                        continue
    except Exception as e:
        print(f"❌ Error reading Q&A file: {e}")
    
    return qa_pairs


def write_qa_pairs(qa_pairs):
    """Write all Q&A pairs to JSONL file"""
    ensure_qa_file_exists()
    
    try:
        with open(QA_FILE_PATH, 'w', encoding='utf-8') as f:
            for qa_pair in qa_pairs:
                # Remove 'id' field before writing (it's generated from line number)
                qa_to_write = {k: v for k, v in qa_pair.items() if k != 'id'}
                f.write(json.dumps(qa_to_write, ensure_ascii=False) + '\n')
        return True
    except Exception as e:
        print(f"❌ Error writing Q&A file: {e}")
        return False


def build_qa_entry(
    question: str,
    answer: str,
    language: str,
    category: str,
    qa_group_id: str,
    source_language: str,
    is_auto_translated: bool,
):
    """Build a normalized Q&A entry for JSONL storage."""
    return {
        "question": question,
        "answer": answer,
        "language": language_detection_service.normalize_training_language(language),
        "category": category,
        "timestamp": datetime.now().isoformat(),
        "qa_group_id": qa_group_id,
        "source_language": language_detection_service.normalize_training_language(source_language),
        "is_auto_translated": bool(is_auto_translated),
    }


def reload_local_qa_cache():
    """Reload in-memory local QA cache so bot uses latest training instantly."""
    try:
        from services.local_qa_service import local_qa_service

        local_qa_service.qa_pairs = local_qa_service.load_from_jsonl()
    except Exception as e:
        print(f"⚠️ Failed to reload local_qa_service cache: {e}")


@app.get("/api/local-qa/list")
async def list_local_qa_pairs(language: Optional[str] = None):
    """List all Q&A pairs from local JSON file"""
    try:
        print("📖 Reading local Q&A pairs from file...")
        qa_pairs = read_qa_pairs()
        selected_language = language_detection_service.normalize_training_language(
            language, default="ar"
        )

        if selected_language:
            qa_pairs = [
                qa for qa in qa_pairs
                if language_detection_service.normalize_training_language(
                    qa.get("language"), default=""
                ) == selected_language
            ]

        by_language = {"ar": [], "en": [], "fr": [], "franco": []}
        for qa in qa_pairs:
            lang = language_detection_service.normalize_training_language(qa.get("language"))
            if lang not in by_language:
                by_language[lang] = []
            by_language[lang].append(qa)

        print(
            f"✅ Found {len(qa_pairs)} Q&A pairs"
            f"{f' for {selected_language}' if selected_language else ''}"
        )
        
        return {
            "success": True,
            "data": qa_pairs,
            "count": len(qa_pairs),
            "selected_language": selected_language,
            "by_language": by_language,
        }
    except Exception as e:
        print(f"❌ Error listing Q&A pairs: {e}")
        return {"success": False, "error": str(e)}


@app.post("/api/local-qa/create")
async def create_local_qa_pair(qa_data: dict):
    """Create a new Q&A pair in local JSON file"""
    try:
        print("\n" + "="*80)
        print("🆕 Creating new Q&A pair (LOCAL JSON)")
        print("="*80)
        print(f"📥 Received data: {qa_data}")
        
        question = qa_data.get("question", "").strip()
        answer = qa_data.get("answer", "").strip()
        category = qa_data.get("category", "general")
        requested_language = qa_data.get("language")
        
        if not question or not answer:
            return {
                "success": False,
                "error": "Question and answer are required"
            }
        
        detected_language = language_detection_service.normalize_training_language(
            requested_language,
            default=language_detection_service.detect_training_language(question),
        )
        print(f"🔍 Training language: {detected_language}")

        qa_group_id = qa_data.get("qa_group_id") or f"qa_{uuid.uuid4().hex[:10]}"
        created_entries = []

        if detected_language == "ar":
            # Arabic source entries must save EN/FR/Franco variants too.
            translation_result = await language_detection_service.translate_arabic_training_pair(
                question_ar=question,
                answer_ar=answer,
                target_languages=["en", "fr", "franco"],
            )
            if not translation_result.get("success"):
                return {
                    "success": False,
                    "error": "Failed to auto-translate Arabic Q&A to all target languages",
                    "missing_languages": translation_result.get("missing_languages", []),
                }

            created_entries.append(
                build_qa_entry(
                    question=question,
                    answer=answer,
                    language="ar",
                    category=category,
                    qa_group_id=qa_group_id,
                    source_language="ar",
                    is_auto_translated=False,
                )
            )

            translations = translation_result.get("translations", {})
            for target_lang in ["en", "fr", "franco"]:
                translated = translations.get(target_lang, {})
                created_entries.append(
                    build_qa_entry(
                        question=translated.get("question", ""),
                        answer=translated.get("answer", ""),
                        language=target_lang,
                        category=category,
                        qa_group_id=qa_group_id,
                        source_language="ar",
                        is_auto_translated=True,
                    )
                )
        else:
            created_entries.append(
                build_qa_entry(
                    question=question,
                    answer=answer,
                    language=detected_language,
                    category=category,
                    qa_group_id=qa_group_id,
                    source_language=detected_language,
                    is_auto_translated=False,
                )
            )
        
        # Read existing Q&A pairs
        qa_pairs = read_qa_pairs()
        
        # Append new Q&A entries (single language or multilingual batch)
        qa_pairs.extend(created_entries)
        
        # Write back to file
        if write_qa_pairs(qa_pairs):
            reload_local_qa_cache()
            print(f"✅ Q&A pair saved successfully!")
            print(f"   Question: {question}")
            print(f"   Answer: {answer}")
            print(f"   Language: {detected_language}")
            print(f"   Category: {category}")
            print(f"   Entries created: {len(created_entries)}")
            print("="*80 + "\n")
            
            return {
                "success": True,
                "message": "Q&A pair created successfully",
                "data": created_entries[0],
                "created_entries": created_entries,
                "count_created": len(created_entries),
                "detected_language": detected_language,
                "qa_group_id": qa_group_id,
            }
        else:
            return {
                "success": False,
                "error": "Failed to write to file"
            }
            
    except Exception as e:
        print(f"❌ Error creating Q&A pair: {e}")
        import traceback
        traceback.print_exc()
        return {"success": False, "error": str(e)}


@app.put("/api/local-qa/{qa_id}")
async def update_local_qa_pair(qa_id: int, updates: dict):
    """Update an existing Q&A pair in local JSON file"""
    try:
        print(f"✏️ Updating Q&A pair ID: {qa_id}")
        
        qa_pairs = read_qa_pairs()
        
        # Find the Q&A pair by ID (line number)
        if qa_id < 1 or qa_id > len(qa_pairs):
            return {
                "success": False,
                "error": f"Q&A pair with ID {qa_id} not found"
            }
        
        # Update the Q&A pair (ID is 1-indexed, list is 0-indexed)
        qa_index = qa_id - 1
        
        if "question" in updates:
            qa_pairs[qa_index]["question"] = updates["question"]
        if "answer" in updates:
            qa_pairs[qa_index]["answer"] = updates["answer"]
        if "category" in updates:
            qa_pairs[qa_index]["category"] = updates["category"]
        if "language" in updates:
            qa_pairs[qa_index]["language"] = language_detection_service.normalize_training_language(
                updates["language"]
            )
        
        # Re-detect language only if question changed and language not explicitly provided
        if "question" in updates and "language" not in updates:
            qa_pairs[qa_index]["language"] = language_detection_service.detect_training_language(
                updates["question"]
            )
        
        qa_pairs[qa_index]["timestamp"] = datetime.now().isoformat()
        
        # Write back to file
        if write_qa_pairs(qa_pairs):
            reload_local_qa_cache()
            print(f"✅ Q&A pair {qa_id} updated successfully")
            return {
                "success": True,
                "message": "Q&A pair updated successfully",
                "data": qa_pairs[qa_index]
            }
        else:
            return {
                "success": False,
                "error": "Failed to write to file"
            }
            
    except Exception as e:
        print(f"❌ Error updating Q&A pair: {e}")
        return {"success": False, "error": str(e)}


@app.delete("/api/local-qa/{qa_id}")
async def delete_local_qa_pair(qa_id: int):
    """Delete a Q&A pair from local JSON file"""
    try:
        print(f"🗑️ Deleting Q&A pair ID: {qa_id}")
        
        qa_pairs = read_qa_pairs()
        
        # Find the Q&A pair by ID (line number)
        if qa_id < 1 or qa_id > len(qa_pairs):
            return {
                "success": False,
                "error": f"Q&A pair with ID {qa_id} not found"
            }
        
        # Remove the Q&A pair (ID is 1-indexed, list is 0-indexed)
        deleted_qa = qa_pairs.pop(qa_id - 1)
        
        # Write back to file
        if write_qa_pairs(qa_pairs):
            reload_local_qa_cache()
            print(f"✅ Q&A pair {qa_id} deleted successfully")
            print(f"   Deleted: {deleted_qa['question']}")
            return {
                "success": True,
                "message": "Q&A pair deleted successfully",
                "deleted": deleted_qa
            }
        else:
            return {
                "success": False,
                "error": "Failed to write to file"
            }
            
    except Exception as e:
        print(f"❌ Error deleting Q&A pair: {e}")
        return {"success": False, "error": str(e)}


@app.get("/api/local-qa/statistics")
async def get_local_qa_statistics():
    """Get statistics about local Q&A pairs"""
    try:
        qa_pairs = read_qa_pairs()
        
        # Count by language
        language_counts = {}
        category_counts = {}
        
        for qa in qa_pairs:
            lang = language_detection_service.normalize_training_language(
                qa.get("language"), default="unknown"
            )
            cat = qa.get("category", "general")
            
            language_counts[lang] = language_counts.get(lang, 0) + 1
            category_counts[cat] = category_counts.get(cat, 0) + 1
        
        return {
            "success": True,
            "statistics": {
                "total": len(qa_pairs),
                "by_language": language_counts,
                "by_category": category_counts
            }
        }
    except Exception as e:
        print(f"❌ Error getting statistics: {e}")
        return {"success": False, "error": str(e)}


@app.post("/api/local-qa/test-match")
async def test_local_qa_match(test_data: dict):
    """Test if a question matches any Q&A pair in local file"""
    try:
        question = test_data.get("question", "")
        language = test_data.get("language", "ar")
        
        if not question:
            return {"success": False, "error": "Question is required"}
        
        print(f"\n{'='*80}")
        print(f"🧪 TESTING LOCAL Q&A MATCH")
        print(f"{'='*80}")
        print(f"📝 Question: {question}")
        print(f"🌐 Language: {language}")
        
        # Import local Q&A service
        from services.local_qa_service import local_qa_service
        
        # Reload Q&A pairs to ensure we have latest data
        local_qa_service.qa_pairs = local_qa_service.load_from_jsonl()
        print(f"📚 Loaded {len(local_qa_service.qa_pairs)} Q&A pairs")
        
        match_result = await local_qa_service.find_match(question, language)
        
        if match_result:
            qa_pair = match_result["qa_pair"]
            match_score = match_result["match_score"]
            
            print(f"✅ MATCH FOUND!")
            print(f"   Score: {match_score:.2%}")
            print(f"   Matched Question: {qa_pair.get('question')}")
            print(f"   Answer: {qa_pair.get('answer')[:100]}...")
            print(f"{'='*80}\n")
            
            return {
                "success": True,
                "match_found": True,
                "match_score": match_score,
                "matched_question": qa_pair.get("question"),
                "answer": qa_pair.get("answer"),
                "category": qa_pair.get("category"),
                "language": qa_pair.get("language")
            }
        else:
            print(f"❌ NO MATCH FOUND")
            print(f"{'='*80}\n")
            
            return {
                "success": True,
                "match_found": False,
                "message": "No matching Q&A pair found (threshold: 70%)"
            }
    except Exception as e:
        print(f"❌ Error testing Q&A match: {e}")
        import traceback
        traceback.print_exc()
        return {"success": False, "error": str(e)}
