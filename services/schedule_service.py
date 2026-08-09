"""Generic content scheduling engine."""

from __future__ import annotations

import json
import threading
import time
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Literal

from services.entitlements_service import assert_feature
from services.job_queue import job_queue
from storage.persistent_storage import _DATA_ROOT

ScheduleStatus = Literal["draft", "scheduled", "publishing", "published", "failed", "canceled"]


@dataclass
class ScheduledPost:
    id: str
    tenant_id: str
    connected_account: str
    platform: str
    content_asset: dict[str, Any]
    scheduled_at: float
    timezone: str
    status: ScheduleStatus
    retries: int
    failure_reason: str | None
    provider_result_id: str | None
    created_at: float
    updated_at: float
    idempotency_key: str


class ScheduleService:
    def __init__(self, root: Path | None = None) -> None:
        self._lock = threading.RLock()
        self._root = root or (Path(_DATA_ROOT) / "scheduled_posts")
        self._root.mkdir(parents=True, exist_ok=True)

    def _path(self, tenant_id: str, post_id: str) -> Path:
        d = self._root / tenant_id
        d.mkdir(parents=True, exist_ok=True)
        return d / f"{post_id}.json"

    def create(
        self,
        *,
        tenant_id: str,
        connected_account: str,
        platform: str,
        content_asset: dict[str, Any],
        scheduled_at: float,
        timezone: str,
        idempotency_key: str,
    ) -> ScheduledPost:
        assert_feature(tenant_id, "scheduling")
        # Idempotency
        for existing in self.list_for_tenant(tenant_id):
            if existing.idempotency_key == idempotency_key:
                return existing
        now = time.time()
        post = ScheduledPost(
            id=uuid.uuid4().hex,
            tenant_id=tenant_id,
            connected_account=connected_account,
            platform=platform,
            content_asset=content_asset,
            scheduled_at=scheduled_at,
            timezone=timezone or "UTC",
            status="scheduled",
            retries=0,
            failure_reason=None,
            provider_result_id=None,
            created_at=now,
            updated_at=now,
            idempotency_key=idempotency_key,
        )
        with self._lock:
            self._path(tenant_id, post.id).write_text(json.dumps(asdict(post)), encoding="utf-8")
        job_queue.enqueue(
            queue="background",
            job_type="publish_scheduled",
            tenant_id=tenant_id,
            payload={"scheduled_post_id": post.id},
            idempotency_key=idempotency_key or f"schedule:{post.id}",
        )
        return post

    def list_for_tenant(self, tenant_id: str) -> list[ScheduledPost]:
        d = self._root / tenant_id
        if not d.is_dir():
            return []
        items: list[ScheduledPost] = []
        for path in d.glob("*.json"):
            try:
                items.append(ScheduledPost(**json.loads(path.read_text(encoding="utf-8"))))
            except Exception:
                continue
        items.sort(key=lambda p: p.scheduled_at)
        return items

    def cancel(self, *, tenant_id: str, post_id: str) -> ScheduledPost | None:
        path = self._path(tenant_id, post_id)
        with self._lock:
            if not path.is_file():
                return None
            post = ScheduledPost(**json.loads(path.read_text(encoding="utf-8")))
            if post.status in {"published", "publishing"}:
                raise PermissionError("Cannot cancel a post that is publishing/published")
            post.status = "canceled"
            post.updated_at = time.time()
            path.write_text(json.dumps(asdict(post)), encoding="utf-8")
            return post


schedule_service = ScheduleService()
