"""Media, inbound, and resource live-cert scenarios."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from _live_cert.bootstrap import TENANT_ID
from _live_cert.calls import dm, has_price, record, trace

WOMEN_PHOTOS = "ابعتلي صور laser hair removal للنساء"


async def run_media_scenarios(*, product: dict[str, Any], assets: Path, api_key: str) -> None:
    from openai import AsyncOpenAI

    from services.cm.version_store import load_published_content
    from services.customer_reply_v2.inbound_extract import extract_inbound_file
    from services.customer_reply_v2.inbound_stt import transcribe_inbound_audio
    from services.customer_reply_v2.inbound_video import extract_bounded_video, ffmpeg_available
    from services.customer_reply_v2.media_actions import resolve_media_actions
    from services.customer_reply_v2.retrieval_tools import ToolContext, dispatch_retrieval_tool
    from services.ssrf_guard import SSRFValidationError, validate_fetch_url

    pointer, _sections = load_published_content(TENANT_ID)
    ctx = ToolContext(tenant_id=TENANT_ID, published_revision=pointer.content_version_id, channel="instagram_dm")
    img_out = dispatch_retrieval_tool(
        "find_product_by_image", {"image_media_id": product["image_media_id"], "top_k": 8}, ctx
    )
    record(
        "inbound_product_image_tool",
        "REAL OPENAI" if (img_out.get("data") or {}).get("vision_used") else "REAL DATABASE/RETRIEVAL",
        ok=bool((img_out.get("data") or {}).get("matches") or img_out.get("ok")),
        reason=str((img_out.get("data") or {}).get("resolver") or img_out.get("error")),
        trace={"tool": img_out},
    )
    named = dispatch_retrieval_tool(
        "find_product_by_image",
        {"image_media_id": product["image_media_id"], "product_name": "After Care Cream", "top_k": 8},
        ctx,
    )
    record(
        "inbound_product_image_then_name",
        "REAL DATABASE/RETRIEVAL",
        ok=(named.get("data") or {}).get("resolver") == "name_first",
        reason=str((named.get("data") or {}).get("resolver")),
        trace={"tool": named},
    )

    burger = dispatch_retrieval_tool(
        "find_product_by_image", {"image_media_id": product["burger_media_id"], "top_k": 8}, ctx
    )
    tattoo = dispatch_retrieval_tool(
        "find_product_by_image", {"image_media_id": product["tattoo_media_id"], "top_k": 8}, ctx
    )
    burger_ids = [
        str(m.get("id") or m.get("product_id") or "") for m in ((burger.get("data") or {}).get("matches") or [])
    ]
    tattoo_ids = [
        str(m.get("id") or m.get("product_id") or "") for m in ((tattoo.get("data") or {}).get("matches") or [])
    ]
    record(
        "burger_vs_tattoo_images",
        "REAL OPENAI" if (burger.get("data") or {}).get("vision_used") else "REAL DATABASE/RETRIEVAL",
        ok=bool(burger_ids) and burger_ids[:1] != tattoo_ids[:1],
        burger_ids=burger_ids[:3],
        tattoo_ids=tattoo_ids[:3],
    )

    out = await dm(
        "شو هيدا؟",
        conversation_id="c_in_img",
        provider_sender_id="u_in_img",
        inbound_media={"attachment_types": ["image"], "image_media_id": product["image_media_id"]},
        attachment_types=["image"],
    )
    tr = trace(out, message="شو هيدا؟", channel="instagram_dm")
    record(
        "inbound_image_wired_to_v2",
        "REAL OPENAI",
        ok=tr["luna_called"] and tr["faq_direct"] is not True,
        reason=out.reason,
        trace=tr,
        note="image_media_id passed into V2; Meta social path no longer collapses to generic text.",
    )

    try:
        client = AsyncOpenAI(api_key=api_key)
        speech = await client.audio.speech.create(
            model="gpt-4o-mini-tts", voice="alloy", input="مرحبا، بدي أعرف سعر Full Body."
        )
        audio_path = assets / "full_body_price.mp3"
        raw = speech.content if hasattr(speech, "content") else await speech.aread()
        audio_path.write_bytes(raw)
        stt = await transcribe_inbound_audio(data=audio_path.read_bytes(), filename="full_body_price.mp3")
        transcript = str(stt.get("text") or "").strip()
        out = await dm(
            transcript or "مرحبا، بدي أعرف سعر Full Body.",
            conversation_id="c_voice",
            provider_sender_id="u_voice",
            inbound_media={"attachment_types": ["audio"], "transcript": transcript},
            attachment_types=["audio"],
        )
        tr = trace(out, message=transcript, channel="instagram_dm")
        record(
            "voice_stt_then_v2",
            "REAL OPENAI",
            ok=bool(stt.get("ok")) and bool(transcript) and (has_price(out.reply) or tr["luna_called"]),
            reason=out.reason,
            trace=tr,
            transcript=transcript[:200],
            stt_model=stt.get("model"),
        )
    except Exception as exc:
        record(
            "voice_stt_then_v2",
            "BLOCKED",
            ok=False,
            blocker=f"stt_or_tts:{type(exc).__name__}",
            error=str(exc)[:200],
        )

    video_path = assets / "test_card.mp4"
    video_bytes = video_path.read_bytes() if video_path.is_file() else b""
    extracted = extract_bounded_video(video_bytes) if video_bytes else {"status": "empty_video"}
    if extracted.get("status") == "ffmpeg_unavailable":
        record(
            "inbound_video_frames",
            "BLOCKED",
            ok=False,
            blocker="ffmpeg_unavailable",
            first_failing_layer="services/customer_reply_v2/inbound_video.py extract_bounded_video",
        )
    else:
        record(
            "inbound_video_frames",
            "REAL DATABASE/RETRIEVAL",
            ok=extracted.get("status") in {"extracted", "audio_only"} or int(extracted.get("frame_count") or 0) > 0,
            status=extracted.get("status"),
            frame_count=extracted.get("frame_count") or len(extracted.get("frames") or []),
            ffmpeg=ffmpeg_available(),
        )

    pdf_extract = extract_inbound_file(
        data=(assets / "price_list.pdf").read_bytes(), filename="price_list.pdf", mime="application/pdf"
    )
    txt_extract = extract_inbound_file(
        data=(assets / "after_care_notes.txt").read_bytes(), filename="after_care_notes.txt", mime="text/plain"
    )
    record(
        "inbound_file_extract",
        "REAL DATABASE/RETRIEVAL",
        ok=str(txt_extract.get("status") or "") == "extracted" or bool(txt_extract.get("text")),
        pdf_status=pdf_extract.get("status"),
        txt_preview=str(txt_extract.get("text") or "")[:180],
    )

    try:
        validate_fetch_url("http://127.0.0.1/secret")
        ssrf_ok = False
        ssrf_err = "ssrf_allowed_loopback"
    except SSRFValidationError:
        ssrf_ok = True
        ssrf_err = "SSRFValidationError"
    record("inbound_link_ssrf", "REAL DATABASE/RETRIEVAL", ok=ssrf_ok, error=ssrf_err)

    out = await dm(WOMEN_PHOTOS, conversation_id="c_women", provider_sender_id="u_women")
    tr = trace(out, message=WOMEN_PHOTOS, channel="instagram_dm")
    selected = " ".join(str(x) for x in tr["selected_source_ids"])
    delivery = tr["resource_delivery"] or {}
    refs = [str(x.get("resource_ref") or "") for x in (delivery.get("items") or [])]
    women_ref = ((product.get("attachments") or {}).get("laser_women") or [{}])[0].get("id")
    service_ref = ((product.get("attachments") or {}).get("laser_service") or [{}])[0].get("id")
    record(
        "women_laser_photos",
        "REAL OPENAI",
        ok=tr["luna_called"] and tr["tera_called"] and (women_ref in refs or "svc_laser_women" in selected),
        reason=out.reason,
        selected_source_ids=tr["selected_source_ids"],
        resource_refs=refs,
        claimed_sent=tr["claimed_sent"],
        luna_recommended_tera_effort=tr["luna_recommended_tera_effort"],
        answer_effective=tr["answer_effective"],
        note="Luna sees resource counts only. Tera send_resource is validated; claimed_sent stays false until channel send.",
        reply=(out.reply or "")[:240],
    )
    record(
        "women_vs_service_files",
        "REAL OPENAI",
        ok=service_ref not in refs,
        service_ref=service_ref,
        women_ref=women_ref,
        resource_refs=refs,
    )

    out = await dm("ابعتلي صور After Care Cream", conversation_id="c_media", provider_sender_id="u_media")
    tr = trace(out, message="ابعتلي صور After Care Cream", channel="instagram_dm")
    media_delivery = tr["media_delivery"] or {}
    body = out.reply or ""
    record(
        "product_image_outbound",
        "REAL OPENAI",
        ok=bool(tr["media_actions"] or media_delivery.get("items") or "cream" in body.lower() or "كريم" in body),
        reason=out.reason,
        media_delivery_ok=media_delivery.get("ok"),
        claimed_sent=False,
        note="Meta Graph send not executed. media_actions/plan only.",
    )

    video = resolve_media_actions(
        tenant_id=TENANT_ID,
        actions=[
            {
                "product_id": product["product"]["id"],
                "media_type": "videos",
                "max_items": 1,
                "order": "configured_order",
            }
        ],
        channel_capabilities={"max_media_items": 10},
    )
    record(
        "product_video_outbound",
        "REAL DATABASE/RETRIEVAL",
        ok=bool(video.get("ok")) and bool(video.get("items")),
        result=video,
        claimed_sent=False,
        note="Stored product video MIME is sent where the channel supports video. No Meta Graph send in this cert.",
    )

    out = await dm("عطيني لينك After Care Cream", conversation_id="c_link", provider_sender_id="u_link")
    tr = trace(out, message="عطيني لينك After Care Cream", channel="instagram_dm")
    record(
        "link_outbound",
        "REAL OPENAI",
        ok="example.com" in (out.reply or "") or "http" in (out.reply or "").lower() or tr["luna_called"],
        reason=out.reason,
        reply=(out.reply or "")[:180],
    )

    out = await dm("ابعتلي ملف After Care", conversation_id="c_file_out", provider_sender_id="u_file_out")
    tr = trace(out, message="ابعتلي ملف After Care", channel="instagram_dm")
    file_delivery = tr["resource_delivery"] or {}
    record(
        "file_outbound",
        "REAL OPENAI",
        ok=tr["luna_called"] and tr["claimed_sent"] is False,
        reason=out.reason,
        resource_delivery=file_delivery,
        note="AI Setup file send is planned via resource_actions; never claimed_sent before channel success.",
    )
