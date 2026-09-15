"""WAVE O6 leftovers: museum deletes folded; KEEP surfaces intact."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_o6_root_museum_prompt_and_resolver_folded() -> None:
    assert not (ROOT / "prompt_templates.py").exists()
    assert not (ROOT / "utils/utils_prompt.py").exists()
    assert not (ROOT / "language_resolver.py").exists()
    assert not (ROOT / "language_resolver_signals.py").exists()
    assert not (ROOT / "language_resolver_text.py").exists()
    assert (ROOT / "services/brain/language_resolver.py").is_file()
    assert (ROOT / "services/brain/language_resolver_signals.py").is_file()
    assert (ROOT / "services/brain/language_resolver_text.py").is_file()
    assert not (ROOT / "services/brain/shadow.py").exists()
    assert not (ROOT / "docs/FINAL_CLEANUP_VERIFY.md").exists()


def test_o6_business_scope_guard_renamed_not_removed() -> None:
    keywords = (ROOT / "services/brain/inbound/text_handlers_respond_keywords.py").read_text(encoding="utf-8")
    intent = (ROOT / "services/brain/inbound/text_handlers_respond_intent.py").read_text(encoding="utf-8")
    phase2 = (ROOT / "services/brain/inbound/text_handlers_respond_phase2.py").read_text(encoding="utf-8")
    assert "BUSINESS_SCOPE_KEYWORDS" in keywords
    assert "CLINIC_SCOPE_KEYWORDS" not in keywords
    assert "_is_out_of_business_scope_query" in intent
    assert "_is_out_of_clinic_scope_query" not in intent
    assert "_is_out_of_business_scope_query" in phase2
    assert "OFF_TOPIC_KEYWORDS" in keywords


def test_o6_keep_surfaces_intact() -> None:
    assert (ROOT / "docs/KEEP_SURFACE.md").is_file()
    assert (ROOT / "docs/BACKEND_ENV.md").is_file()
    assert (ROOT / "modules/local_qa_api.py").is_file()
    assert (ROOT / "services/saas_no_boc.py").is_file()
    billing = (ROOT / "services/billing/iap_product_catalog.py").read_text(encoding="utf-8")
    assert "com.linasai.credits." in billing
    constants = (ROOT / "services/ai_setup/constants.py").read_text(encoding="utf-8")
    assert "brain_temporary_error" in constants
    assert "CM_DISABLE_LEGACY_BRIDGE" in constants
