"""CM Phase 7-8: publish, rollback, cutover rehearsal, and SoT audit (report-only)."""

from __future__ import annotations

import uuid

import pytest

from services.cm.cutover import evaluate_cutover_readiness, run_publish_rehearsal, seed_rehearsal_tenant_from_draft
from services.cm.publish import PublishBlockedError, RollbackTargetError, publish_draft, rollback_to_version
from services.cm.sot_audit import audit_sot_sources
from services.cm.storage import get_draft, put_draft
from services.cm.version_store import PublishedVersionError, load_published_content


@pytest.mark.asyncio
async def test_publish_draft_writes_version_builds_index_and_flips_pointer() -> None:
    tenant_id = f"cm_publish_test_basic_{uuid.uuid4().hex[:8]}"
    result = await publish_draft(tenant_id=tenant_id, published_by="tester")

    assert result.content_version_id
    assert result.index_version_id
    # Fresh unique tenant: first publish has no previous pointer
    assert result.previous_pointer is None

    pointer, sections = load_published_content(tenant_id)
    assert pointer.content_version_id == result.content_version_id
    assert pointer.index_version_id == result.index_version_id
    assert set(sections.keys())  # sections were written and load with verified checksums


@pytest.mark.asyncio
async def test_second_publish_creates_new_immutable_version_and_records_previous_pointer() -> None:
    tenant_id = f"cm_publish_test_second_{uuid.uuid4().hex[:8]}"
    first = await publish_draft(tenant_id=tenant_id, published_by="tester")
    second = await publish_draft(tenant_id=tenant_id, published_by="tester")

    assert second.content_version_id != first.content_version_id
    assert second.previous_pointer is not None
    assert second.previous_pointer["content_version_id"] == first.content_version_id

    pointer, _ = load_published_content(tenant_id)
    assert pointer.content_version_id == second.content_version_id


@pytest.mark.asyncio
async def test_publish_blocked_on_restricted_conflict_validation_error() -> None:
    tenant_id = f"cm_publish_test_blocked_{uuid.uuid4().hex[:8]}"

    restricted_env = get_draft("restricted", tenant_id=tenant_id, create_default=True)
    restricted_payload = dict(restricted_env.payload)
    topics = list(restricted_payload.get("topics") or [])
    assert topics, "expected default restricted topics (tattoo_removal etc.)"
    conflicting_topic_id = topics[0]["id"]

    prices_env = get_draft("prices", tenant_id=tenant_id, create_default=True)
    prices_payload = dict(prices_env.payload)
    prices_payload["items"] = [
        {
            "id": "row_1",
            "service_id": conflicting_topic_id,
            "amount": 100,
            "currency": "USD",
        }
    ]
    put_draft(
        "prices",
        payload=prices_payload,
        if_match=prices_env.etag,
        tenant_id=tenant_id,
        updated_by="tester",
    )

    with pytest.raises(PublishBlockedError) as excinfo:
        await publish_draft(tenant_id=tenant_id, published_by="tester")
    assert excinfo.value.errors

    # A blocked publish must never advance the published pointer.
    with pytest.raises(PublishedVersionError):
        load_published_content(tenant_id)


@pytest.mark.asyncio
async def test_rollback_restores_prior_content_and_index_together() -> None:
    tenant_id = f"cm_publish_test_rollback_{uuid.uuid4().hex[:8]}"
    first = await publish_draft(tenant_id=tenant_id, published_by="tester")
    second = await publish_draft(tenant_id=tenant_id, published_by="tester")

    pointer_before, _ = load_published_content(tenant_id)
    assert pointer_before.content_version_id == second.content_version_id

    rollback_result = rollback_to_version(tenant_id=tenant_id, content_version_id=first.content_version_id)
    assert rollback_result.content_version_id == first.content_version_id
    assert rollback_result.index_version_id == first.index_version_id

    pointer_after, _ = load_published_content(tenant_id)
    assert pointer_after.content_version_id == first.content_version_id
    assert pointer_after.index_version_id == first.index_version_id


def test_rollback_unknown_version_raises_honest_error() -> None:
    with pytest.raises(RollbackTargetError):
        rollback_to_version(
            tenant_id=f"cm_publish_test_rollback_missing_{uuid.uuid4().hex[:8]}", content_version_id="v_does_not_exist"
        )


@pytest.mark.asyncio
async def test_publish_is_idempotent_safe_to_call_repeatedly_without_deadlock() -> None:
    """Regression guard: publish_draft must not self-deadlock on the tenant lock (nested
    get_draft calls inside validate_cm/_collect_draft_sections)."""
    tenant_id = f"cm_publish_test_repeat_{uuid.uuid4().hex[:8]}"
    for _ in range(3):
        result = await publish_draft(tenant_id=tenant_id, published_by="tester")
        assert result.content_version_id


def test_sot_audit_is_report_only_and_lists_known_legacy_sources() -> None:
    report = audit_sot_sources()
    assert report["sources"]
    ids = {s["id"] for s in report["sources"]}
    assert "price_list_file" in ids
    assert "default_whatsapp_contacts" in ids
    for source in report["sources"]:
        assert "referenced_in" in source
        assert "fully_gated_by_cm_runtime_mode" in source


@pytest.mark.asyncio
async def test_cutover_rehearsal_never_touches_real_tenant_published_pointer() -> None:
    real_tenant_id = f"cm_cutover_test_real_{uuid.uuid4().hex[:8]}"
    rehearsal = await run_publish_rehearsal(tenant_id=real_tenant_id, published_by="tester")
    assert rehearsal["ok"] is True
    assert rehearsal["rehearsal_tenant_id"] != real_tenant_id

    with pytest.raises(PublishedVersionError):
        load_published_content(real_tenant_id)

    pointer, _ = load_published_content(rehearsal["rehearsal_tenant_id"])
    assert pointer.content_version_id == rehearsal["content_version_id"]


def test_seed_rehearsal_tenant_is_idempotent() -> None:
    real_tenant_id = f"cm_cutover_test_seed_{uuid.uuid4().hex[:8]}"
    first_tid = seed_rehearsal_tenant_from_draft(tenant_id=real_tenant_id)
    second_tid = seed_rehearsal_tenant_from_draft(tenant_id=real_tenant_id)
    assert first_tid == second_tid


def test_cutover_readiness_gate_ready_when_draft_valid() -> None:
    result = evaluate_cutover_readiness(tenant_id="cm_cutover_test_readiness")
    assert result.ready is True
    assert result.checks["draft_validation_ok"] is True
    assert "sot_audit" in result.checks
    assert "ungated_legacy_sources" in result.checks
