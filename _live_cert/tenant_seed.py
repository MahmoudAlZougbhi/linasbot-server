"""SQLite, synthetic assets, products, and request graphs for live cert."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine, event

from _live_cert.bootstrap import ASSETS, TENANT_ID
from _live_cert.tenant_sections import APPT_SOURCE, ORDER_SOURCE, _att


def init_sqlite(db_url: str) -> None:
    from db.models import Base
    from db.session import reset_engine_for_tests

    reset_engine_for_tests()
    engine = create_engine(db_url, future=True)

    @event.listens_for(engine, "connect")
    def _fk(dbapi_conn, _connection_record):  # type: ignore[no-untyped-def]
        dbapi_conn.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)


def _png(path: Path, color: tuple[int, int, int], lines: list[str]) -> Path:
    from PIL import Image, ImageDraw, ImageFont

    im = Image.new("RGB", (640, 360), color)
    draw = ImageDraw.Draw(im)
    font = ImageFont.load_default()
    draw.rectangle((24, 24, 616, 336), outline=(240, 240, 240), width=4)
    y = 120
    for line in lines:
        draw.text((60, y), line, fill=(255, 255, 255), font=font)
        y += 36
    im.save(path, format="PNG")
    return path


def _tiny_mp4(path: Path) -> Path:
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg:
        cmd = [
            ffmpeg,
            "-y",
            "-f",
            "lavfi",
            "-i",
            "color=c=teal:s=320x240:d=2",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:duration=2",
            "-shortest",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            str(path),
        ]
        try:
            subprocess.run(cmd, check=True, capture_output=True, timeout=30)
            if path.is_file() and path.stat().st_size > 64:
                return path
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError):
            pass
    path.write_bytes(b"\x00\x00\x00\x18ftypmp42\x00\x00\x00\x00mp42mp41" + b"\x00" * 256)
    return path


def make_assets() -> dict[str, Path]:
    cream = _png(
        ASSETS / "after_care_cream.png",
        (20, 40, 70),
        ["V10 TEST STORE", "After Care Cream $19", "NO REAL PERSON"],
    )
    women = _png(
        ASSETS / "laser_women.png",
        (80, 30, 60),
        ["Women Laser Hair Removal", "Photos for women only", "NO REAL PERSON"],
    )
    burger = _png(ASSETS / "burger.png", (140, 70, 20), ["BURGER TEST IMAGE", "NOT A PERSON"])
    tattoo = _png(ASSETS / "tattoo.png", (30, 30, 30), ["TATTOO TEST IMAGE", "NOT A PERSON"])
    pdf_path = ASSETS / "price_list.pdf"
    pdf_path.write_bytes(
        b"%PDF-1.1\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
        b"2 0 obj<</Type/Pages/Count 1/Kids[3 0 R]>>endobj\n"
        b"3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 200 200]>>endobj\n"
        b"trailer<</Root 1 0 R>>\n%%EOF\n"
    )
    txt_path = ASSETS / "after_care_notes.txt"
    txt_path.write_text("V10 test file: After Care Cream is in stock. Small/Large. White. $19.\n", encoding="utf-8")
    service_txt = ASSETS / "laser_service_notes.txt"
    service_txt.write_text(
        "Laser Hair Removal Service file. Staff protocol only. Not women photos.\n", encoding="utf-8"
    )
    video = _tiny_mp4(ASSETS / "test_card.mp4")
    return {
        "cream": cream,
        "women": women,
        "burger": burger,
        "tattoo": tattoo,
        "pdf": pdf_path,
        "txt": txt_path,
        "service_txt": service_txt,
        "video": video,
    }


def _store_cm(*, filename: str, content: bytes, content_type: str) -> dict[str, Any]:
    from services.cm.article_media import store_article_media

    return store_article_media(
        tenant_id=TENANT_ID,
        user_id="v10cert",
        filename=filename,
        content=content,
        content_type=content_type,
    )


def _store_product(*, filename: str, content: bytes, content_type: str) -> dict[str, Any]:
    from services.products.media import store_product_media

    return store_product_media(
        tenant_id=TENANT_ID,
        user_id="v10cert",
        filename=filename,
        content=content,
        content_type=content_type,
    )


def seed_catalog(assets: dict[str, Path]) -> dict[str, Any]:
    from db.session import whatsapp_session
    from services.products.schemas import ProductWriteBody
    from services.products.service import ProductsService

    cream_img = _store_product(
        filename="after_care_cream.png", content=assets["cream"].read_bytes(), content_type="image/png"
    )
    cream_vid = _store_product(filename="test_card.mp4", content=assets["video"].read_bytes(), content_type="video/mp4")
    burger_img = _store_product(filename="burger.png", content=assets["burger"].read_bytes(), content_type="image/png")
    tattoo_img = _store_product(filename="tattoo.png", content=assets["tattoo"].read_bytes(), content_type="image/png")
    women_img = _store_cm(filename="laser_women.png", content=assets["women"].read_bytes(), content_type="image/png")
    service_file = _store_cm(
        filename="laser_service_notes.txt", content=assets["service_txt"].read_bytes(), content_type="text/plain"
    )
    pdf_media = _store_cm(filename="price_list.pdf", content=assets["pdf"].read_bytes(), content_type="application/pdf")
    txt_media = _store_cm(
        filename="after_care_notes.txt", content=assets["txt"].read_bytes(), content_type="text/plain"
    )
    with whatsapp_session(require=True) as session:
        svc = ProductsService(session)
        cream = svc.create_product(
            tenant_id=TENANT_ID,
            body=ProductWriteBody(
                name="After Care Cream",
                price="19 USD",
                sizes=["Small", "Large"],
                colors=["White"],
                note="In stock. Test catalog only.",
                availability="in_stock",
                images=[
                    {"media_id": cream_img["media_id"], "sort_order": 0},
                    {"media_id": cream_vid["media_id"], "sort_order": 1},
                ],
                links=[
                    {"url": "https://example.com/v10-live-cert-cream", "label": "Test product page", "sort_order": 0}
                ],
            ),
        )
        burger = svc.create_product(
            tenant_id=TENANT_ID,
            body=ProductWriteBody(
                name="Burger Demo",
                price="0",
                note="Synthetic burger image only.",
                images=[{"media_id": burger_img["media_id"], "sort_order": 0}],
            ),
        )
        tattoo = svc.create_product(
            tenant_id=TENANT_ID,
            body=ProductWriteBody(
                name="Tattoo Demo",
                price="0",
                note="Synthetic tattoo image only.",
                images=[{"media_id": tattoo_img["media_id"], "sort_order": 0}],
            ),
        )
    return {
        "product": cream,
        "burger": burger,
        "tattoo": tattoo,
        "image_media_id": cream_img["media_id"],
        "video_media_id": cream_vid["media_id"],
        "burger_media_id": burger_img["media_id"],
        "tattoo_media_id": tattoo_img["media_id"],
        "attachments": {
            "laser_women": [
                _att(
                    id=women_img["media_id"],
                    kind="image",
                    title="Women Laser Hair Removal photos",
                    description="Before and after photos for women laser hair removal only",
                    mime="image/png",
                    filename="laser_women.png",
                    size=int(women_img.get("size") or 0),
                )
            ],
            "laser_service": [
                _att(
                    id=service_file["media_id"],
                    kind="file",
                    title="Laser Hair Removal Service file",
                    description="Staff protocol file, not customer women photos",
                    mime="text/plain",
                    filename="laser_service_notes.txt",
                    size=int(service_file.get("size") or 0),
                )
            ],
            "cream_files": [
                _att(
                    id=pdf_media["media_id"],
                    kind="file",
                    title="After Care price list",
                    description="PDF price list for After Care Cream",
                    mime="application/pdf",
                    filename="price_list.pdf",
                    size=int(pdf_media.get("size") or 0),
                )
            ],
            "comment_rule": [
                _att(
                    id=txt_media["media_id"],
                    kind="file",
                    title="Static comment file",
                    description="Deterministic comment-rule resource",
                    mime="text/plain",
                    filename="after_care_notes.txt",
                    size=int(txt_media.get("size") or 0),
                )
            ],
        },
        "txt_media": txt_media,
        "pdf_media": pdf_media,
    }


def seed_graphs() -> dict[str, Any]:
    from db.session import whatsapp_session
    from services.request_graphs.service import publish_graph

    with whatsapp_session(require=True) as db:
        appt = publish_graph(
            db,
            tenant_id=TENANT_ID,
            source_item_id="req_full_body",
            title="موعد Full Body",
            source_text=APPT_SOURCE,
            destination="APPOINTMENT",
            confirm=True,
        )
        order = publish_graph(
            db,
            tenant_id=TENANT_ID,
            source_item_id="req_cream",
            title="طلب After Care Cream",
            source_text=ORDER_SOURCE,
            destination="ORDER",
            confirm=True,
        )
    return {"appointment": appt, "order": order}


def grant_test_credits() -> dict[str, Any]:
    from services.credit_ledger_service import credit_ledger_service
    from services.token_wallet_service import token_wallet_service

    ledger = credit_ledger_service.grant_pack(
        tenant_id=TENANT_ID,
        credits=5000,
        request_id="v10-live-cert-pack",
        source="v10_live_cert",
        meta={"isolated": True},
    )
    wallet = token_wallet_service.credit(
        TENANT_ID,
        input_tokens=2_000_000,
        output_tokens=2_000_000,
        reason="v10_live_cert",
        reference="v10-live-cert-wallet",
    )
    return {"ledger": ledger, "wallet_ok": True, "wallet_input": wallet.input_remaining}
