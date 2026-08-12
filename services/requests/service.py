"""Domain service for Customer Requests."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from db.models.requests import CustomerRequest
from services.requests.config_loader import (
    published_configuration_version,
    requests_capture_active,
)
from services.requests.repository import CustomerRequestsRepository
from services.requests.schemas import RequestCreateBody
from services.requests.serialize import (
    serialize_card,
    serialize_event,
    serialize_note,
    serialize_request,
)
from services.requests.state_machine import (
    InvalidRequestTransition,
    require_transition,
    resolve_final_action_status,
)


class CustomerRequestsError(Exception):
    def __init__(self, code: str, message: str, *, http_status: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.http_status = http_status


def _now() -> datetime:
    return datetime.now(UTC)


class CustomerRequestsService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.repo = CustomerRequestsRepository(session)

    def create_from_ai(self, *, tenant_id: str, body: RequestCreateBody) -> dict[str, Any]:
        if not body.customer_confirmed:
            raise CustomerRequestsError(
                "CUSTOMER_CONFIRMATION_REQUIRED",
                "Request create requires customer confirmation",
            )
        if not requests_capture_active(tenant_id):
            raise CustomerRequestsError(
                "REQUESTS_SETUP_REQUIRED",
                "Requests capture inactive until published configuration",
                http_status=409,
            )
        existing = self.repo.get_idempotency(tenant_id=tenant_id, scope="ai_create", key=body.idempotency_key)
        if existing and existing.request_id:
            row = self.repo.get_for_tenant(tenant_id=tenant_id, request_id=existing.request_id)
            if row is None:
                raise CustomerRequestsError("IDEMPOTENCY_ORPHAN", "Idempotency points to missing request")
            return serialize_request(row, include_sensitive=True)

        cfg_version = body.configuration_version or published_configuration_version(tenant_id)
        number = self.repo.allocate_request_number(tenant_id)
        now = _now()
        row = self.repo.create_request(
            tenant_id=tenant_id,
            request_number=number,
            request_type=body.request_type.strip().upper(),
            status="NEW",
            source_channel=body.source_channel.strip().lower(),
            source_account_id=body.source_account_id,
            external_customer_id=body.external_customer_id,
            platform_username=body.platform_username,
            customer_display_name=body.customer_display_name,
            customer_name=body.customer_name,
            phone_normalized=body.phone_normalized,
            email=body.email,
            conversation_id=body.conversation_id,
            originating_message_id=body.originating_message_id,
            originating_comment_id=body.originating_comment_id,
            title=body.title,
            collected_fields=body.collected_fields,
            requested_items=body.requested_items,
            requested_branch=body.requested_branch,
            preferred_date=body.preferred_date,
            preferred_time=body.preferred_time,
            fulfillment_preference=body.fulfillment_preference,
            delivery_address=body.delivery_address,
            customer_notes=body.customer_notes,
            configuration_version=cfg_version,
            row_version=1,
            notification_status="none",
            submitted_at=now,
        )
        self.repo.add_event(
            tenant_id=tenant_id,
            request_id=row.id,
            event_type="create",
            actor_kind="ai",
            payload={"request_number": number, "request_type": row.request_type},
        )
        self.repo.put_idempotency(
            tenant_id=tenant_id,
            scope="ai_create",
            key=body.idempotency_key,
            request_id=row.id,
        )
        self.session.commit()
        return serialize_request(row, include_sensitive=True)

    def get(self, *, tenant_id: str, request_id: str, include_sensitive: bool) -> dict[str, Any]:
        row = self.repo.get_for_tenant(tenant_id=tenant_id, request_id=request_id)
        if row is None:
            raise CustomerRequestsError("NOT_FOUND", "Request not found", http_status=404)
        data = serialize_request(row, include_sensitive=include_sensitive)
        data["notes"] = [serialize_note(n) for n in self.repo.list_notes(tenant_id=tenant_id, request_id=request_id)]
        data["events"] = [serialize_event(e) for e in self.repo.list_events(tenant_id=tenant_id, request_id=request_id)]
        return data

    def list(
        self,
        *,
        tenant_id: str,
        request_type: str | None = None,
        status: str | None = None,
        source_channel: str | None = None,
        assigned_user_id: str | None = None,
        q: str | None = None,
        cursor: str | None = None,
        limit: int = 25,
    ) -> dict[str, Any]:
        created_before = None
        if cursor:
            try:
                created_before = datetime.fromisoformat(cursor)
            except ValueError as exc:
                raise CustomerRequestsError("INVALID_CURSOR", "Invalid pagination cursor") from exc
        rows = self.repo.list_requests(
            tenant_id=tenant_id,
            request_type=request_type.upper() if request_type else None,
            status=status.upper() if status else None,
            source_channel=source_channel,
            assigned_user_id=assigned_user_id,
            q=q,
            created_before=created_before,
            limit=limit + 1,
        )
        has_more = len(rows) > limit
        page = rows[:limit]
        next_cursor = None
        if has_more and page and page[-1].created_at is not None:
            next_cursor = page[-1].created_at.isoformat()
        return {
            "items": [serialize_card(r) for r in page],
            "next_cursor": next_cursor,
            "counts": self.repo.status_counts(tenant_id=tenant_id),
        }

    def assign(
        self,
        *,
        tenant_id: str,
        request_id: str,
        actor_user_id: str,
        assigned_user_id: str | None,
        row_version: int,
    ) -> dict[str, Any]:
        row = self._lock_version(tenant_id, request_id, row_version)
        row.assigned_user_id = assigned_user_id
        row.row_version += 1
        row.updated_at = _now()
        self.repo.add_event(
            tenant_id=tenant_id,
            request_id=request_id,
            event_type="assignment",
            actor_kind="operator",
            actor_user_id=actor_user_id,
            payload={"assigned_user_id": assigned_user_id},
        )
        self.session.commit()
        return serialize_request(row)

    def add_note(self, *, tenant_id: str, request_id: str, author_user_id: str, body: str) -> dict[str, Any]:
        row = self.repo.get_for_tenant(tenant_id=tenant_id, request_id=request_id)
        if row is None:
            raise CustomerRequestsError("NOT_FOUND", "Request not found", http_status=404)
        note = self.repo.add_note(
            tenant_id=tenant_id,
            request_id=request_id,
            author_user_id=author_user_id,
            body=body.strip(),
        )
        self.repo.add_event(
            tenant_id=tenant_id,
            request_id=request_id,
            event_type="note",
            actor_kind="operator",
            actor_user_id=author_user_id,
            payload={"note_id": note.id},
        )
        self.session.commit()
        return serialize_note(note)

    def transition_status(
        self,
        *,
        tenant_id: str,
        request_id: str,
        actor_user_id: str,
        to_status: str,
        row_version: int,
        cancellation_reason: str | None = None,
    ) -> dict[str, Any]:
        row = self._lock_version(tenant_id, request_id, row_version)
        target = to_status.strip().upper()
        try:
            require_transition(row.request_type, row.status, target)
        except InvalidRequestTransition as exc:
            raise CustomerRequestsError("INVALID_TRANSITION", str(exc)) from exc
        previous = row.status
        row.status = target
        row.row_version += 1
        row.updated_at = _now()
        if target == "CANCELLED":
            row.cancellation_reason = cancellation_reason
            row.cancelled_at = _now()
        elif target == "CONFIRMED":
            row.confirmed_at = _now()
        elif target == "READY":
            row.ready_at = _now()
        elif target == "COMPLETED":
            row.completed_at = _now()
        self.repo.add_event(
            tenant_id=tenant_id,
            request_id=request_id,
            event_type="status_change",
            actor_kind="operator",
            actor_user_id=actor_user_id,
            payload={"from": previous, "to": target},
        )
        self.session.commit()
        return serialize_request(row)

    def final_action(
        self,
        *,
        tenant_id: str,
        request_id: str,
        actor_user_id: str,
        action: str,
        row_version: int,
        completion_message: str | None,
        idempotency_key: str,
        send_notification: bool,
    ) -> dict[str, Any]:
        existing = self.repo.get_idempotency(tenant_id=tenant_id, scope="final_action", key=idempotency_key)
        if existing and existing.request_id:
            row = self.repo.get_for_tenant(tenant_id=tenant_id, request_id=existing.request_id)
            if row is None:
                raise CustomerRequestsError("IDEMPOTENCY_ORPHAN", "Idempotency points to missing request")
            return serialize_request(row)

        row = self._lock_version(tenant_id, request_id, row_version)
        try:
            target = resolve_final_action_status(row.request_type, action)
            require_transition(row.request_type, row.status, target)
        except InvalidRequestTransition as exc:
            raise CustomerRequestsError("INVALID_TRANSITION", str(exc)) from exc

        previous = row.status
        row.status = target
        row.row_version += 1
        row.updated_at = _now()
        if completion_message is not None:
            row.completion_message = completion_message
        if target == "CONFIRMED":
            row.confirmed_at = _now()
        elif target == "READY":
            row.ready_at = _now()
        elif target == "COMPLETED":
            row.completed_at = _now()

        self.repo.add_event(
            tenant_id=tenant_id,
            request_id=request_id,
            event_type="final_action",
            actor_kind="operator",
            actor_user_id=actor_user_id,
            payload={"action": action, "from": previous, "to": target},
        )
        self.repo.put_idempotency(
            tenant_id=tenant_id,
            scope="final_action",
            key=idempotency_key,
            request_id=request_id,
        )

        if send_notification:
            message = (completion_message or row.completion_message or "").strip()
            outbox = self.repo.enqueue_outbox(
                tenant_id=tenant_id,
                request_id=request_id,
                idempotency_key=f"notify:{idempotency_key}",
                channel=row.source_channel,
                payload={"message": message, "request_number": row.request_number},
            )
            # Delivery is attempted by outbox worker / notify endpoint; mark pending.
            if outbox.status == "pending":
                row.notification_status = "pending"

        self.session.commit()
        return serialize_request(row)

    def retry_notification(
        self, *, tenant_id: str, request_id: str, actor_user_id: str, idempotency_key: str
    ) -> dict[str, Any]:
        row = self.repo.get_for_tenant(tenant_id=tenant_id, request_id=request_id)
        if row is None:
            raise CustomerRequestsError("NOT_FOUND", "Request not found", http_status=404)
        outbox = self.repo.enqueue_outbox(
            tenant_id=tenant_id,
            request_id=request_id,
            idempotency_key=idempotency_key,
            channel=row.source_channel,
            payload={
                "message": row.completion_message or "",
                "request_number": row.request_number,
                "retry": True,
            },
        )
        row.notification_status = "pending" if outbox.status == "pending" else row.notification_status
        row.updated_at = _now()
        self.repo.add_event(
            tenant_id=tenant_id,
            request_id=request_id,
            event_type="notification_retry",
            actor_kind="operator",
            actor_user_id=actor_user_id,
            payload={"outbox_id": outbox.id, "idempotency_key": idempotency_key},
        )
        self.session.commit()
        return serialize_request(row)

    def _lock_version(self, tenant_id: str, request_id: str, row_version: int) -> CustomerRequest:
        row = self.repo.get_for_tenant(tenant_id=tenant_id, request_id=request_id)
        if row is None:
            raise CustomerRequestsError("NOT_FOUND", "Request not found", http_status=404)
        if int(row.row_version) != int(row_version):
            raise CustomerRequestsError(
                "VERSION_CONFLICT",
                "Stale row_version; refresh and retry",
                http_status=409,
            )
        return row
