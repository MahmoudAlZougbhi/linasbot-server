"""Tenant-scoped persistence for customer request drafts."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from db.models.request_drafts import CustomerRequestDraft

OPEN_STATUSES = ("collecting", "paused", "ready")


def _uuid() -> str:
    return str(uuid.uuid4())


class DraftRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get(self, *, tenant_id: str, draft_id: str) -> CustomerRequestDraft | None:
        stmt = select(CustomerRequestDraft).where(
            CustomerRequestDraft.tenant_id == tenant_id,
            CustomerRequestDraft.draft_id == draft_id,
        )
        return self.session.execute(stmt).scalars().first()

    def list_open(self, *, tenant_id: str, customer_id: str) -> list[CustomerRequestDraft]:
        if not customer_id:
            return []
        stmt = (
            select(CustomerRequestDraft)
            .where(
                CustomerRequestDraft.tenant_id == tenant_id,
                CustomerRequestDraft.customer_id == customer_id,
                CustomerRequestDraft.status.in_(OPEN_STATUSES),
            )
            .order_by(CustomerRequestDraft.created_at.asc())
        )
        return list(self.session.execute(stmt).scalars().all())

    def list_for_definition(self, *, tenant_id: str, definition_id: str) -> list[CustomerRequestDraft]:
        stmt = select(CustomerRequestDraft).where(
            CustomerRequestDraft.tenant_id == tenant_id,
            CustomerRequestDraft.definition_id == definition_id,
        )
        return list(self.session.execute(stmt).scalars().all())

    def insert(self, **kwargs: Any) -> CustomerRequestDraft:
        row = CustomerRequestDraft(id=_uuid(), **kwargs)
        self.session.add(row)
        self.session.flush()
        return row
