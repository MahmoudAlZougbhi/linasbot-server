"""LOC split: utils.py siblings under 500 lines; public exports and Qiscus identity preserved."""

from __future__ import annotations

from pathlib import Path

from utils.utils import (
    get_firestore_db,
    get_openai_tools_schema,
    save_conversation_message_to_firestore,
)


def _line_count(rel: str) -> int:
    return len(Path(rel).read_text(encoding="utf-8").splitlines())


def test_utils_modules_under_500_lines() -> None:
    files = [Path("utils/utils.py"), *sorted(Path("utils").glob("utils_*.py"))]
    assert files
    for path in files:
        assert _line_count(str(path)) < 500, f"{path} is {_line_count(str(path))} lines"


def test_utils_preserves_public_api() -> None:
    assert callable(get_firestore_db)
    assert callable(save_conversation_message_to_firestore)
    assert callable(get_openai_tools_schema)
    tools = get_openai_tools_schema()
    assert len(tools) == 29
    assert tools[0]["function"]["name"] == "update_customer_profile"
    assert tools[-1]["function"]["name"] == "create_customer"


def test_utils_keeps_qiscus_room_id_identity() -> None:
    identity = Path("utils/utils_identity.py").read_text(encoding="utf-8")
    save = Path("utils/utils_conversation_save.py").read_text(encoding="utf-8")
    assert "Qiscus" in identity
    assert "room_id" in identity
    assert "Qiscus" in save
    assert "room_id" in save
