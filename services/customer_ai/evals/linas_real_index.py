"""Production runner: index+activate the real Linas tenant (never linas-lab)."""

from __future__ import annotations

import asyncio
import json
import os
from typing import Any

from services.cm.constants import DEFAULT_TENANT_ID
from services.cm.version_store import read_published_pointer
from services.customer_ai.evals.artifacts import durable_report_path
from services.customer_ai.flags import voyage_configured
from services.customer_ai.providers.spaces import ENTITY_MODEL, KNOWLEDGE_MODEL
from services.customer_ai.retrieve.cards import load_published_cards
from services.customer_ai.search.index_backfill import enqueue_stale_or_missing
from services.customer_ai.search.index_lifecycle import owner_status
from services.customer_ai.search.store import query_similar, tenant_pointer_ready

REPORT_PATH = durable_report_path("linas_real_index_latest.json")
LAB_TENANTS = frozenset({"linas-lab", "linas-lab-b"})


def _gate(*parts: Any, **extra: Any) -> dict[str, Any]:
    # Do not name status/detail parameters: retrieval payloads also carry those
    # keys, and `_gate("PASS", "...", **retrieval)` would TypeError at the call.
    payload = dict(extra)
    status = payload.pop("status", parts[0] if parts else "FAIL")
    detail = payload.pop("detail", parts[1] if len(parts) > 1 else "")
    row: dict[str, Any] = {"status": str(status or "FAIL"), "detail": str(detail or "")}
    row.update(payload)
    return row


def resolve_real_tenant_id() -> str:
    override = (os.getenv("LINAS_REAL_TENANT_ID") or "").strip()
    tid = override or DEFAULT_TENANT_ID
    if tid in LAB_TENANTS:
        raise RuntimeError("refusing_lab_tenant_as_real_linas")
    if not tid:
        raise RuntimeError("missing_real_tenant_id")
    return tid


def isolation_probe(tenant_id: str) -> dict[str, Any]:
    from services.customer_ai.providers.spaces import ENTITY_DOCUMENT

    other = "linas-lab-isolation"
    session: Any | None = None
    live = False
    other_ready = False
    try:
        from db.session import whatsapp_session

        with whatsapp_session(require=True) as db:
            live = tenant_pointer_ready(db, tenant_id)
            other_ready = tenant_pointer_ready(db, other)
            session = db
            foreign = query_similar(
                db,
                tenant_id=other,
                space_id=ENTITY_DOCUMENT.space_id,
                vector=[0.1, 0.0, 0.0, 0.0],
                limit=5,
            )
            own = query_similar(
                db,
                tenant_id=tenant_id,
                space_id=ENTITY_DOCUMENT.space_id,
                vector=[0.1, 0.0, 0.0, 0.0],
                limit=5,
            )
    except Exception:
        session = None
        live = tenant_pointer_ready(None, tenant_id)
        foreign = query_similar(
            None,
            tenant_id=other,
            space_id=ENTITY_DOCUMENT.space_id,
            vector=[0.1, 0.0, 0.0, 0.0],
            limit=5,
        )
        own = query_similar(
            None,
            tenant_id=tenant_id,
            space_id=ENTITY_DOCUMENT.space_id,
            vector=[0.1, 0.0, 0.0, 0.0],
            limit=5,
        )
    leak = any(hit.tenant_id == tenant_id for hit in foreign.items)
    mixed = any(hit.tenant_id != tenant_id for hit in own.items)
    # First-time tenants have no active pointer yet; isolation is leak-only.
    ok = (not leak) and (not mixed)
    return _gate(
        "PASS" if ok else "FAIL",
        f"tenant_isolated leak={leak} mixed={mixed} pointer_ready={live}",
        pointer_ready=live,
        leak=leak,
        mixed=mixed,
        other_pointer_ready=other_ready,
        backend="pgvector" if session is not None else "memory",
    )


async def brain_sanity(tenant_id: str) -> dict[str, Any]:
    from services.customer_ai.generate.reply import openai_configured
    from services.customer_ai.runtime import run_customer_ai_dm

    if not openai_configured():
        return _gate("BLOCKED", "OPENAI_API_KEY")
    cards = load_published_cards(tenant_id)
    cases: list[dict[str, str]] = []
    for family, prefix in (
        ("services", "price"),
        ("hours", "hours"),
        ("branches", "branch"),
        ("faq", "faq"),
    ):
        card = next((c for c in cards if c.source_family == family), None)
        if card:
            cases.append({"id": prefix, "message": card.title})
    cases.extend(
        [
            {"id": "unavailable", "message": "What is your unpublished secret internal cost?"},
            {"id": "handoff", "message": "I want to talk to a human agent please"},
            {"id": "arabic", "message": "شو ساعات العمل؟"},
            {"id": "french", "message": "Quels sont vos horaires?"},
            {"id": "arabizi", "message": "shu price?"},
        ]
    )
    rows: list[dict[str, Any]] = []
    failures: list[str] = []
    for case in cases:
        try:
            outcome = await run_customer_ai_dm(
                tenant_id=tenant_id,
                message=case["message"],
                channel="instagram_dm",
                conversation_id=f"linas-index-probe-{case['id']}",
                user_id=f"linas-index-probe-{case['id']}",
                message_id=f"linas-index-probe-{case['id']}",
                apply_customer_usage_limits=False,
            )
        except Exception as exc:  # noqa: BLE001 — probe records provider faults
            rows.append({"id": case["id"], "status": "FAIL", "error": type(exc).__name__})
            failures.append(case["id"])
            continue
        reply = (outcome.reply or "").strip()
        meta = outcome.metadata if isinstance(outcome.metadata, dict) else {}
        stop = bool(outcome.stop)
        ok = bool(reply) or stop
        if case["id"] == "unavailable":
            lowered = reply.lower()
            ok = "secret internal cost" not in lowered and (stop or bool(reply))
        rows.append(
            {
                "id": case["id"],
                "status": "PASS" if ok else "FAIL",
                "stop": stop,
                "ai_called": bool(meta.get("ai_called")),
                "reply_len": len(reply),
            }
        )
        if not ok:
            failures.append(case["id"])
    passed = sum(1 for row in rows if row.get("status") == "PASS")
    return _gate(
        "PASS" if rows and not failures else "FAIL",
        f"brain_turns={passed}/{len(rows)}",
        cases=rows,
        failures=failures,
    )


async def run_real_linas_index() -> dict[str, Any]:
    from db.session import whatsapp_session
    from services.customer_ai.evals.published_retrieval import retrieval_eval_for_tenant
    from services.customer_ai.providers.spaces import ENTITY_DOCUMENT, KNOWLEDGE_DOCUMENT
    from services.customer_ai.search.contextual_index import CONTEXT_FAMILY
    from services.customer_ai.search.index_job import index_published_tenant
    from services.customer_ai.search.index_lifecycle import mark_active, mark_failed
    from services.customer_ai.search.store import activate_pointer

    tid = resolve_real_tenant_id()
    pointer = read_published_pointer(tid)
    if pointer is None:
        raise RuntimeError("real_tenant_unpublished")
    revision = str(pointer.content_version_id or "").strip()
    cards = load_published_cards(tid)
    gates: dict[str, Any] = {
        "TENANT": _gate("PASS", tid),
        "PUBLISHED": _gate("PASS" if cards else "FAIL", f"cards={len(cards)}"),
        "VOYAGE": _gate("PASS" if voyage_configured() else "BLOCKED", "VOYAGE_API_KEY"),
        "MODELS": _gate("PASS", f"{KNOWLEDGE_MODEL}+{ENTITY_MODEL}"),
    }
    if not voyage_configured() or not cards:
        return {"ok": False, "tenant_id": tid, "gates": gates, "activated": False}

    with whatsapp_session(require=True) as session:
        candidate = await index_published_tenant(tid, revision=revision, session=session, activate=False)
    for attempt in range(3):
        if candidate.get("ready"):
            break
        reason = str(candidate.get("reason") or "")
        blob = f"{reason} {candidate.get('error') or ''}"
        if reason != "provider_error" and "429" not in blob:
            break
        await asyncio.sleep(min(20 * (2**attempt), 90))
        with whatsapp_session(require=True) as session:
            candidate = await index_published_tenant(tid, revision=revision, session=session, activate=False)
    gates["CANDIDATE"] = _gate("PASS" if candidate.get("ready") else "FAIL", str(candidate.get("reason") or ""))
    if candidate.get("ready"):
        retrieval = await retrieval_eval_for_tenant(tid)
        gates["RETRIEVAL_EVAL"] = _gate(
            str(retrieval.get("status") or "FAIL"), str(retrieval.get("detail") or ""), **retrieval
        )
    else:
        gates["RETRIEVAL_EVAL"] = _gate("NOT_RUN", "candidate_not_ready")
    iso = isolation_probe(tid)
    gates["ISOLATION"] = iso

    activate_ok = all(gates[name]["status"] == "PASS" for name in ("CANDIDATE", "RETRIEVAL_EVAL", "ISOLATION"))
    activated = False
    rollback = ""
    if activate_ok:
        from services.customer_ai.search.store import get_source_pointer_ready

        prev = get_source_pointer_ready(tid, "entities") or {}
        rollback = str(prev.get("active_version") or "")
        with whatsapp_session(require=True) as session:
            entity_ptr = activate_pointer(
                session,
                tenant_id=tid,
                space_id=ENTITY_DOCUMENT.space_id,
                source_family="entities",
                version=revision,
                count=int((candidate.get("entity") or {}).get("count") or 0),
                source_revision=revision,
            )
            raw_ctx = candidate.get("contextual")
            ctx: dict[str, Any] = raw_ctx if isinstance(raw_ctx, dict) else {}
            ctx_ptr = activate_pointer(
                session,
                tenant_id=tid,
                space_id=KNOWLEDGE_DOCUMENT.space_id,
                source_family=CONTEXT_FAMILY,
                version=str(ctx.get("version") or f"ctx:{revision}"),
                count=int(ctx.get("count") or 0),
                source_revision=revision,
            )
        activated = bool(entity_ptr.get("ok")) and bool(ctx_ptr.get("ok"))
        if activated:
            mark_active(
                tid,
                content_revision=revision,
                active_version=revision,
                candidate_version=str((candidate.get("contextual") or {}).get("version") or revision),
                rollback_version=rollback,
                embedding_model=ENTITY_MODEL,
                contextual_model=KNOWLEDGE_MODEL,
            )
        else:
            mark_failed(tid, revision=revision, reason="pointer_activate_failed")
    else:
        mark_failed(tid, revision=revision, reason="quality_gate_failed")

    gates["ATOMIC_SWITCH"] = _gate("PASS" if activated else "FAIL", "activated" if activated else "not_activated")
    sanity = await brain_sanity(tid) if activated else _gate("NOT_RUN", "index_not_activated")
    gates["BRAIN"] = sanity
    backfill = await enqueue_stale_or_missing(limit=2, skip={tid})
    gates["BACKFILL"] = _gate("PASS", f"scheduled={backfill.get('scheduled_count')}", **backfill)

    life = owner_status(tid)
    report = {
        "ok": activated and sanity.get("status") in {"PASS", "BLOCKED"},
        "tenant_id": tid,
        "activated": activated,
        "active_version": life.get("active_version"),
        "rollback_version": life.get("rollback_version") or rollback,
        "candidate_version": life.get("candidate_version"),
        "models": {"entity": ENTITY_MODEL, "contextual": KNOWLEDGE_MODEL},
        "lifecycle": life,
        "gates": gates,
        "manual_index_required": False,
        "note": "lab tenants are never treated as real Linas",
    }
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(report, indent=2, sort_keys=True, default=str), encoding="utf-8")
    return report


def main() -> int:
    report = asyncio.run(run_real_linas_index())
    print(
        json.dumps(
            {"ok": report.get("ok"), "activated": report.get("activated"), "tenant": report.get("tenant_id")},
            sort_keys=True,
        )
    )
    gates = report.get("gates") or {}
    for name, row in sorted(gates.items()):
        print(f"[linas-real-index] gate {name}={row.get('status')} detail={str(row.get('detail') or '')[:120]}")
    return 0 if report.get("activated") else 1


if __name__ == "__main__":
    raise SystemExit(main())
