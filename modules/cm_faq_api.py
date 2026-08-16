"""AI Setup FAQ API — canonical owner-facing FAQ control plane."""

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
    replace_cm_faq_attachments,
    update_cm_faq_variant,
)
from services.dashboard_session_service import SessionRecord


def _actor(session: Any) -> str:
    return getattr(session, "user_id", None) or getattr(session, "email", None) or "content_manager"


def _session_tenant(session: SessionRecord) -> str:
    tenant_id = str(session.tenant_id or "").strip()
    if not tenant_id:
        raise HTTPException(status_code=403, detail="Tenant context required")
    return tenant_id


@app.get("/api/cm/faq")
async def cm_list_faq(
    request: Request,
    status: str | None = Query(default=None),
    language: str | None = Query(default=None),
    q: str | None = Query(default=None),
    reviewed: bool | None = Query(default=None),
    include_archived: bool = Query(default=False),
) -> Any:
    session = require_permission(request, "contentManagers")
    tenant_id = _session_tenant(session)
    from services.faq_entitlements import get_faq_entitlement

    items = list_cm_faq(
        tenant_id=tenant_id,
        status=status,
        language=language,
        q=q,
        reviewed=reviewed,
        include_archived=include_archived,
    )
    entitlement = get_faq_entitlement(tenant_id)
    from services.cm.smart_answer_languages import smart_answer_languages_public

    langs = smart_answer_languages_public(tenant_id=tenant_id)
    return {
        "success": True,
        "data": items,
        "count": len(items),
        "entitlement": entitlement,
        "quota_display": entitlement.get("quota_display"),
        **langs,
    }


@app.get("/api/cm/faq/duplicates")
async def cm_faq_duplicates(
    request: Request,
    question: str = Query(...),
    language: str = Query(default="ar"),
) -> Any:
    session = require_permission(request, "contentManagers")
    tenant_id = _session_tenant(session)
    hits = find_duplicate_faq_groups(question=question, language=language, tenant_id=tenant_id)
    return {"success": True, "data": hits, "count": len(hits)}


@app.post("/api/cm/faq")
async def cm_create_faq(request: Request, body: dict[str, Any] = Body(default={})) -> Any:
    session = require_permission(request, "contentManagers")
    tenant_id = _session_tenant(session)
    question = str(body.get("question") or "").strip()
    answer = str(body.get("answer") or "").strip()
    language = str(body.get("language") or "ar")
    raw_tags = body.get("tags")
    tags = [str(tag) for tag in raw_tags] if isinstance(raw_tags, list) else []

    if not question or not answer:
        raise HTTPException(status_code=400, detail="question and answer are required")

    from services.faq_entitlements import FaqEntitlementError, assert_can_create_faq

    try:
        assert_can_create_faq(tenant_id)
    except FaqEntitlementError as exc:
        status = 403 if exc.code == "FAQ_DISABLED" else 402
        raise HTTPException(status_code=status, detail={"code": exc.code, **exc.payload}) from exc

    try:
        duplicates = find_duplicate_faq_groups(question=question, language=language, tenant_id=tenant_id)
        result = await create_faq_pair(
            question=question,
            answer=answer,
            language=language,
            tags=tags,
            updated_by=_actor(session),
            tenant_id=tenant_id,
        )
    except FaqIntegrationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    from services.faq_entitlements import get_faq_entitlement

    return {
        "success": True,
        "duplicates": duplicates,
        "entitlement": get_faq_entitlement(tenant_id),
        **result,
    }


@app.post("/api/cm/faq/from-livechat")
async def cm_faq_from_livechat(request: Request, body: dict[str, Any] = Body(default={})) -> Any:
    """Live Chat Like → canonical FAQ. Requires liveChat; contentPublish for add_and_publish."""
    session = require_permission(request, "liveChat")
    tenant_id = _session_tenant(session)
    question = str(body.get("question") or body.get("user_question") or "").strip()
    answer = str(body.get("answer") or body.get("correct_answer") or "").strip()
    language = str(body.get("language") or "ar")
    publish = bool(body.get("publish") or body.get("add_and_publish"))
    if publish:
        require_permission(request, "contentPublish")
    if not question or not answer:
        raise HTTPException(status_code=400, detail="question and answer are required")

    from services.faq_entitlements import FaqEntitlementError, assert_can_create_faq

    try:
        assert_can_create_faq(tenant_id)
    except FaqEntitlementError as exc:
        status = 403 if exc.code == "FAQ_DISABLED" else 402
        raise HTTPException(status_code=status, detail={"code": exc.code, **exc.payload}) from exc

    try:
        result = await create_faq_pair_from_livechat(
            question=question,
            answer=answer,
            language=language,
            updated_by=_actor(session),
            publish=publish,
            tenant_id=tenant_id,
        )
    except FaqIntegrationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"success": True, **result}


@app.get("/api/cm/faq/{qa_group_id}")
async def cm_get_faq(request: Request, qa_group_id: str) -> Any:
    session = require_permission(request, "contentManagers")
    tenant_id = _session_tenant(session)
    item = get_cm_faq_group(qa_group_id=qa_group_id, tenant_id=tenant_id)
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
    tenant_id = _session_tenant(session)
    try:
        result = await update_cm_faq_variant(
            qa_group_id=qa_group_id,
            language=language,
            question=body.get("question"),
            answer=body.get("answer"),
            reviewed=body.get("reviewed") if "reviewed" in body else None,
            updated_by=_actor(session),
            tenant_id=tenant_id,
        )
    except FaqIntegrationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return result


@app.put("/api/cm/faq/{qa_group_id}/attachments")
async def cm_put_faq_attachments(
    request: Request,
    qa_group_id: str,
    body: dict[str, Any] = Body(default={}),
) -> Any:
    session = require_permission(request, "contentManagers")
    tenant_id = _session_tenant(session)
    raw = body.get("attachments")
    if not isinstance(raw, list):
        raise HTTPException(status_code=400, detail="attachments array is required")
    try:
        return replace_cm_faq_attachments(
            qa_group_id=qa_group_id,
            attachments=raw,
            updated_by=_actor(session),
            tenant_id=tenant_id,
        )
    except FaqIntegrationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/api/cm/faq/{qa_group_id}/regenerate")
async def cm_regenerate_faq(
    request: Request,
    qa_group_id: str,
    body: dict[str, Any] = Body(default={}),
) -> Any:
    session = require_permission(request, "contentManagers")
    tenant_id = _session_tenant(session)
    raw_langs = body.get("languages")
    languages = [str(lang) for lang in raw_langs] if isinstance(raw_langs, list) else None
    try:
        result = await regenerate_cm_faq_variants(
            qa_group_id=qa_group_id,
            source_language=str(body["source_language"]) if body.get("source_language") else None,
            languages=languages,
            updated_by=_actor(session),
            tenant_id=tenant_id,
        )
    except FaqIntegrationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return result


@app.get("/api/cm/faq/smart-answer-languages")
async def cm_get_smart_answer_languages(request: Request) -> Any:
    session = require_permission(request, "contentManagers")
    tenant_id = _session_tenant(session)
    from services.cm.smart_answer_languages import smart_answer_languages_public

    return {"success": True, **smart_answer_languages_public(tenant_id=tenant_id)}


@app.put("/api/cm/faq/smart-answer-languages")
async def cm_put_smart_answer_languages(request: Request, body: dict[str, Any] = Body(default={})) -> Any:
    session = require_permission(request, "contentManagers")
    tenant_id = _session_tenant(session)
    raw = body.get("smart_answer_languages") or body.get("languages")
    if not isinstance(raw, list):
        raise HTTPException(status_code=400, detail="smart_answer_languages array is required")
    translate_existing = bool(body.get("translate_existing"))
    from services.cm.faq_integration import FaqIntegrationError, translate_existing_faq_groups_to_language
    from services.cm.smart_answer_languages import save_smart_answer_languages

    try:
        saved = save_smart_answer_languages(
            tenant_id=tenant_id,
            languages=[str(x) for x in raw],
            updated_by=_actor(session),
        )
    except FaqIntegrationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    batch: dict[str, Any] | None = None
    added = list(saved.get("added") or [])
    if translate_existing and added:
        batch_results = []
        for lang in added:
            batch_results.append(
                await translate_existing_faq_groups_to_language(
                    language=lang,
                    tenant_id=tenant_id,
                    updated_by=_actor(session),
                )
            )
        batch = {"languages": added, "results": batch_results}
    return {"success": True, **saved, "batch_translate": batch}


@app.delete("/api/cm/faq/smart-answer-languages/{language}")
async def cm_delete_smart_answer_language(request: Request, language: str) -> Any:
    """Remove a Smart Q&A language and permanently delete all saved Q&A for that language."""
    session = require_permission(request, "contentManagers")
    tenant_id = _session_tenant(session)
    from services.cm.faq_integration import FaqIntegrationError, purge_smart_answer_language_data

    try:
        result = purge_smart_answer_language_data(
            language=language,
            tenant_id=tenant_id,
            updated_by=_actor(session),
        )
    except FaqIntegrationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return result


@app.post("/api/cm/faq/smart-answer-languages/translate-existing")
async def cm_translate_existing_smart_answers(request: Request, body: dict[str, Any] = Body(default={})) -> Any:
    session = require_permission(request, "contentManagers")
    tenant_id = _session_tenant(session)
    language = str(body.get("language") or "").strip()
    if not language:
        raise HTTPException(status_code=400, detail="language is required")
    try:
        from services.cm.faq_integration import FaqIntegrationError, translate_existing_faq_groups_to_language

        result = await translate_existing_faq_groups_to_language(
            language=language,
            tenant_id=tenant_id,
            updated_by=_actor(session),
        )
    except FaqIntegrationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return result


@app.post("/api/cm/faq/{qa_group_id}/archive")
async def cm_archive_faq(request: Request, qa_group_id: str) -> Any:
    session = require_permission(request, "contentManagers")
    tenant_id = _session_tenant(session)
    try:
        return archive_cm_faq_group(
            qa_group_id=qa_group_id,
            updated_by=_actor(session),
            tenant_id=tenant_id,
        )
    except FaqIntegrationError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
