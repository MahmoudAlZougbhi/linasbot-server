# -*- coding: utf-8 -*-
"""
Content Files Service - File system for Knowledge Base, Style Guide, and Price List.
Each section supports multiple files with title, content, tags, and language.
"""

import json
import os
import uuid
from datetime import datetime
from typing import Dict, List, Optional
from pathlib import Path

from storage.persistent_storage import (
    CONTENT_DIR,
    KNOWLEDGE_FILES_DIR,
    STYLE_FILES_DIR,
    PRICE_FILES_DIR,
    ensure_dirs,
)

CONTENT_SECTIONS = {
    "knowledge": {"dir": str(KNOWLEDGE_FILES_DIR), "name": "Knowledge Base"},
    "style": {"dir": str(STYLE_FILES_DIR), "name": "Style Guide"},
    "price": {"dir": str(PRICE_FILES_DIR), "name": "Price List"},
}


def _section_path(section: str) -> str:
    """Get full path for a section's directory (persistent storage)."""
    if section not in CONTENT_SECTIONS:
        raise ValueError(f"Unknown section: {section}")
    ensure_dirs()
    return CONTENT_SECTIONS[section]["dir"]


def _ensure_section_dir(section: str) -> str:
    """Ensure section directory exists; return full path."""
    path = _section_path(section)
    os.makedirs(path, exist_ok=True)
    return path


def _file_path(section: str, file_id: str) -> str:
    """Get full path for a content file."""
    return os.path.join(_section_path(section), f"{file_id}.json")


def _list_json_files(section: str) -> List[str]:
    """List all .json file IDs in a section (without .json extension)."""
    path = _section_path(section)
    if not os.path.exists(path):
        return []
    ids = []
    for name in os.listdir(path):
        if name.endswith(".json"):
            ids.append(name[:-5])
    return ids


def list_files(section: str) -> List[Dict]:
    """
    List all files in a section.
    Returns list of dicts with: id, title, tags, language, created_at, updated_at
    (content is NOT included for listing - use get_file for full content)
    """
    _ensure_section_dir(section)
    result = []
    for file_id in _list_json_files(section):
        try:
            with open(_file_path(section, file_id), "r", encoding="utf-8") as f:
                data = json.load(f)
            aud = (data.get("audience") or "general").lower()
            if aud not in ("men", "women", "general"):
                aud = "general"
            prio = data.get("priority", 3)
            try:
                prio = max(1, min(5, int(prio)))
            except (TypeError, ValueError):
                prio = 3
            result.append({
                "id": file_id,
                "title": data.get("title", ""),
                "tags": data.get("tags", []),
                "language": data.get("language", ""),
                "audience": aud,
                "priority": prio,
                "created_at": data.get("created_at", ""),
                "updated_at": data.get("updated_at", ""),
            })
        except Exception as e:
            print(f"⚠️ Error loading file {file_id} in {section}: {e}")
    return sorted(result, key=lambda x: (x.get("updated_at", ""), x.get("title", "")), reverse=True)


def get_titles_only(section: str) -> List[Dict[str, str]]:
    """
    Get titles and metadata for smart retrieval (lightweight, cacheable).
    Returns: [{"id", "title", "tags", "language", "audience", "priority"}, ...]
    audience: "men" | "women" | "general" (default "general")
    priority: 1-5, higher = more important (default 3)
    """
    _ensure_section_dir(section)
    result = []
    for file_id in _list_json_files(section):
        try:
            with open(_file_path(section, file_id), "r", encoding="utf-8") as f:
                data = json.load(f)
            audience = (data.get("audience") or "general").lower()
            if audience not in ("men", "women", "general"):
                audience = "general"
            priority = data.get("priority")
            if priority is None:
                priority = 3
            try:
                priority = max(1, min(5, int(priority)))
            except (TypeError, ValueError):
                priority = 3
            result.append({
                "id": file_id,
                "title": data.get("title", ""),
                "tags": data.get("tags", []),
                "language": data.get("language", ""),
                "audience": audience,
                "priority": priority,
            })
        except Exception as e:
            print(f"⚠️ Error loading titles for {file_id}: {e}")
    return result


def get_file(section: str, file_id: str) -> Optional[Dict]:
    """Get full file content by ID."""
    path = _file_path(section, file_id)
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"⚠️ Error reading file {file_id}: {e}")
        return None


def create_file(
    section: str,
    title: str,
    content: str,
    tags: Optional[List[str]] = None,
    language: Optional[str] = None,
    audience: Optional[str] = None,
    priority: Optional[int] = None,
) -> Dict:
    """Create a new content file.
    audience: "men" | "women" | "general" (default "general")
    priority: 1-5 (default 3)
    """
    _ensure_section_dir(section)
    file_id = str(uuid.uuid4())
    now = datetime.utcnow().isoformat() + "Z"
    aud = (audience or "general").lower()
    if aud not in ("men", "women", "general"):
        aud = "general"
    prio = priority if priority is not None else 3
    try:
        prio = max(1, min(5, int(prio)))
    except (TypeError, ValueError):
        prio = 3
    data = {
        "id": file_id,
        "title": title or "Untitled",
        "content": content or "",
        "tags": tags if tags is not None else [],
        "language": language or "",
        "audience": aud,
        "priority": prio,
        "created_at": now,
        "updated_at": now,
    }
    path = _file_path(section, file_id)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return data


def update_file(
    section: str,
    file_id: str,
    title: Optional[str] = None,
    content: Optional[str] = None,
    tags: Optional[List[str]] = None,
    language: Optional[str] = None,
    audience: Optional[str] = None,
    priority: Optional[int] = None,
) -> Optional[Dict]:
    """Update an existing content file."""
    path = _file_path(section, file_id)
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        print(f"⚠️ Error reading file for update: {e}")
        return None

    if title is not None:
        data["title"] = title
    if content is not None:
        data["content"] = content
    if tags is not None:
        data["tags"] = tags
    if language is not None:
        data["language"] = language
    if audience is not None:
        aud = audience.lower()
        data["audience"] = aud if aud in ("men", "women", "general") else "general"
    if priority is not None:
        try:
            data["priority"] = max(1, min(5, int(priority)))
        except (TypeError, ValueError):
            pass
    data["updated_at"] = datetime.utcnow().isoformat() + "Z"

    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return data


def delete_file(section: str, file_id: str) -> bool:
    """Delete a content file."""
    path = _file_path(section, file_id)
    if os.path.exists(path):
        os.remove(path)
        return True
    return False


def load_file_contents(section: str, file_ids: List[str]) -> str:
    """
    Load content from selected files and concatenate.
    Used by smart retrieval after file selection.
    """
    if not file_ids:
        return ""
    parts = []
    for file_id in file_ids:
        data = get_file(section, file_id)
        if data and data.get("content"):
            title = data.get("title", "Untitled")
            parts.append(f"--- {title} ---\n{data['content']}")
    return "\n\n".join(parts)


def migrate_from_legacy(section: str, legacy_path: str) -> Optional[str]:
    """
    Migrate from legacy single .txt file to new file system.
    Creates one file with content from legacy file.
    legacy_path: absolute or project-relative path (e.g. data/knowledge_base.txt).
    Returns the new file_id if migration was performed, else None.
    """
    from pathlib import Path
    full_path = Path(legacy_path)
    if not full_path.is_absolute():
        base = Path(__file__).resolve().parent.parent
        full_path = base / legacy_path
    # Fallback: check persistent content dir (e.g. /opt/linasbot_data/content/knowledge_base.txt)
    if not full_path.exists() and section in CONTENT_SECTIONS:
        legacy_name = Path(legacy_path).name
        persistent_legacy = CONTENT_DIR / legacy_name
        if persistent_legacy.exists():
            full_path = persistent_legacy
    if not full_path.exists():
        return None
    if _list_json_files(section):
        return None  # Already has files, skip migration

    with open(full_path, "r", encoding="utf-8") as f:
        content = f.read().strip()
    if not content:
        return None

    # Infer title from section name
    title_map = {"knowledge": "Core Knowledge Base", "style": "Bot Style Guide", "price": "Price List"}
    title = title_map.get(section, "Migrated Content")
    data = create_file(section, title, content, tags=[], language="")
    return data.get("id")
