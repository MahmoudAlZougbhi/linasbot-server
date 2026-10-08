"""Portal APIs for owner knowledge, Q&A, traces, audit, and health."""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import HTTPException, Query, Request
from pydantic import BaseModel, Field

from modules.api_security import require_platform_owner
from modules.core import app


class KbBody(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    body: str = Field(min_length=1, max_length=8000)
    id: str | None = None


class QaVariant(BaseModel):
    language: str
    question: str = ""
    answer: str = ""


class QaBody(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    answer: str = Field(min_length=1, max_length=8000)
    source_language: str = "en"


def _langs() -> tuple[str, ...]:
    return ("ar", "en", "fr", "franco")


async def _variants(body: QaBody) -> list[dict[str, str]]:
    source = body.source_language if body.source_language in _langs() else "en"
    variants = {source: {"language": source, "question": body.question.strip(), "answer": body.answer.strip()}}
    try:
        from services.brain.language_detection_service import language_detection_service
        from services.owner_portal.protected_text import translate_kept

        async def _one(language: str) -> tuple[str, str, str]:
            async def _translate(text: str, attempt: int) -> str:
                payload = text
                if attempt > 1:
                    payload = f"{text}\nKeep every placeholder exactly as written."
                rendered = await language_detection_service.translate_answer_text(
                    payload, source_language=source, target_language=language
                )
                return str(rendered or "")

            question, _tries = await translate_kept(body.question, target=language, translate=_translate)
            answer, _tries = await translate_kept(body.answer, target=language, translate=_translate)
            return language, question, answer

        targets = [language for language in ("ar", "fr") if language != source]
        for language, question, answer in await asyncio.gather(*[_one(language) for language in targets]):
            variants[language] = {"language": language, "question": question, "answer": answer}
    except Exception:
        pass
    for language in _langs():
        if language == "franco":
            continue
        variants.setdefault(
            language,
            {"language": language, "question": body.question.strip(), "answer": body.answer.strip()},
        )
    from services.owner_portal.franco import franco_pair

    question, answer = await franco_pair(body.question.strip(), body.answer.strip())
    variants["franco"] = {"language": "franco", "question": question, "answer": answer}
    return list(variants.values())


@app.get("/api/platform/copilot/knowledge")
async def list_knowledge(request: Request) -> Any:
    require_platform_owner(request)
    from services.owner_portal.owner_kb_store import list_entries

    return {"success": True, "entries": list_entries()}


@app.post("/api/platform/copilot/knowledge")
async def save_knowledge(body: KbBody, request: Request) -> Any:
    require_platform_owner(request)
    from services.owner_portal.owner_kb_store import save_entry

    try:
        entry = await asyncio.to_thread(save_entry, title=body.title, body=body.body, entry_id=body.id)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return {"success": True, "entry": entry}


@app.delete("/api/platform/copilot/knowledge/{entry_id}")
async def remove_knowledge(entry_id: str, request: Request) -> Any:
    require_platform_owner(request)
    from services.owner_portal.owner_kb_store import delete_entry

    await asyncio.to_thread(delete_entry, entry_id)
    return {"success": True}


@app.get("/api/platform/copilot/qa")
async def list_saved_qa(request: Request) -> Any:
    require_platform_owner(request)
    from services.owner_portal.owner_qa import list_qa

    return {"success": True, "items": list_qa()}


@app.post("/api/platform/copilot/qa")
async def save_saved_qa(body: QaBody, request: Request) -> Any:
    require_platform_owner(request)
    from services.owner_portal.owner_qa import save_qa

    try:
        variants = await _variants(body)
        qa_id = await asyncio.to_thread(save_qa, variants=variants, source_language=body.source_language)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return {"success": True, "id": qa_id}


@app.delete("/api/platform/copilot/qa/{qa_id}")
async def delete_saved_qa(qa_id: str, request: Request) -> Any:
    session = require_platform_owner(request)
    from services.owner_portal.owner_qa import delete_qa
    from services.team.platform_owner_service import platform_owner_service

    if not await asyncio.to_thread(delete_qa, qa_id):
        raise HTTPException(status_code=404, detail="qa_not_found")
    platform_owner_service.log_action(
        actor_user_id=session.user_id,
        action="copilot_qa_delete",
        tenant_id="platform",
        details={"qa_id": qa_id},
    )
    return {"success": True}


@app.get("/api/platform/copilot/traces")
async def list_portal_traces(
    request: Request,
    tenant_id: str = Query(default=""),
    brain: str = Query(default=""),
    channel: str = Query(default=""),
    has_error: bool | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> Any:
    require_platform_owner(request)
    from services.owner_portal.owner_traces import list_traces

    return {
        "success": True,
        "traces": list_traces(
            tenant_id=tenant_id.strip(),
            brain=brain.strip(),
            channel=channel.strip(),
            has_error=has_error,
            limit=limit,
            offset=offset,
        ),
    }


@app.get("/api/platform/copilot/traces/{trace_id}")
async def portal_trace(trace_id: str, request: Request) -> Any:
    require_platform_owner(request)
    from services.owner_portal.owner_traces import get_trace

    row = get_trace(trace_id)
    if row is None:
        raise HTTPException(status_code=404, detail="trace_not_found")
    return {"success": True, "trace": row}


@app.get("/api/platform/audit")
async def portal_audit(request: Request) -> Any:
    require_platform_owner(request)
    from services.owner_portal.audit_feed import merged_audit_events

    return {"success": True, "events": merged_audit_events()}


@app.get("/api/platform/version")
async def portal_version(request: Request) -> Any:
    require_platform_owner(request)
    from services.owner_portal.release_version import version_payload

    return {"success": True, "version": version_payload()}


@app.get("/api/platform/health")
async def portal_health(request: Request) -> Any:
    require_platform_owner(request)
    from db.session import ping_whatsapp_db

    db = ping_whatsapp_db()
    return {"success": True, "database": db, "api": "ok"}
