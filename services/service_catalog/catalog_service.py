"""Business logic for tenant services with priced options."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from services.service_catalog.repository import ServiceCatalogRepository
from services.service_catalog.schemas import ServiceWriteBody, service_to_dict


class ServiceCatalogError(Exception):
    def __init__(self, *, code: str, message: str, http_status: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.http_status = http_status


class ServiceCatalogService:
    def __init__(self, session: Session) -> None:
        self.repo = ServiceCatalogRepository(session)
        self.session = session

    def list_services(self, *, tenant_id: str, limit: int = 200, offset: int = 0) -> dict[str, Any]:
        rows = self.repo.list_services(tenant_id=tenant_id, limit=limit, offset=offset)
        total = self.repo.count_services(tenant_id=tenant_id)
        return {
            "services": [service_to_dict(row) for row in rows],
            "total": total,
        }

    def get_service(self, *, tenant_id: str, service_id: str) -> dict[str, Any]:
        row = self.repo.get_service(tenant_id=tenant_id, service_id=service_id)
        if row is None:
            raise ServiceCatalogError(code="NOT_FOUND", message="service_not_found", http_status=404)
        return service_to_dict(row)

    def create_service(self, *, tenant_id: str, body: ServiceWriteBody) -> dict[str, Any]:
        row = self.repo.create_service(
            tenant_id=tenant_id,
            fields={"name": body.name.strip(), "active": body.active},
        )
        self.repo.replace_options(
            tenant_id=tenant_id,
            service_id=row.id,
            options=[opt.model_dump() for opt in body.options],
        )
        self.session.flush()
        self.session.expire(row, ["options"])
        refreshed = self.repo.get_service(tenant_id=tenant_id, service_id=row.id)
        assert refreshed is not None
        return service_to_dict(refreshed)

    def update_service(
        self,
        *,
        tenant_id: str,
        service_id: str,
        body: ServiceWriteBody,
    ) -> dict[str, Any]:
        row = self.repo.get_service(tenant_id=tenant_id, service_id=service_id)
        if row is None:
            raise ServiceCatalogError(code="NOT_FOUND", message="service_not_found", http_status=404)
        self.repo.update_service(
            row,
            fields={"name": body.name.strip(), "active": body.active},
        )
        self.repo.replace_options(
            tenant_id=tenant_id,
            service_id=row.id,
            options=[opt.model_dump() for opt in body.options],
        )
        self.session.flush()
        self.session.expire(row, ["options"])
        refreshed = self.repo.get_service(tenant_id=tenant_id, service_id=row.id)
        assert refreshed is not None
        return service_to_dict(refreshed)

    def delete_service(self, *, tenant_id: str, service_id: str) -> None:
        row = self.repo.get_service(tenant_id=tenant_id, service_id=service_id)
        if row is None:
            raise ServiceCatalogError(code="NOT_FOUND", message="service_not_found", http_status=404)
        self.repo.delete_service(row)
