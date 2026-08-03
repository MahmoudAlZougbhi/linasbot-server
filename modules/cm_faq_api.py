"""Content Management FAQ API — canonical owner-facing FAQ control plane."""

from __future__ import annotations

from typing import Any

from fastapi import Body, HTTPException, Query, Request

from modules.api_security import require_permission
from modules.core import app
from services.cm.faq_integration import (
    FaqIntegrationError,
    archive_cm_faq_group,
    create_faq_pair,
    create_faq_pair_from_livechat,
    find_duplicate_faq_groups,
    get_cm_faq_group,
    list_cm_faq,
    regenerate_cm_faq_variants,
    update_cm_faq_variant,
)


def _actor(session: Any) -> str:
    return getattr(session, "user_id", None) or getattr(session, "email", None) or "content_manager"


@app.get("/api/cm/faq")
async def cm_list_faq(
    request: Request,
    status: str | None = Query(default=None),
    language: str | None = Query(default=None),
    q: str | None = Query(default=None),
    reviewed: bool | None = Query(default=None),
    include_archived: bool = Query(default=False),
) -> Any:
    require_permission(request, "contentManagers")
    items = list_cm_faq(
        status=status,
        language=language,
        q=q,
        reviewed=reviewed,
        include_archived=include_archived,
    )
    return {"success": True, "data": items, "count": len(items)}


@app.get("/api/cm/faq/duplicates")
async def cm_faq_duplicates(
    request: Request,
    question: str = Query(...),
    language: str = Query(default="ar"),
) -> Any:
    require_permission(request, "contentManagers")
    hits = find_duplicate_faq_groups(question=question, language=language)
    return {"success": True, "data": hits, "count": len(hits)}


@app.post("/api/cm/faq")
async def cm_create_faq(request: Request, body: dict[str, Any] = Body(default={})) -> Any:
    session = require_permission(request, "contentManagers")
    question = str(body.get("question") or "").strip()
    answer = str(body.get("answer") or "").strip()
    language = str(body.get("language") or "ar")
    raw_tags = body.get("tags")
    tags = [str(tag) for tag in raw_tags] if isinstance(raw_tags, list) else []

    if not question or not answer:
        raise HTTPException(status_code=400, detail="question and answer are required")

    try:
        duplicates = find_duplicate_faq_groups(question=question, language=language)
        result = await create_faq_pair(
            question=question,
            answer=answer,
            language=language,
            tags=tags,
            updated_by=_actor(session),
        )
    except FaqIntegrationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return {"success": True, "duplicates": duplicates, **result}


@app.post("/api/cm/faq/from-livechat")
async def cm_faq_from_livechat(request: Request, body: dict[str, Any] = Body(default={})) -> Any:
    """Live Chat Like → canonical FAQ. Requires liveChat; contentPublish for add_and_publish."""
    session = require_permission(request, "liveChat")
    question = str(body.get("question") or body.get("user_question") or "").strip()
    answer = str(body.get("answer") or body.get("correct_answer") or "").strip()
    language = str(body.get("language") or "ar")
    publish = bool(body.get("publish") or body.get("add_and_publish"))
    if publish:
        require_permission(request, "contentPublish")
    if not question or not answer:
        raise HTTPException(status_code=400, detail="question and answer are required")
    try:
        result = await create_faq_pair_from_livechat(
            question=question,
            answer=answer,
            language=language,
            updated_by=_actor(session),
            publish=publish,
        )
    except FaqIntegrationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"success": True, **result}


@app.get("/api/cm/faq/{qa_group_id}")
async def cm_get_faq(request: Request, qa_group_id: str) -> Any:
    require_permission(request, "contentManagers")
    item = get_cm_faq_group(qa_group_id=qa_group_id)
    if item is None:
        raise HTTPException(status_code=404, detail="FAQ group not found")
    return {"success": True, "data": item}


@app.patch("/api/cm/faq/{qa_group_id}/variants/{language}")
async def cm_patch_faq_variant(
    request: Request,
    qa_group_id: str,
    language: str,
    body: dict[str, Any] = Body(default={}),
) -> Any:
    session = require_permission(request, "contentManagers")
    try:
        result = await update_cm_faq_variant(
            qa_group_id=qa_group_id,
            language=language,
            question=body.get("question"),
            answer=body.get("answer"),
            reviewed=body.get("reviewed") if "reviewed" in body else None,
            updated_by=_actor(session),
        )
    except FaqIntegrationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return result


@app.post("/api/cm/faq/{qa_group_id}/regenerate")
async def cm_regenerate_faq(
    request: Request,
    qa_group_id: str,
    body: dict[str, Any] = Body(default={}),
) -> Any:
    session = require_permission(request, "contentManagers")
    raw_langs = body.get("languages")
    languages = [str(lang) for lang in raw_langs] if isinstance(raw_langs, list) else None
    try:
        result = await regenerate_cm_faq_variants(
            qa_group_id=qa_group_id,
            source_language=str(body["source_language"]) if body.get("source_language") else None,
            languages=languages,
            updated_by=_actor(session),
        )
    except FaqIntegrationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return result


@app.post("/api/cm/faq/{qa_group_id}/archive")
async def cm_archive_faq(request: Request, qa_group_id: str) -> Any:
    session = require_permission(request, "contentManagers")
    try:
        return archive_cm_faq_group(qa_group_id=qa_group_id, updated_by=_actor(session))
    except FaqIntegrationError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
