"""Owner attachment MIME + prompt packing so Sol sees file bytes."""

from __future__ import annotations

from pathlib import Path

from services.owner_copilot_v2.attachment_prompt import user_content_with_attachments
from services.owner_copilot_v2.attachments import store_attachment, validate_upload


def test_validate_upload_accepts_documents_and_rejects_exe() -> None:
    assert validate_upload(filename="n.pdf", content_type="application/pdf", size=20)["ok"] is True
    assert validate_upload(filename="n.txt", content_type="text/plain", size=20)["ok"] is True
    assert validate_upload(filename="n.csv", content_type="text/csv", size=20)["ok"] is True
    assert (
        validate_upload(
            filename="n.docx",
            content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            size=20,
        )["ok"]
        is True
    )
    assert validate_upload(filename="n.csv", content_type="application/octet-stream", size=20)["ok"] is True
    assert validate_upload(filename="x.exe", content_type="application/octet-stream", size=20)["ok"] is False


def test_user_message_includes_txt_body(tmp_path: Path, monkeypatch) -> None:
    import services.owner_copilot_v2.attachments as att

    monkeypatch.setattr(att, "_root", lambda: tmp_path / "owner_attachments")
    stored = store_attachment(
        tenant_id="t1",
        user_id="u1",
        filename="notes.txt",
        content=b"Salon hours are 9 to 5.",
        content_type="text/plain",
    )
    assert stored["ok"] is True
    content = user_content_with_attachments(
        tenant_id="t1",
        user_text="Please analyze this.",
        attachment_ids=[stored["attachment_id"]],
    )
    assert isinstance(content, str)
    assert "Salon hours are 9 to 5." in content
    assert stored["attachment_id"] in content
    assert "notes.txt" in content


def test_user_message_inlines_image_bytes(tmp_path: Path, monkeypatch) -> None:
    import services.owner_copilot_v2.attachments as att

    monkeypatch.setattr(att, "_root", lambda: tmp_path / "owner_attachments")
    stored = store_attachment(
        tenant_id="t1",
        user_id="u1",
        filename="shot.jpg",
        content=b"\xff\xd8\xff" + b"1" * 40,
        content_type="image/jpeg",
    )
    assert stored["ok"] is True
    content = user_content_with_attachments(
        tenant_id="t1",
        user_text="What is this?",
        attachment_ids=[stored["attachment_id"]],
    )
    assert isinstance(content, list)
    assert content[0]["type"] == "text"
    assert content[1]["type"] == "image_url"
    assert str(content[1]["image_url"]["url"]).startswith("data:image/jpeg;base64,")
