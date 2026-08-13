"""Durable Smart Follow-Up worker — claim and dispatch channel-routed jobs."""

from __future__ import annotations

import uuid
from typing import Any

from db.session import WhatsAppDatabaseUnavailable, whatsapp_session
from services.smart_followup.constants import WORKER_ID_PREFIX
from services.smart_followup.repository import SmartFollowUpRepository
from services.smart_followup.worker_job import process_one_followup_job


async def process_due_followup_jobs(*, limit: int = 25) -> dict[str, Any]:
    worker_id = f"{WORKER_ID_PREFIX}:{uuid.uuid4().hex[:10]}"
    try:
        with whatsapp_session() as session:
            repo = SmartFollowUpRepository(session)
            claimed = repo.claim_due_jobs(worker_id=worker_id, limit=limit)
            job_ids = [j.id for j in claimed]
    except WhatsAppDatabaseUnavailable:
        return {"processed": 0, "reason": "whatsapp_db_unavailable"}

    results: list[dict[str, Any]] = []
    for job_id in job_ids:
        result = await process_one_followup_job(job_id=job_id, worker_id=worker_id)
        results.append(result)

    return {"processed": len(results), "worker_id": worker_id, "results": results}
