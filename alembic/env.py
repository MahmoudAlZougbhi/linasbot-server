"""Alembic environment for Linas WhatsApp Cloud PostgreSQL migrations."""

from __future__ import annotations

import os
import sys
from logging.config import fileConfig
from pathlib import Path

from alembic.ddl.impl import DefaultImpl
from sqlalchemy import (
    Column,
    MetaData,
    PrimaryKeyConstraint,
    String,
    Table,
    engine_from_config,
    pool,
)

from alembic import context

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from db.models import (  # noqa: E402, F401 — register models on metadata
    Base,  # noqa: E402
    MetaAssetBindingRow,
    MetaBindingCredentialRow,
    MetaOAuthStateRow,
    MetaRegistryAuditEvent,
    TikTokConnection,
    TikTokCredential,
    TikTokOAuthAttempt,
    TikTokWebhookEvent,
    WhatsAppAuditEvent,
    WhatsAppConnection,
    WhatsAppConnectionAttempt,
    WhatsAppConversation,
    WhatsAppCredential,
    WhatsAppMessage,
    WhatsAppOutboundIntent,
    WhatsAppPilotEntitlement,
    WhatsAppWebhookEvent,
)

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

# Alembic 1.14 DefaultImpl creates version_num VARCHAR(32). Fresh databases
# must allocate VARCHAR(64) before any longer revision id is stamped. Existing
# VARCHAR(32) catalogs are widened by revision 20260814_widen_ver_num.
_VERSION_NUM_WIDTH = 64


def _version_table_impl(
    self: DefaultImpl,
    *,
    version_table: str,
    version_table_schema: str | None,
    version_table_pk: bool,
    **kw: object,
) -> Table:
    table = Table(
        version_table,
        MetaData(),
        Column("version_num", String(_VERSION_NUM_WIDTH), nullable=False),
        schema=version_table_schema,
    )
    if version_table_pk:
        table.append_constraint(PrimaryKeyConstraint("version_num", name=f"{version_table}_pkc"))
    return table


if not hasattr(DefaultImpl, "version_table_impl"):
    raise RuntimeError("Alembic DefaultImpl.version_table_impl is required for version_num VARCHAR(64)")
DefaultImpl.version_table_impl = _version_table_impl  # type: ignore[method-assign]


def get_url() -> str:
    url = (os.getenv("LINAS_WHATSAPP_DATABASE_URL") or os.getenv("DATABASE_URL") or "").strip()
    if not url:
        raise RuntimeError(
            "Set LINAS_WHATSAPP_DATABASE_URL or DATABASE_URL before running alembic. "
            "Do not invent production credentials."
        )
    return url


def run_migrations_offline() -> None:
    context.configure(
        url=get_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    configuration = config.get_section(config.config_ini_section) or {}
    configuration["sqlalchemy.url"] = get_url()
    connectable = engine_from_config(configuration, prefix="sqlalchemy.", poolclass=pool.NullPool)
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
