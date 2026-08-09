"""Queue job models."""

from __future__ import annotations

import time
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class QueueJob:
    id: str
    queue: str
    job_type: str
    tenant_id: str
    payload: dict[str, Any]
    status: str
    created_at: float
    attempts: int = 0
    max_attempts: int = 5
    last_error: str | None = None
    idempotency_key: str | None = None
    reservation_id: str | None = None
    timeout_seconds: int = 300
    available_at: float = 0.0
    updated_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> QueueJob:
        return cls(
            id=str(data["id"]),
            queue=str(data["queue"]),
            job_type=str(data["job_type"]),
            tenant_id=str(data["tenant_id"]),
            payload=dict(data.get("payload") or {}),
            status=str(data.get("status") or "queued"),
            created_at=float(data.get("created_at") or time.time()),
            attempts=int(data.get("attempts") or 0),
            max_attempts=int(data.get("max_attempts") or 5),
            last_error=data.get("last_error"),
            idempotency_key=data.get("idempotency_key"),
            reservation_id=data.get("reservation_id"),
            timeout_seconds=int(data.get("timeout_seconds") or 300),
            available_at=float(data.get("available_at") or 0.0),
            updated_at=float(data.get("updated_at") or time.time()),
        )

    @classmethod
    def new(
        cls,
        *,
        queue: str,
        job_type: str,
        tenant_id: str,
        payload: dict[str, Any],
        idempotency_key: str | None = None,
        reservation_id: str | None = None,
        max_attempts: int = 5,
        timeout_seconds: int = 300,
    ) -> QueueJob:
        now = time.time()
        return cls(
            id=uuid.uuid4().hex,
            queue=queue,
            job_type=job_type,
            tenant_id=tenant_id,
            payload=payload,
            status="queued",
            created_at=now,
            updated_at=now,
            attempts=0,
            max_attempts=max_attempts,
            idempotency_key=idempotency_key,
            reservation_id=reservation_id,
            timeout_seconds=timeout_seconds,
            available_at=now,
        )
