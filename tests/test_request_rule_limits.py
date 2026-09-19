"""Max 10 request rules per ORDER / APPOINTMENT / HUMAN / OTHER."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from services.ai_setup.request_rule_limits import (
    REQUEST_RULE_LIMIT_CODE,
    RequestRuleLimitError,
    assert_request_rule_limits,
    count_rules_by_type,
)
from services.ai_setup.schemas import RequestsAppointmentsSection, default_section_payload
from services.ai_setup.validation import validate_cm
from services.requests.constants import MAX_RULES_PER_REQUEST_TYPE


def _rules(kind: str, count: int) -> list[dict[str, object]]:
    return [{"id": f"{kind.lower()}-{i}", "type": kind, "name": f"{kind} {i}", "enabled": True} for i in range(count)]


def test_ten_rules_per_type_are_valid() -> None:
    section = RequestsAppointmentsSection.model_validate(
        {"module_enabled": True, "enabled_types": ["ORDER"], "rules": _rules("ORDER", MAX_RULES_PER_REQUEST_TYPE)}
    )
    assert len(section.rules) == MAX_RULES_PER_REQUEST_TYPE


def test_eleventh_order_rule_is_rejected() -> None:
    with pytest.raises(ValidationError) as exc:
        RequestsAppointmentsSection.model_validate({"rules": _rules("ORDER", MAX_RULES_PER_REQUEST_TYPE + 1)})
    assert "ORDER" in str(exc.value)


def test_put_draft_raises_clear_limit_error(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    from pathlib import Path

    from services.ai_setup.storage import ensure_defaults, get_draft, put_draft

    monkeypatch.setenv("LINASBOT_DATA_ROOT", str(tmp_path))
    from storage import persistent_storage as ps

    monkeypatch.setattr(ps, "_DATA_ROOT", Path(tmp_path))
    monkeypatch.setattr(ps, "_LINASBOT_DATA_ROOT", str(tmp_path))
    tenant = "limit-tenant"
    ensure_defaults(tenant_id=tenant)
    env = get_draft("requests_appointments", tenant_id=tenant, create_default=True)
    payload = dict(default_section_payload("requests_appointments"))
    payload["rules"] = _rules("APPOINTMENT", MAX_RULES_PER_REQUEST_TYPE + 1)
    with pytest.raises(RequestRuleLimitError) as exc:
        put_draft("requests_appointments", payload=payload, if_match=env.etag, tenant_id=tenant)
    assert exc.value.code == REQUEST_RULE_LIMIT_CODE
    assert "10" in str(exc.value)
    assert exc.value.request_type == "APPOINTMENT"


def test_validate_cm_blocks_over_limit(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    from pathlib import Path

    from services.ai_setup.storage import ensure_defaults

    monkeypatch.setenv("LINASBOT_DATA_ROOT", str(tmp_path))
    from storage import persistent_storage as ps

    monkeypatch.setattr(ps, "_DATA_ROOT", Path(tmp_path))
    monkeypatch.setattr(ps, "_LINASBOT_DATA_ROOT", str(tmp_path))
    tenant = "limit-validate"
    ensure_defaults(tenant_id=tenant)
    report = validate_cm(
        section="requests_appointments",
        payload={"rules": _rules("HUMAN", MAX_RULES_PER_REQUEST_TYPE + 1)},
        tenant_id=tenant,
    )
    assert report["ok"] is False
    assert any(item.get("code") == REQUEST_RULE_LIMIT_CODE for item in report["errors"])


def test_limit_counter_and_assert() -> None:
    counts = count_rules_by_type(_rules("ORDER", 3) + _rules("APPOINTMENT", 11))
    assert counts["ORDER"] == 3
    assert counts["APPOINTMENT"] == 11
    with pytest.raises(RequestRuleLimitError):
        assert_request_rule_limits({"rules": _rules("APPOINTMENT", 11)})
