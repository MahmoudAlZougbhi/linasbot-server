"""HA alembic admit: skip leftover tenant-file copy; tenant env fail-closed."""

from __future__ import annotations

import inspect

import pytest

from scripts.ha.release_alembic_migrate import (
    HA_MAINTENANCE_TENANT_ENV,
    ha_maintenance_tenant_id,
    main,
    skip_ha_tenant_runtime_config_file_migrate,
)


def test_ha_admit_skips_tenant_runtime_file_migrate() -> None:
    assert skip_ha_tenant_runtime_config_file_migrate() == "skipped"
    src = inspect.getsource(main)
    assert "skip_ha_tenant_runtime_config_file_migrate()" in src
    assert "migrate_tenant(" not in src
    assert "DEFAULT_TENANT_ID" not in src


def test_ha_maintenance_tenant_id_empty_fails_closed() -> None:
    with pytest.raises(RuntimeError, match=r"set LINASBOT_TENANT_ID="):
        ha_maintenance_tenant_id({})
    with pytest.raises(RuntimeError, match=r"set LINASBOT_TENANT_ID="):
        ha_maintenance_tenant_id({HA_MAINTENANCE_TENANT_ENV: "   "})
    with pytest.raises(RuntimeError, match=r"set LINASBOT_TENANT_ID="):
        ha_maintenance_tenant_id({"DEFAULT_TENANT_ID": "founder-slug"})


def test_ha_maintenance_tenant_id_set_proceeds() -> None:
    assert ha_maintenance_tenant_id({HA_MAINTENANCE_TENANT_ENV: "ops-tenant"}) == "ops-tenant"
    src = inspect.getsource(ha_maintenance_tenant_id)
    assert "tenant env for HA maintenance only — not founder clinic product" in src
