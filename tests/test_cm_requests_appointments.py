"""CM Requests & Appointments section: schema, defaults, publish inactive capture."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from services.cm.constants import CM_SECTIONS
from services.cm.schemas import (
    LocalizedLabels,
    RequestFieldDef,
    RequestsAppointmentsSection,
    default_section_payload,
)
from services.cm.section_guide import guide_for_section
from services.cm.setup_chat import SECTION_MODELS
from services.cm.validation import validate_cm
from services.requests.config_loader import (
    load_published_requests_config,
    requests_capture_active,
)
from services.requests.constants import CM_SECTION_REQUESTS_APPOINTMENTS


def test_section_registered_end_to_end() -> None:
    assert CM_SECTION_REQUESTS_APPOINTMENTS == "requests_appointments"
    assert "requests_appointments" in CM_SECTIONS
    assert CM_SECTIONS[-1] == "requests_appointments"
    assert "requests_appointments" in SECTION_MODELS
    guide = guide_for_section("requests_appointments")
    assert guide is not None
    assert guide["title"] == "Requests & Appointments"
    assert guide.get("title_ar") == "الطلبات والمواعيد"


def test_defaults_keep_module_inactive() -> None:
    payload = default_section_payload("requests_appointments")
    section = RequestsAppointmentsSection.model_validate(payload)
    assert section.module_enabled is False
    assert section.rules == []
    assert section.enabled_types == []
    assert section.fields == []
    assert section.services == []
    assert section.products == []
    assert section.branches == []
    assert section.messages.acknowledgment == ""
    assert section.notification_language == "auto"
    assert section.push_enabled is True
    assert section.assignment_defaults.auto_assign is False
    assert section.prohibited == []


def test_schema_accepts_configured_section() -> None:
    section = RequestsAppointmentsSection(
        module_enabled=True,
        enabled_types=["ORDER", "APPOINTMENT", "ORDER"],
        type_labels={"ORDER": LocalizedLabels(en="Order", ar="طلب")},
        fields=[
            RequestFieldDef(
                id="phone",
                labels=LocalizedLabels(en="Phone"),
                required=True,
                order=1,
                validation="phone",
                applies_to=["ORDER"],
            ),
            RequestFieldDef(
                id="preferred_date",
                labels=LocalizedLabels(en="Preferred date"),
                required=False,
                order=2,
                validation="date",
                applies_to=["APPOINTMENT"],
            ),
        ],
        messages={
            "acknowledgment": "Thanks — we received your request.",
            "appointment_confirmed": "Your appointment preference is confirmed.",
            "order_ready": "Your order is ready.",
            "completed": "Done.",
            "cancelled": "Cancelled.",
        },
        prohibited=["illegal items"],
    )
    assert section.enabled_types == ["ORDER", "APPOINTMENT"]
    dumped = section.model_dump(mode="json")
    assert dumped["messages"]["order_ready"] == "Your order is ready."
    RequestsAppointmentsSection.model_validate(dumped)


def test_schema_rejects_bad_type_label_keys() -> None:
    with pytest.raises(ValidationError):
        RequestsAppointmentsSection(type_labels={"BOOKING": LocalizedLabels(en="x")})


@pytest.fixture()
def tenant_data(tmp_path, monkeypatch: pytest.MonkeyPatch) -> str:
    from pathlib import Path

    monkeypatch.setenv("LINASBOT_DATA_ROOT", str(tmp_path))
    from storage import persistent_storage as ps

    monkeypatch.setattr(ps, "_DATA_ROOT", Path(tmp_path))
    monkeypatch.setattr(ps, "_LINASBOT_DATA_ROOT", str(tmp_path))
    return "tenant_requests_cm"


def test_validate_cm_accepts_default_section(tenant_data: str) -> None:
    from services.cm.storage import ensure_defaults, get_draft, put_draft

    ensure_defaults(tenant_id=tenant_data)
    result = validate_cm(tenant_id=tenant_data)
    assert result["ok"] is True

    env = get_draft("requests_appointments", tenant_id=tenant_data, create_default=True)
    put_draft(
        "requests_appointments",
        payload=default_section_payload("requests_appointments"),
        if_match=env.etag,
        tenant_id=tenant_data,
        updated_by="test",
    )
    result2 = validate_cm(section="requests_appointments", tenant_id=tenant_data)
    assert result2["ok"] is True


def test_missing_or_unpublished_section_keeps_capture_inactive(tenant_data: str) -> None:
    assert load_published_requests_config(tenant_data) is None
    assert requests_capture_active(tenant_data) is False
    assert requests_capture_active(None) is False


@pytest.mark.asyncio
async def test_published_defaults_do_not_activate_capture(
    tenant_data: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from tests.cm_test_helpers import install_mocked_openai_embeddings, publish_test_content

    install_mocked_openai_embeddings(monkeypatch, published_mode=True)
    await publish_test_content(tenant_data)
    cfg = load_published_requests_config(tenant_data)
    assert isinstance(cfg, dict)
    assert cfg.get("module_enabled") is False
    assert cfg.get("enabled_types") == []
    assert requests_capture_active(tenant_data) is False


@pytest.mark.asyncio
async def test_published_enabled_activates_capture(
    tenant_data: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from tests.cm_test_helpers import install_mocked_openai_embeddings, publish_test_content

    install_mocked_openai_embeddings(monkeypatch, published_mode=True)
    enabled = RequestsAppointmentsSection(
        module_enabled=True,
        enabled_types=["APPOINTMENT"],
    ).model_dump(mode="json")
    await publish_test_content(tenant_data, {"requests_appointments": enabled})
    assert requests_capture_active(tenant_data) is True


@pytest.mark.asyncio
async def test_published_without_section_key_stays_inactive(
    tenant_data: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Existing tenants whose published blob lacks the new section stay safe."""
    from services.cm.embeddings import embedding_pin
    from services.cm.schemas import PublishedPointer, default_section_payload
    from services.cm.semantic_index import build_index
    from services.cm.version_store import write_published_pointer, write_version_content
    from tests.cm_test_helpers import install_mocked_openai_embeddings

    install_mocked_openai_embeddings(monkeypatch, published_mode=True)
    legacy_sections = {name: default_section_payload(name) for name in CM_SECTIONS if name != "requests_appointments"}
    version_id = f"v_{tenant_data}_legacy"
    checksums = write_version_content(tenant_data, version_id, legacy_sections)
    index_manifest = await build_index(
        tenant_id=tenant_data,
        content_version_id=version_id,
        sections=legacy_sections,
        index_id=f"idx_{tenant_data}_legacy",
    )
    pin = embedding_pin()
    write_published_pointer(
        tenant_data,
        PublishedPointer(
            content_version_id=version_id,
            index_version_id=str(index_manifest["index_id"]),
            checksums=checksums,
            embedding_provider=pin.provider,
            embedding_model=pin.model,
            embedding_version=pin.version,
            embedding_dimensions=pin.dimensions,
        ),
    )
    assert load_published_requests_config(tenant_data) is None
    assert requests_capture_active(tenant_data) is False
