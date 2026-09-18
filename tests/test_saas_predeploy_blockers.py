"""Off days, handoff destinations, comments actions, and generic-tenant leakage guards."""

from __future__ import annotations

import time

import pytest

from services.ai_setup.actions import (
    ACTION_FACEBOOK_COMMENTS,
    comments_enforcement_decision,
    evaluate_comments_meta_readiness,
)
from services.ai_setup.schemas import (
    ActionsSection,
    AiBasics,
    HandoffContact,
    HandoffMatrixRow,
    HandoffPolicy,
    OffDayRule,
    OffDaysSection,
)
from services.ai_setup.structured_resolver import resolve_handoff
from tests.cm_test_helpers import install_mocked_openai_embeddings, publish_test_content


@pytest.fixture(autouse=True)
def _openai_published_embeddings(monkeypatch: pytest.MonkeyPatch) -> None:
    install_mocked_openai_embeddings(monkeypatch, published_mode=True)


def test_handoff_email_and_url_destinations() -> None:
    email = HandoffContact(
        id="desk",
        destination_type="email",
        destination_value="hello@gym.example",
        label="Front desk",
    )
    url = HandoffContact(
        id="book",
        destination_type="url",
        destination_value="https://gym.example/book",
        label="Booking page",
    )
    policy = HandoffPolicy(
        contacts=[email, url],
        matrix=[HandoffMatrixRow(id="r1", contact_id="desk", enabled=True)],
    )
    resolution = resolve_handoff(policy)
    assert resolution.destination_type == "email"
    assert resolution.destination_value == "hello@gym.example"
    assert resolution.contact_phone_e164 is None

    policy2 = HandoffPolicy(
        contacts=[url],
        matrix=[HandoffMatrixRow(id="r2", contact_id="book", enabled=True)],
    )
    r2 = resolve_handoff(policy2)
    assert r2.destination_type == "url"
    assert r2.destination_value == "https://gym.example/book"


def test_comments_action_gate_and_readiness() -> None:
    readiness = evaluate_comments_meta_readiness(
        channel="facebook",
        cm_action_enabled=True,
        per_asset_switch_enabled=True,
    )
    assert readiness["scopes_ready"] is False
    assert readiness["live_verified"] is False
    assert "pages_manage_engagement" in readiness["scopes_missing"]

    from services.integrations.meta.meta_app_registry import MetaAssetBinding, MetaBindingCredential

    binding = MetaAssetBinding(
        binding_id="fb-test",
        tenant_id="tenant-x",
        channel="facebook",
        asset_id="page-1",
        page_id="page-1",
        instagram_account_id="",
        app_key="linas_first_party",
        credential_id="cred-1",
        status="active",
        generation=1,
        created_at=0.0,
        updated_at=0.0,
        auth_flow="facebook_login",
        comment_permission_status="verified_granted",
        comment_permission_verified_at=1.0,
        comment_permission_source="oauth_stored_scopes",
        comment_permission_credential_id="cred-1",
        comment_permission_token_fingerprint="abc",
    )
    credential = MetaBindingCredential(
        access_token="page-token",
        token_app_id="2963733803971681",
        token_profile_id="page-1",
        scopes=("pages_read_user_content", "pages_manage_engagement", "pages_messaging"),
        expires_at=int(time.time()) + 3600,
        authorized_meta_user_id="user-1",
        auth_flow="facebook_login",
    )
    decision = comments_enforcement_decision(
        tenant_id="no_such_tenant_actions",
        channel="facebook",
        per_asset_enabled=True,
        binding=binding,
        credential=credential,
    )
    assert decision["allow"] is False
    assert decision["reason"] == "cm_action_disabled"
    assert ACTION_FACEBOOK_COMMENTS == "respond_facebook_comments"


def test_legacy_bridge_kill_switch(monkeypatch, tmp_path) -> None:
    monkeypatch.delenv("CM_EMERGENCY_FORCE_LEGACY", raising=False)
    monkeypatch.setenv("CM_DISABLE_LEGACY_BRIDGE", "true")
    monkeypatch.setenv("CM_DISABLE_LINAS_LEGACY_BRIDGE", "true")
    monkeypatch.setenv("LINASBOT_DATA_ROOT", str(tmp_path))
    # Re-import path uses env each call
    from services.ai_setup import constants as cm_constants

    assert cm_constants.cm_disable_linas_legacy_bridge() is True
    assert cm_constants.tenant_allows_legacy_bridge("linas") is False


@pytest.mark.asyncio
async def test_generic_gym_tenant_zero_linas_leakage(monkeypatch: pytest.MonkeyPatch) -> None:
    """Restaurant/gym published path must not mention Linas/Marwa/Beirut/Antelias/legacy phones."""
    tenant_id = "acme-gym-e2e"
    banned = (
        "linas",
        "marwa",
        "beirut",
        "antelias",
        "tattoo",
        "laser",
        "khaled",
        "96170123456",
        "96171111111",
        "مروى",
        "ليناز",
    )
    await publish_test_content(
        tenant_id,
        {
            "ai_basics": AiBasics(
                assistant_name="FitBot",
                clinic_name="Acme Gym",
                identity_summary="Friendly gym assistant for Acme Gym only.",
            ).model_dump(mode="json"),
            "handoff": HandoffPolicy(
                contacts=[
                    HandoffContact(
                        id="main",
                        destination_type="whatsapp",
                        destination_value="+96176111222",
                        phone_e164="+96176111222",
                        label="Acme desk",
                    )
                ],
                matrix=[HandoffMatrixRow(id="row", contact_id="main", enabled=True)],
            ).model_dump(mode="json"),
            "off_days": OffDaysSection(
                timezone="UTC",
                rules=[OffDayRule(id="mon", kind="weekly", weekday=0, reason="Maintenance")],
            ).model_dump(mode="json"),
            "faq": {
                "items": [
                    {
                        "qa_group_id": "membership_fees",
                        "status": "active",
                        "source_language": "en",
                        "variants": [
                            {
                                "language": "en",
                                "question": "What are your membership fees?",
                                "answer": "Acme Gym monthly membership is 40 USD.",
                                "reviewed": True,
                            }
                        ],
                    }
                ]
            },
            "actions": ActionsSection().model_dump(mode="json"),
        },
    )

    from services.ai_setup.version_store import load_published_content
    from services.brain.faq_exact import find_exact_faq, load_faq_section

    _pointer, sections = load_published_content(tenant_id)
    identity = sections.get("ai_basics") or {}
    blob = " ".join(str(v) for v in identity.values()).lower()
    for token in banned:
        assert token not in blob, f"leakage token {token!r} in published identity"
    section = load_faq_section(tenant_id)
    hit = find_exact_faq(section, "What are your membership fees?")
    assert hit is not None
    reply = hit.answer.lower()
    assert "acme" in reply or "40" in reply
    for token in banned:
        assert token not in reply, f"leakage token {token!r} in FAQ reply"
    policy = HandoffPolicy.model_validate(sections.get("handoff") or {})
    resolved = resolve_handoff(policy)
    dest = (resolved.destination_value or "").lower()
    assert "96176111222" in dest.replace("+", "")
    for token in banned:
        assert token not in dest, f"leakage token {token!r} in handoff"
