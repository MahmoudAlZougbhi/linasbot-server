"""Comment stills must not be dumped into Tera/Luna JSON text."""

from __future__ import annotations

import json

from services.customer_reply_v2.answer_luna import build_answer_messages
from services.customer_reply_v2.comment_vision_payload import comment_context_for_text, strip_data_urls
from services.customer_reply_v2.models import EvidenceRecord
from services.customer_reply_v2.retrieval_tools import ToolContext, dispatch_retrieval_tool


def test_one_image_does_not_enter_json_text() -> None:
    huge = "A" * 80_000
    data_url = f"data:image/jpeg;base64,{huge}"
    msgs = build_answer_messages(
        message="What is this",
        fixed_context={"ai_basics": {"advanced_instructions": "x"}, "style": {"style_body": "y"}},
        evidence=[EvidenceRecord("services:s1", "services", "S", "body", "v1")],
        evidence_status="sufficient",
        customer_profile={},
        history_messages=[],
        comment_context={
            "caption": "laser underarm",
            "media_status": "available",
            "image_inputs": [{"url": data_url, "kind": "image"}],
        },
        channel="instagram_comment",
        published_revision="v1",
        response_language="en",
        detected_language="en",
    )
    text = msgs[1]["content"][0]["text"]
    assert huge not in text
    assert data_url not in text
    payload = json.loads(text)
    assert payload["comment_context"]["caption"] == "laser underarm"
    assert payload["comment_context"]["image_input_count"] == 1
    assert "image_inputs" not in payload["comment_context"]
    images = [part for part in msgs[1]["content"] if part.get("type") == "image_url"]
    assert len(images) == 1
    assert images[0]["image_url"]["url"].startswith("data:image/")


def test_comment_tool_omits_binary_stills() -> None:
    ctx = ToolContext(
        tenant_id="t1",
        published_revision="v1",
        channel="instagram_comment",
        comment_context={
            "caption": "offer",
            "image_inputs": [{"url": "data:image/jpeg;base64," + ("B" * 5000), "kind": "image"}],
        },
    )
    out = dispatch_retrieval_tool("get_comment_post_context", {}, ctx)
    dumped = json.dumps(out)
    assert "BBBBB" not in dumped
    assert out["data"]["caption"] == "offer"
    assert out["data"]["image_inputs_omitted"] is True


def test_compact_shrinks_large_jpeg() -> None:
    import base64
    import io

    from PIL import Image

    from services.customer_reply_v2.comment_vision_payload import compact_data_url

    image = Image.new("RGB", (2000, 2000), (255, 0, 0))
    buf = io.BytesIO()
    image.save(buf, format="JPEG", quality=95)
    raw = f"data:image/jpeg;base64,{base64.b64encode(buf.getvalue()).decode('ascii')}"
    out = compact_data_url(raw)
    assert out.startswith("data:image/jpeg;base64,")
    assert len(out) < len(raw) // 2


def test_strip_nested_data_urls() -> None:
    cleaned = strip_data_urls({"thumb": "data:image/png;base64,abc", "ok": "caption"})
    assert cleaned["ok"] == "caption"
    assert "[omitted]" in cleaned["thumb"]
    text_ctx = comment_context_for_text(
        {"caption": "x", "image_inputs": [{"url": "data:image/jpeg;base64,abc", "kind": "image"}]}
    )
    assert "image_inputs" not in text_ctx
    assert text_ctx["image_input_count"] == 1
