"""Tenant-scoped persistence for request definition graphs."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.orm import Session, selectinload

from db.models.request_graphs import RequestDefinitionGraph, RequestDefinitionLink


def _uuid() -> str:
    return str(uuid.uuid4())


class RequestGraphRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_active_by_source(self, *, tenant_id: str, source_item_id: str) -> RequestDefinitionGraph | None:
        stmt = (
            select(RequestDefinitionGraph)
            .where(
                RequestDefinitionGraph.tenant_id == tenant_id,
                RequestDefinitionGraph.source_item_id == source_item_id,
                RequestDefinitionGraph.status == "active",
            )
            .options(selectinload(RequestDefinitionGraph.links))
            .order_by(RequestDefinitionGraph.revision.desc())
        )
        return self.session.execute(stmt).scalars().first()

    def get_by_definition(
        self, *, tenant_id: str, definition_id: str, revision: int | None = None
    ) -> RequestDefinitionGraph | None:
        filters = [
            RequestDefinitionGraph.tenant_id == tenant_id,
            RequestDefinitionGraph.definition_id == definition_id,
        ]
        if revision is not None:
            filters.append(RequestDefinitionGraph.revision == revision)
        stmt = (
            select(RequestDefinitionGraph)
            .where(*filters)
            .options(selectinload(RequestDefinitionGraph.links))
            .order_by(RequestDefinitionGraph.revision.desc())
        )
        return self.session.execute(stmt).scalars().first()

    def get_active_by_definition(self, *, tenant_id: str, definition_id: str) -> RequestDefinitionGraph | None:
        stmt = (
            select(RequestDefinitionGraph)
            .where(
                RequestDefinitionGraph.tenant_id == tenant_id,
                RequestDefinitionGraph.definition_id == definition_id,
                RequestDefinitionGraph.status == "active",
            )
            .options(selectinload(RequestDefinitionGraph.links))
            .order_by(RequestDefinitionGraph.revision.desc())
        )
        return self.session.execute(stmt).scalars().first()

    def list_active(self, *, tenant_id: str) -> list[RequestDefinitionGraph]:
        stmt = (
            select(RequestDefinitionGraph)
            .where(RequestDefinitionGraph.tenant_id == tenant_id, RequestDefinitionGraph.status == "active")
            .options(selectinload(RequestDefinitionGraph.links))
            .order_by(RequestDefinitionGraph.title.asc())
        )
        return list(self.session.execute(stmt).scalars().all())

    def insert(
        self,
        *,
        tenant_id: str,
        definition_id: str,
        source_item_id: str,
        revision: int,
        payload: dict[str, Any],
        links: list[dict[str, str]],
    ) -> RequestDefinitionGraph:
        row = RequestDefinitionGraph(
            id=_uuid(),
            tenant_id=tenant_id,
            definition_id=definition_id,
            source_item_id=source_item_id,
            revision=revision,
            source_text_hash=str(payload["source_text_hash"]),
            title=str(payload["title"]),
            status=str(payload.get("status") or "draft"),
            destination=str(payload["destination"]),
            graph_json=dict(payload.get("graph_json") or {}),
            confirmation_required=bool(payload.get("confirmation_required", True)),
            needs_owner_clarification=bool(payload.get("needs_owner_clarification")),
        )
        self.session.add(row)
        self.session.flush()
        for link in links:
            self.session.add(
                RequestDefinitionLink(
                    id=_uuid(),
                    tenant_id=tenant_id,
                    graph_id=row.id,
                    definition_id=definition_id,
                    entity_type=str(link.get("type") or ""),
                    entity_id=str(link.get("id") or ""),
                )
            )
        self.session.flush()
        return row

    def deactivate_source(self, *, tenant_id: str, source_item_id: str) -> None:
        stmt = (
            update(RequestDefinitionGraph)
            .where(
                RequestDefinitionGraph.tenant_id == tenant_id,
                RequestDefinitionGraph.source_item_id == source_item_id,
                RequestDefinitionGraph.status == "active",
            )
            .values(status="inactive")
        )
        self.session.execute(stmt)

    def mark_deleted(self, *, tenant_id: str, definition_id: str) -> int:
        stmt = (
            update(RequestDefinitionGraph)
            .where(
                RequestDefinitionGraph.tenant_id == tenant_id,
                RequestDefinitionGraph.definition_id == definition_id,
                RequestDefinitionGraph.status != "deleted",
            )
            .values(status="deleted")
        )
        result = self.session.execute(stmt)
        return int(result.rowcount or 0)
