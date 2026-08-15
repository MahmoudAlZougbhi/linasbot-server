"""Repository for tenant services with priced options."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from db.models.tenant_services import ServiceOption, TenantService
from services.service_catalog.schemas import normalize_service_name


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(UTC)


class ServiceCatalogRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def list_services(self, *, tenant_id: str, limit: int = 200, offset: int = 0) -> list[TenantService]:
        stmt = (
            select(TenantService)
            .where(TenantService.tenant_id == tenant_id)
            .options(selectinload(TenantService.options))
            .order_by(TenantService.updated_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(self.session.execute(stmt).scalars().all())

    def count_services(self, *, tenant_id: str) -> int:
        stmt = select(func.count()).select_from(TenantService).where(TenantService.tenant_id == tenant_id)
        return int(self.session.execute(stmt).scalar_one())

    def get_service(self, *, tenant_id: str, service_id: str) -> TenantService | None:
        stmt = (
            select(TenantService)
            .where(TenantService.tenant_id == tenant_id, TenantService.id == service_id)
            .options(selectinload(TenantService.options))
        )
        return self.session.execute(stmt).scalar_one_or_none()

    def create_service(self, *, tenant_id: str, fields: dict[str, Any]) -> TenantService:
        row = TenantService(
            id=_uuid(),
            tenant_id=tenant_id,
            name=fields["name"],
            name_normalized=normalize_service_name(fields["name"]),
            active=bool(fields.get("active", True)),
            created_at=_now(),
            updated_at=_now(),
        )
        self.session.add(row)
        self.session.flush()
        return row

    def update_service(self, row: TenantService, *, fields: dict[str, Any]) -> TenantService:
        if "name" in fields:
            row.name = fields["name"]
            row.name_normalized = normalize_service_name(fields["name"])
        if "active" in fields:
            row.active = bool(fields["active"])
        row.updated_at = _now()
        self.session.flush()
        return row

    def replace_options(
        self,
        *,
        tenant_id: str,
        service_id: str,
        options: list[dict[str, Any]],
    ) -> None:
        existing = self.session.execute(
            select(ServiceOption).where(
                ServiceOption.tenant_id == tenant_id,
                ServiceOption.service_id == service_id,
            )
        ).scalars().all()
        for row in existing:
            self.session.delete(row)
        self.session.flush()
        for index, opt in enumerate(options):
            self.session.add(
                ServiceOption(
                    id=str(opt.get("id") or _uuid()),
                    tenant_id=tenant_id,
                    service_id=service_id,
                    machine_name=opt.get("machine_name"),
                    body_part=opt.get("body_part"),
                    staff_name=opt.get("staff_name"),
                    price=opt["price"],
                    currency=str(opt.get("currency") or "USD"),
                    sort_order=int(opt.get("sort_order", index)),
                    created_at=_now(),
                )
            )
        self.session.flush()

    def delete_service(self, row: TenantService) -> None:
        self.session.delete(row)
        self.session.flush()

    def search_by_name_prefix(
        self,
        *,
        tenant_id: str,
        query: str,
        limit: int = 10,
    ) -> list[TenantService]:
        normalized = normalize_service_name(query)
        if not normalized:
            return []
        stmt = (
            select(TenantService)
            .where(
                TenantService.tenant_id == tenant_id,
                TenantService.name_normalized.contains(normalized),
            )
            .options(selectinload(TenantService.options))
            .order_by(TenantService.updated_at.desc())
            .limit(limit)
        )
        return list(self.session.execute(stmt).scalars().all())

    def list_all_for_tenant(self, *, tenant_id: str) -> list[TenantService]:
        stmt = (
            select(TenantService)
            .where(TenantService.tenant_id == tenant_id)
            .options(selectinload(TenantService.options))
        )
        return list(self.session.execute(stmt).scalars().all())
