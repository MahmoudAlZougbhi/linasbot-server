"""LOC split: text_handlers_respond phases under 500 lines; public exports preserved."""

from __future__ import annotations

from pathlib import Path

from handlers.text_handlers_respond import _handle_published_cm_runtime, _process_and_respond


def _line_count(rel: str) -> int:
    return len(Path(rel).read_text(encoding="utf-8").splitlines())


def test_text_handlers_respond_modules_under_500_lines() -> None:
    root = Path("handlers")
    files = [root / "text_handlers_respond.py", *sorted(root.glob("text_handlers_respond_*.py"))]
    assert files
    for path in files:
        assert _line_count(str(path)) < 500, f"{path} is {_line_count(str(path))} lines"


def test_text_handlers_respond_preserves_public_api() -> None:
    parent_src = Path("handlers/text_handlers.py").read_text(encoding="utf-8")
    assert "from handlers.text_handlers_respond import" in parent_src or "text_handlers_respond" in parent_src
    assert callable(_process_and_respond)
    assert callable(_handle_published_cm_runtime)
