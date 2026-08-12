"""Residual PII print redaction: source must not log full phones/message bodies."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Full-phone / message-body patterns that must not appear in print f-strings.
_FORBIDDEN_SNIPPETS = (
    "phone={phone_clean}",
    "phone={phone}",
    "phone={customer_phone}",
    "Stored phone_number {phone_number}",
    "Customer: {customer_name} ({customer_phone})",
    "normalized_input: '{user_input_to_process",
    "text: {message_text}",
    "Parsed simple format: {parsed_message}",
    "Answer: {qa_response[:100]}",
)

_SCAN_GLOBS = (
    "handlers/**/*.py",
    "services/**/*.py",
    "modules/**/*.py",
)


def test_handlers_services_modules_print_strings_mask_phone_and_message_bodies() -> None:
    hits: list[str] = []
    for glob in _SCAN_GLOBS:
        for path in ROOT.glob(glob):
            if not path.is_file():
                continue
            text = path.read_text(encoding="utf-8")
            for snippet in _FORBIDDEN_SNIPPETS:
                if snippet in text:
                    hits.append(f"{path.relative_to(ROOT)}: {snippet!r}")
    assert not hits, "unredacted PII print patterns remain:\n" + "\n".join(hits)


def test_text_handlers_message_still_excludes_sec047_debug_patterns() -> None:
    source = (ROOT / "handlers/text_handlers_message.py").read_text(encoding="utf-8")
    for pattern in (
        "phone_number from user_data",
        "phone_number from config",
        "raw_msg preview",
        "HANDLE_MESSAGE: About to save USER message",
    ):
        assert pattern not in source
