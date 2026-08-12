"""FAQ correction endpoints from Live Chat (LOC split from local_qa_api).

SEC-041: require liveChat (or contentManagers) + tenant scope. Writes go through
canonical CM FAQ integration so multi-language saves cannot cross tenants.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import Body, HTTPException, Request

from modules.api_security import require_permission
from modules.core import app
from modules.local_qa_api_helpers import (
    _answer_in_arabic_script,
    _translate_to_arabic_script,
    read_qa_pairs,
    reload_local_qa_cache,
    write_qa_pairs,
)
from services.dashboard_session_service import SessionRecord
from services.language_detection_service import language_detection_service


def _session_tenant(session: SessionRecord) -> str:
    tenant_id = str(session.tenant_id or "").strip()
    if not tenant_id:
        raise HTTPException(status_code=403, detail="Tenant context required")
    return tenant_id


def _require_faq_write_session(request: Request) -> SessionRecord:
    """Live Chat FAQ correction requires liveChat permission."""
    return require_permission(request, "liveChat")


def _actor(session: SessionRecord) -> str:
    return getattr(session, "user_id", None) or getattr(session, "email", None) or "operator"


def _faq_row_tenant(row: dict[str, Any]) -> str:
    return str(row.get("tenant_id") or row.get("tenantId") or "").strip().lower()


def _assert_faq_row_writable(row: dict[str, Any], *, tenant_id: str) -> None:
    """Reject cross-tenant FAQ mutations (save-all-languages must stay scoped)."""
    row_tenant = _faq_row_tenant(row)
    tid = tenant_id.strip().lower()
    qa_group_id = str(row.get("qa_group_id") or "").strip()

    if row_tenant and row_tenant != tid:
        raise HTTPException(status_code=403, detail="FAQ entry belongs to another tenant")

    # Prefer CM draft membership as the source of truth for tenant-scoped groups.
    if qa_group_id:
        from services.cm.faq_integration import get_cm_faq_group

        owned = get_cm_faq_group(qa_group_id=qa_group_id, tenant_id=tid)
        if owned is not None:
            return
        # Group exists for another tenant's draft → deny.
        # Legacy linas rows without tenant_id / CM mirror: allow only for linas.
        if row_tenant == tid:
            return
        if not row_tenant and tid == "linas":
            return
        raise HTTPException(status_code=403, detail="FAQ entry not found for tenant")
    if not row_tenant and tid != "linas":
        raise HTTPException(status_code=403, detail="FAQ entry not found for tenant")


# ---------- FAQ Correction Workflow (Live Chat Dislike) ----------


@app.post("/api/faq/update-answer")
async def faq_update_answer(request: Request, body: dict = Body(default={})) -> Any:
    """
    Update an existing FAQ entry's answer (e.g. from Live Chat dislike → Save Change).
    Body: { faq_id, new_answer_text, updated_by, source }.
    Answer is stored in Arabic; all rows with same qa_group_id get the same Arabic answer.
    Requires liveChat + tenant scope (SEC-041).
    """
    session = _require_faq_write_session(request)
    tenant_id = _session_tenant(session)
    try:
        faq_id = body.get("faq_id")
        new_answer_text = (body.get("new_answer_text") or "").strip()
        updated_by = body.get("updated_by") or _actor(session)
        source = body.get("source") or "live_chat_dislike"
        if not new_answer_text:
            return {"success": False, "error": "new_answer_text is required"}
        if faq_id is None:
            return {"success": False, "error": "faq_id is required"}

        qa_id = (
            int(faq_id)
            if isinstance(faq_id, str) and str(faq_id).isdigit()
            else (int(faq_id) if isinstance(faq_id, int) else None)
        )
        if qa_id is None or qa_id < 1:
            return {"success": False, "error": "Invalid faq_id"}

        qa_pairs = read_qa_pairs()
        if qa_id > len(qa_pairs):
            return {"success": False, "error": f"FAQ entry {faq_id} not found"}

        row = qa_pairs[qa_id - 1]
        _assert_faq_row_writable(row, tenant_id=tenant_id)

        qa_group_id = row.get("qa_group_id")
        detected_language = language_detection_service.normalize_training_language(row.get("language"), default="ar")
        answer_ar = new_answer_text
        if not _answer_in_arabic_script(answer_ar):
            answer_ar = await _translate_to_arabic_script(answer_ar, detected_language)
            if not _answer_in_arabic_script(answer_ar):
                answer_ar = await _translate_to_arabic_script(answer_ar, "franco")

        now = datetime.now().isoformat()
        for qa in qa_pairs:
            same_group = bool(qa_group_id) and qa.get("qa_group_id") == qa_group_id
            same_row = not qa_group_id and qa is row
            if not (same_group or same_row):
                continue
            # Do not mutate another tenant's linked rows even if qa_group_id collides.
            other_tid = _faq_row_tenant(qa)
            if other_tid and other_tid != tenant_id.strip().lower():
                continue
            qa["answer"] = answer_ar
            qa["updated_at"] = now
            qa["updated_by"] = updated_by
            qa["source"] = source
            qa["tenant_id"] = tenant_id.strip().lower()

        if write_qa_pairs(qa_pairs):
            reload_local_qa_cache()
            # Mirror into CM draft for all languages when the group is known to this tenant.
            if qa_group_id:
                try:
                    from services.cm.faq_integration import FaqIntegrationError, update_cm_faq_variant
                    from services.cm.faq_integration_helpers import FAQ_TARGET_LANGUAGES

                    for lang in FAQ_TARGET_LANGUAGES:
                        try:
                            await update_cm_faq_variant(
                                qa_group_id=str(qa_group_id),
                                language=lang,
                                answer=answer_ar,
                                updated_by=updated_by,
                                tenant_id=tenant_id,
                            )
                        except FaqIntegrationError:
                            continue
                except Exception as mirror_exc:
                    print(f"⚠️ CM FAQ mirror after update-answer failed: {mirror_exc}")
            return {
                "success": True,
                "message": "FAQ answer updated",
                "faq_id": qa_id,
                "updated_at": now,
                "updated_by": updated_by,
                "tenant_id": tenant_id,
            }
        return {"success": False, "error": "Failed to write Q&A file"}
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Error in faq_update_answer: {e}")
        import traceback

        traceback.print_exc()
        return {"success": False, "error": str(e)}


@app.post("/api/faq/create-from-livechat")
async def faq_create_from_livechat(request: Request, body: dict = Body(default={})) -> Any:
    """
    Create a new FAQ entry from Live Chat dislike → Save New (all languages).
    Requires liveChat + tenant scope; writes via canonical CM FAQ (SEC-041).
    """
    session = _require_faq_write_session(request)
    tenant_id = _session_tenant(session)
    try:
        question_text = (body.get("question_text") or "").strip()
        answer_text = (body.get("answer_text") or "").strip()
        question_language = body.get("question_language") or "ar"
        created_by = body.get("created_by") or _actor(session)
        source = body.get("source") or "live_chat_dislike"

        if not question_text or not answer_text:
            return {"success": False, "error": "question_text and answer_text are required"}

        from services.cm.faq_integration import FaqIntegrationError, create_faq_pair_from_livechat
        from services.faq_entitlements import FaqEntitlementError, assert_can_create_faq

        try:
            assert_can_create_faq(tenant_id)
        except FaqEntitlementError as exc:
            status = 403 if exc.code == "FAQ_DISABLED" else 402
            raise HTTPException(status_code=status, detail={"code": exc.code, **exc.payload}) from exc

        try:
            result = await create_faq_pair_from_livechat(
                question=question_text,
                answer=answer_text,
                language=question_language,
                updated_by=created_by,
                publish=False,
                tenant_id=tenant_id,
            )
        except FaqIntegrationError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

        return {
            "success": True,
            "message": "New FAQ entry created",
            "created_entries": result.get("created_entries") or [],
            "count_created": result.get("count_created", 0),
            "qa_group_id": result.get("qa_group_id"),
            "created_by": created_by,
            "source": source,
            "tenant_id": tenant_id,
            "duplicates": result.get("duplicates") or [],
        }
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Error in faq_create_from_livechat: {e}")
        import traceback

        traceback.print_exc()
        return {"success": False, "error": str(e)}
