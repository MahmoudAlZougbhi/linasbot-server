"""Repository for Customer Requests (tenant-scoped Postgres)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from db.models.requests import CustomerRequest, CustomerRequestCounter
from db.models.requests_support import (
    CustomerRequestEvent,
    CustomerRequestIdempotency,
    CustomerRequestNote,
    CustomerRequestOutbox,
)


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(UTC)


class CustomerRequestsRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def allocate_request_number(self, tenant_id: str) -> str:
        row = self.session.get(CustomerRequestCounter, tenant_id)
        if row is None:
            row = CustomerRequestCounter(tenant_id=tenant_id, next_number=2)
            self.session.add(row)
            self.session.flush()
            return "REQ-1"
        n = int(row.next_number)
        row.next_number = n + 1
        row.updated_at = _now()
        self.session.flush()
        return f"REQ-{n}"

    def get_idempotency(self, *, tenant_id: str, scope: str, key: str) -> CustomerRequestIdempotency | None:
        stmt = select(CustomerRequestIdempotency).where(
            CustomerRequestIdempotency.tenant_id == tenant_id,
            CustomerRequestIdempotency.scope == scope,
            CustomerRequestIdempotency.key == key,
        )
        return self.session.execute(stmt).scalar_one_or_none()

    def put_idempotency(
        self,
        *,
        tenant_id: str,
        scope: str,
        key: str,
        request_id: str | None,
        response_fingerprint: str | None = None,
    ) -> CustomerRequestIdempotency:
        row = CustomerRequestIdempotency(
            id=_uuid(),
            tenant_id=tenant_id,
            scope=scope,
            key=key,
            request_id=request_id,
            response_fingerprint=response_fingerprint,
        )
        self.session.add(row)
        self.session.flush()
        return row

    def create_request(self, **fields: Any) -> CustomerRequest:
        row = CustomerRequest(id=_uuid(), **fields)
        self.session.add(row)
        self.session.flush()
        return row

    def get_for_tenant(self, *, tenant_id: str, request_id: str) -> CustomerRequest | None:
        stmt = select(CustomerRequest).where(
            CustomerRequest.tenant_id == tenant_id,
            CustomerRequest.id == request_id,
        )
        return self.session.execute(stmt).scalar_one_or_none()

    def add_event(
        self,
        *,
        tenant_id: str,
        request_id: str,
        event_type: str,
        actor_kind: str,
        actor_user_id: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> CustomerRequestEvent:
        ev = CustomerRequestEvent(
            id=_uuid(),
            tenant_id=tenant_id,
            request_id=request_id,
            event_type=event_type,
            actor_kind=actor_kind,
            actor_user_id=actor_user_id,
            payload=payload,
        )
        self.session.add(ev)
        self.session.flush()
        return ev

    def add_note(self, *, tenant_id: str, request_id: str, author_user_id: str, body: str) -> CustomerRequestNote:
        note = CustomerRequestNote(
            id=_uuid(),
            tenant_id=tenant_id,
            request_id=request_id,
            author_user_id=author_user_id,
            body=body,
        )
        self.session.add(note)
        self.session.flush()
        return note

    def list_notes(self, *, tenant_id: str, request_id: str) -> list[CustomerRequestNote]:
        stmt = (
            select(CustomerRequestNote)
            .where(
                CustomerRequestNote.tenant_id == tenant_id,
                CustomerRequestNote.request_id == request_id,
            )
            .order_by(CustomerRequestNote.created_at.asc())
        )
        return list(self.session.execute(stmt).scalars().all())

    def list_events(self, *, tenant_id: str, request_id: str, limit: int = 100) -> list[CustomerRequestEvent]:
        stmt = (
            select(CustomerRequestEvent)
            .where(
                CustomerRequestEvent.tenant_id == tenant_id,
                CustomerRequestEvent.request_id == request_id,
            )
            .order_by(CustomerRequestEvent.created_at.asc())
            .limit(limit)
        )
        return list(self.session.execute(stmt).scalars().all())

    def enqueue_outbox(
        self,
        *,
        tenant_id: str,
        request_id: str,
        idempotency_key: str,
        channel: str,
        payload: dict[str, Any] | None,
    ) -> CustomerRequestOutbox:
        existing = self.session.execute(
            select(CustomerRequestOutbox).where(
                CustomerRequestOutbox.tenant_id == tenant_id,
                CustomerRequestOutbox.idempotency_key == idempotency_key,
            )
        ).scalar_one_or_none()
        if existing is not None:
            return existing
        row = CustomerRequestOutbox(
            id=_uuid(),
            tenant_id=tenant_id,
            request_id=request_id,
            idempotency_key=idempotency_key,
            channel=channel,
            payload=payload,
            status="pending",
        )
        self.session.add(row)
        self.session.flush()
        return row

    def list_pending_outbox(
        self,
        *,
        tenant_id: str | None = None,
        request_id: str | None = None,
        limit: int = 20,
    ) -> list[CustomerRequestOutbox]:
        lim = max(1, min(int(limit or 20), 100))
        clauses = [CustomerRequestOutbox.status == "pending"]
        if tenant_id:
            clauses.append(CustomerRequestOutbox.tenant_id == tenant_id)
        if request_id:
            clauses.append(CustomerRequestOutbox.request_id == request_id)
        stmt = (
            select(CustomerRequestOutbox)
            .where(and_(*clauses))
            .order_by(CustomerRequestOutbox.created_at.asc())
            .limit(lim)
        )
        return list(self.session.execute(stmt).scalars().all())

    def get_outbox(self, *, tenant_id: str, outbox_id: str) -> CustomerRequestOutbox | None:
        row = self.session.get(CustomerRequestOutbox, outbox_id)
        if row is None or row.tenant_id != tenant_id:
            return None
        return row

    def list_requests(
        self,
        *,
        tenant_id: str,
        request_type: str | None = None,
        status: str | None = None,
        source_channel: str | None = None,
        assigned_user_id: str | None = None,
        q: str | None = None,
        created_before: datetime | None = None,
        limit: int = 25,
    ) -> list[CustomerRequest]:
        clauses = [CustomerRequest.tenant_id == tenant_id]
        if request_type:
            clauses.append(CustomerRequest.request_type == request_type)
        if status:
            clauses.append(CustomerRequest.status == status)
        if source_channel:
            clauses.append(CustomerRequest.source_channel == source_channel)
        if assigned_user_id:
            clauses.append(CustomerRequest.assigned_user_id == assigned_user_id)
        if created_before is not None:
            clauses.append(CustomerRequest.created_at < created_before)
        if q:
            like = f"%{q.strip()}%"
            clauses.append(
                or_(
                    CustomerRequest.request_number.ilike(like),
                    CustomerRequest.customer_name.ilike(like),
                    CustomerRequest.customer_display_name.ilike(like),
                    CustomerRequest.platform_username.ilike(like),
                    CustomerRequest.phone_normalized.ilike(like),
                    CustomerRequest.title.ilike(like),
                )
            )
        stmt = select(CustomerRequest).where(and_(*clauses)).order_by(CustomerRequest.created_at.desc()).limit(limit)
        return list(self.session.execute(stmt).scalars().all())

    def status_counts(self, *, tenant_id: str) -> dict[str, int]:
        from sqlalchemy import func

        stmt = (
            select(CustomerRequest.status, func.count())
            .where(CustomerRequest.tenant_id == tenant_id)
            .group_by(CustomerRequest.status)
        )
        return {str(status): int(count) for status, count in self.session.execute(stmt).all()}
