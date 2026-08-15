from __future__ import annotations

import logging

from services.meta_controlled_evidence import log_meta_controlled_evidence, meta_evidence_surface


def test_surface_mapping_is_closed_and_does_not_reflect_unknown_input() -> None:
    assert meta_evidence_surface(kind="meta_dm", channel="facebook") == "facebook_dm"
    assert meta_evidence_surface(kind="meta_dm", channel="instagram") == "instagram_dm"
    assert meta_evidence_surface(kind="meta_comment", channel="facebook") == "facebook_comment"
    assert meta_evidence_surface(kind="meta_comment", channel="instagram") == "instagram_comment"
    assert meta_evidence_surface(kind="provider-secret", channel="customer content") is None


def test_valid_marker_contains_only_fixed_fields_and_stable_event_hash(caplog) -> None:
    logger = logging.getLogger("test.meta-evidence.valid")
    event_id = "ibe_" + "a" * 40

    with caplog.at_level(logging.INFO, logger=logger.name):
        assert (
            log_meta_controlled_evidence(
                logger,
                event_id=event_id,
                surface="instagram_dm",
                outcome="provider_accepted",
            )
            is True
        )

    assert caplog.messages == [
        f"[meta-evidence-v2] event surface=instagram_dm outcome=provider_accepted event_id={event_id}"
    ]


def test_invalid_marker_is_fully_redacted(caplog) -> None:
    logger = logging.getLogger("test.meta-evidence.invalid")
    raw_provider_id = "17890000000000000"
    raw_content = "private customer comment"
    malicious_event = f"ibe_bad\nprovider_id={raw_provider_id} content={raw_content}"

    with caplog.at_level(logging.WARNING, logger=logger.name):
        assert (
            log_meta_controlled_evidence(
                logger,
                event_id=malicious_event,
                surface="instagram_dm",
                outcome="provider_accepted",
            )
            is False
        )

    rendered = "\n".join(caplog.messages)
    assert rendered == "[meta-evidence-v2] marker_rejected reason=invalid_fixed_field"
    assert raw_provider_id not in rendered
    assert raw_content not in rendered
    assert "ibe_bad" not in rendered
