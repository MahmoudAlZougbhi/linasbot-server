# -*- coding: utf-8 -*-
"""
Content Files API - CRUD for Knowledge, Style, and Price List files.
Each section is a file system with Create (+) button.
"""

from fastapi import HTTPException, Body
from modules.core import app
from services import content_files_service as cfs
from services.smart_retrieval_service import invalidate_titles_cache


VALID_SECTIONS = {"knowledge", "style", "price"}


def _validate_section(section: str) -> None:
    if section not in VALID_SECTIONS:
        raise HTTPException(status_code=400, detail=f"Invalid section. Must be one of: {', '.join(VALID_SECTIONS)}")


@app.get("/api/content-files/{section}/list")
async def list_content_files(section: str):
    """List all files in a section (titles, tags, language only - no content)."""
    _validate_section(section)
    try:
        files = cfs.list_files(section)
        return {"success": True, "data": files, "count": len(files)}
    except Exception as e:
        return {"success": False, "error": str(e), "data": [], "count": 0}


@app.get("/api/content-files/{section}/titles")
async def get_titles_only(section: str):
    """Get titles only for smart retrieval (cacheable)."""
    _validate_section(section)
    try:
        titles = cfs.get_titles_only(section)
        return {"success": True, "data": titles, "count": len(titles)}
    except Exception as e:
        return {"success": False, "error": str(e), "data": []}


@app.get("/api/content-files/{section}/{file_id}")
async def get_content_file(section: str, file_id: str):
    """Get full file content by ID."""
    _validate_section(section)
    data = cfs.get_file(section, file_id)
    if data is None:
        raise HTTPException(status_code=404, detail="File not found")
    return {"success": True, "data": data}


@app.post("/api/content-files/{section}/create")
async def create_content_file(section: str, request: dict = Body(default={})):
    """Create a new content file."""
    _validate_section(section)
    title = request.get("title", "").strip()
    content = request.get("content", "")
    tags = request.get("tags")
    language = request.get("language")
    audience = request.get("audience")  # men | women | general
    priority = request.get("priority")  # 1-5
    if isinstance(tags, str):
        tags = [t.strip() for t in tags.split(",") if t.strip()]
    if tags is None:
        tags = []
    try:
        data = cfs.create_file(section, title, content or "", tags=tags, language=language or "", audience=audience, priority=priority)
        invalidate_titles_cache()
        return {"success": True, "message": "File created", "data": data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.put("/api/content-files/{section}/{file_id}")
async def update_content_file(section: str, file_id: str, request: dict = Body(default={})):
    """Update an existing content file."""
    _validate_section(section)
    data = cfs.get_file(section, file_id)
    if data is None:
        raise HTTPException(status_code=404, detail="File not found")
    title = request.get("title")
    content = request.get("content")
    tags = request.get("tags")
    language = request.get("language")
    audience = request.get("audience")
    priority = request.get("priority")
    if tags is not None and isinstance(tags, str):
        tags = [t.strip() for t in tags.split(",") if t.strip()]
    try:
        updated = cfs.update_file(section, file_id, title=title, content=content, tags=tags, language=language, audience=audience, priority=priority)
        invalidate_titles_cache()
        return {"success": True, "message": "File updated", "data": updated}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/content-files/{section}/{file_id}")
async def delete_content_file(section: str, file_id: str):
    """Delete a content file."""
    _validate_section(section)
    if not cfs.delete_file(section, file_id):
        raise HTTPException(status_code=404, detail="File not found")
    invalidate_titles_cache()
    return {"success": True, "message": "File deleted"}


@app.get("/api/retrieval-debug/logs")
async def get_retrieval_debug_logs(limit: int = 50):
    """Admin-only: Get recent retrieval debug logs for transparency panel.
    Enable SMART_RETRIEVAL_DEBUG=1 for logs to be collected."""
    from services.retrieval_debug import get_recent_logs, is_debug_enabled
    if not is_debug_enabled():
        return {"success": True, "data": [], "message": "Debug disabled. Set SMART_RETRIEVAL_DEBUG=1 to enable."}
    logs = get_recent_logs(limit=min(limit, 100))
    return {"success": True, "data": logs, "count": len(logs)}


@app.post("/api/content-files/migrate-legacy")
async def migrate_legacy():
    """Migrate from legacy single .txt files to new file system (one-time)."""
    results = {}
    for section, legacy in [("knowledge", "data/knowledge_base.txt"), ("style", "data/style_guide.txt"), ("price", "data/price_list.txt")]:
        try:
            file_id = cfs.migrate_from_legacy(section, legacy)
            results[section] = {"migrated": file_id is not None, "file_id": file_id}
        except Exception as e:
            results[section] = {"migrated": False, "error": str(e)}
    return {"success": True, "results": results}
