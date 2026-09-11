"""Local Q&A helpers used by CM FAQ and Live Chat — no leftover HTTP CRUD.

Mobile FAQ writes go through ``/api/cm/faq*``. ``create_local_qa_pair`` stays as a
blocked legacy writer so CM-canonical tests can prove it cannot dual-write.
"""

from __future__ import annotations

from typing import Any

from modules.local_qa_api_helpers import (  # noqa: F401
    _LEGACY_FAQ_WRITE_BLOCKED,
    QA_FILE_PATH,
    _legacy_faq_writes_blocked,
    build_qa_entry,
    create_local_qa_pair_internal,
    read_qa_pairs,
    reload_local_qa_cache,
    write_qa_pairs,
)


async def create_local_qa_pair(qa_data: dict) -> Any:
    """Legacy FAQ create — always blocked when CM FAQ is canonical."""
    blocked = _legacy_faq_writes_blocked()
    if blocked is not None:
        return blocked
    try:
        return await create_local_qa_pair_internal(
            question=(qa_data.get("question") or "").strip(),
            answer=(qa_data.get("answer") or "").strip(),
            language=qa_data.get("language") or "ar",
            category=qa_data.get("category", "general"),
        )
    except Exception as e:
        return {"success": False, "error": str(e)}
