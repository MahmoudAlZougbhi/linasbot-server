"""Widen Customer AI provider/operation id columns for Meta Instagram mids.

Revision ID: 20260918_widen_provider_ids
Revises: 20260912_cai_tidx

Instagram Graph message IDs are ~164 characters. Composite keys are
``tenant + ':' + mid``. Do not truncate existing values.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op
from db.models.id_lengths import COMPOSITE_REF_MAX, PROVIDER_REF_MAX

revision: str = "20260918_widen_provider_ids"
down_revision: str | None = "20260912_cai_tidx"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _widen(table: str, column: str, length: int) -> None:
    op.alter_column(
        table,
        column,
        existing_type=sa.String(),
        type_=sa.String(length=length),
        existing_nullable=False,
    )


def upgrade() -> None:
    _widen("customer_ai_message_reservations", "reservation_id", COMPOSITE_REF_MAX)
    _widen("customer_ai_message_reservations", "operation_id", PROVIDER_REF_MAX)
    _widen("customer_ai_expense_events", "event_id", COMPOSITE_REF_MAX)
    _widen("customer_ai_expense_events", "operation_id", PROVIDER_REF_MAX)
    _widen("customer_ai_expense_events", "parent_event_id", COMPOSITE_REF_MAX)
    _widen("customer_ai_pending_settlements", "settlement_id", COMPOSITE_REF_MAX)
    _widen("customer_ai_pending_settlements", "reservation_id", COMPOSITE_REF_MAX)
    _widen("customer_ai_pending_settlements", "operation_id", PROVIDER_REF_MAX)
    _widen("customer_ai_pending_settlements", "provider_message_id", PROVIDER_REF_MAX)
    _widen("customer_ai_outbox", "outbox_id", COMPOSITE_REF_MAX)
    _widen("customer_ai_outbox", "operation_id", PROVIDER_REF_MAX)
    _widen("customer_ai_outbox", "reservation_id", COMPOSITE_REF_MAX)
    _widen("customer_ai_outbox", "provider_message_id", PROVIDER_REF_MAX)
    _widen("customer_ai_credit_reservation_index", "reservation_id", COMPOSITE_REF_MAX)
    _widen("customer_ai_credit_reservation_index", "request_id", PROVIDER_REF_MAX)


def downgrade() -> None:
    # Shrinking would truncate live Meta IDs. Leave widths in place.
    return
