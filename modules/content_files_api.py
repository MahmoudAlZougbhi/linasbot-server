"""Legacy global content-files API — disabled (410 Gone).

Product path is tenant CM: ``/api/cm/...``.
Runtime still may use ``services.content_files_service`` for linas-era retrieval;
this module only refuses HTTP mutation/read of the shared global store.
"""

from __future__ import annotations

from typing import Any

from fastapi.responses import JSONResponse

from modules.core import app

_GONE = {
    "success": False,
    "error": "Legacy /api/content-files is disabled. Use tenant Content Management (/api/cm/...).",
    "code": "CONTENT_FILES_API_GONE",
}


def _gone() -> JSONResponse:
    return JSONResponse(status_code=410, content=_GONE)


@app.get("/api/content-files/{section}/list")
async def list_content_files(section: str) -> Any:
    return _gone()


@app.get("/api/content-files/{section}/titles")
async def get_titles_only(section: str) -> Any:
    return _gone()


@app.get("/api/content-files/{section}/{file_id}")
async def get_content_file(section: str, file_id: str) -> Any:
    return _gone()


@app.post("/api/content-files/{section}/create")
async def create_content_file(section: str) -> Any:
    return _gone()


@app.put("/api/content-files/{section}/{file_id}")
async def update_content_file(section: str, file_id: str) -> Any:
    return _gone()


@app.delete("/api/content-files/{section}/{file_id}")
async def delete_content_file(section: str, file_id: str) -> Any:
    return _gone()


@app.get("/api/retrieval-debug/logs")
async def get_retrieval_debug_logs(limit: int = 50) -> Any:
    return _gone()


@app.post("/api/content-files/migrate-legacy")
async def migrate_legacy() -> Any:
    return _gone()


@app.get("/api/content-files/dynamic-messages")
async def get_dynamic_messages() -> Any:
    return _gone()


@app.put("/api/content-files/dynamic-messages")
async def put_dynamic_messages() -> Any:
    return _gone()
