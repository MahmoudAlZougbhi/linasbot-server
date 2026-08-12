"""Add processing status to customer_request_outbox for atomic worker claims.

Revision ID: 20260812_outbox_processing
Revises: 20260812_customer_requests
Create Date: 2026-08-12

Upgrade:
  - Extends ck_customer_request_outbox_status to allow 'processing' (in-flight claim).

Rollback:
  - Restores prior check constraint (pending rows only).
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "20260812_outbox_processing"
down_revision: str | None = "20260812_customer_requests"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_STATUS_WITH_PROCESSING = (
    "status IN ('pending','processing','sent','failed','blocked','cancelled')"
)
_STATUS_WITHOUT_PROCESSING = (
    "status IN ('pending','sent','failed','blocked','cancelled')"
)


def upgrade() -> None:
    op.drop_constraint(
        "ck_customer_request_outbox_status",
        "customer_request_outbox",
        type_="check",
    )
    op.create_check_constraint(
        "ck_customer_request_outbox_status",
        "customer_request_outbox",
        _STATUS_WITH_PROCESSING,
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_customer_request_outbox_status",
        "customer_request_outbox",
        type_="check",
    )
    op.create_check_constraint(
        "ck_customer_request_outbox_status",
        "customer_request_outbox",
        _STATUS_WITHOUT_PROCESSING,
    )
