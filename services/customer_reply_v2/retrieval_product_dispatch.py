"""Product retrieval tool dispatch (tenant-scoped)."""

from __future__ import annotations

from typing import Any

PRODUCT_TOOL_NAMES = {
    "search_product_by_title",
    "list_product_titles",
    "get_product_details",
    "get_product_images",
    "find_product_by_url",
    "find_product_by_image",
    "get_active_product_context",
    "resolve_reply_to_product",
}


def dispatch_product_tool(name: str, args: dict[str, Any], ctx: Any) -> dict[str, Any]:
    from db.session import whatsapp_session
    from services.customer_reply_v2.flags import customer_ai_v10_runtime_enabled
    from services.products.crv2_tools import (
        crv2_find_product_by_image,
        crv2_find_product_by_url,
        crv2_get_active_product_context,
        crv2_get_product_details,
        crv2_get_product_images,
        crv2_list_product_titles,
        crv2_resolve_reply_to_product,
        crv2_search_product_by_title,
    )
    from services.products.media import load_media_bytes

    conversation_id = str(ctx.conversation_id or "").strip() or None
    try:
        with whatsapp_session(require=True) as db:
            if name == "resolve_reply_to_product":
                data = crv2_resolve_reply_to_product(
                    db,
                    tenant_id=ctx.tenant_id,
                    channel=ctx.channel,
                    reply_to_message_id=str(args.get("reply_to_message_id") or ctx.reply_to_message_id or ""),
                    conversation_id=conversation_id,
                )
                if data.get("match"):
                    ctx.active_product_id = str(data["match"].get("id") or "") or None
            elif name == "get_active_product_context":
                data = crv2_get_active_product_context(
                    db,
                    tenant_id=ctx.tenant_id,
                    conversation_id=conversation_id or "",
                )
                if data.get("active_product_id"):
                    ctx.active_product_id = str(data.get("active_product_id") or "") or None
            elif name == "search_product_by_title":
                alt_raw = args.get("alternate_queries") or args.get("queries") or []
                if isinstance(alt_raw, str):
                    alternate = [alt_raw]
                elif isinstance(alt_raw, list):
                    alternate = [str(q) for q in alt_raw if str(q).strip()]
                else:
                    alternate = []
                original_query = str(args.get("original_query") or args.get("title") or "").strip()
                data = crv2_search_product_by_title(
                    db,
                    tenant_id=ctx.tenant_id,
                    title=str(args.get("title") or original_query).strip(),
                    limit=int(args.get("limit") or 5),
                    use_luna_fallback=not customer_ai_v10_runtime_enabled(),
                    conversation_id=conversation_id,
                    title_offset=int(args.get("offset") or 0),
                    alternate_queries=alternate,
                    original_query=original_query,
                )
                ctx.product_search_attempted = True
                if int(data.get("match_count") or 0) > 0:
                    ctx.product_match_found = True
                elif not (data.get("titles_fallback") or {}).get("has_more"):
                    ctx.product_match_found = False
            elif name == "list_product_titles":
                data = crv2_list_product_titles(
                    db,
                    tenant_id=ctx.tenant_id,
                    offset=int(args.get("offset") or 0),
                    limit=int(args.get("limit") or 80),
                )
            elif name == "get_product_details":
                product_id = str(args.get("product_id") or ctx.active_product_id or "")
                data = crv2_get_product_details(
                    db,
                    tenant_id=ctx.tenant_id,
                    product_id=product_id,
                    conversation_id=conversation_id,
                    context_source="active_context",
                )
                _remember_product_evidence(ctx, data)
                if data.get("ok"):
                    ctx.product_match_found = True
            elif name == "get_product_images":
                product_id = str(args.get("product_id") or ctx.active_product_id or "")
                data = crv2_get_product_images(db, tenant_id=ctx.tenant_id, product_id=product_id)
            elif name == "find_product_by_url":
                data = crv2_find_product_by_url(
                    db,
                    tenant_id=ctx.tenant_id,
                    url=str(args.get("url") or ""),
                    conversation_id=conversation_id,
                )
                if data.get("match"):
                    ctx.active_product_id = str(data["match"].get("id") or "") or None
            else:
                media_id = str(args.get("image_media_id") or getattr(ctx, "inbound_image_media_id", "") or "").strip()
                raw = load_media_bytes(tenant_id=ctx.tenant_id, media_id=media_id)
                if raw is None:
                    data = {"tool": name, "ok": False, "error": "image_not_found"}
                else:
                    data = crv2_find_product_by_image(
                        db,
                        tenant_id=ctx.tenant_id,
                        image_bytes=raw,
                        top_k=int(args.get("top_k") or 8),
                        conversation_id=conversation_id,
                        known_title=str(args.get("product_name") or args.get("title") or ""),
                    )
                    if data.get("matches"):
                        first = data["matches"][0]
                        ctx.active_product_id = str(first.get("id") or "") or None
    except Exception as exc:
        ctx.audit.append({"tool": name, "ok": False, "class": "products", "error": type(exc).__name__})
        return {"ok": False, "error": "products_tool_failed", "message": type(exc).__name__}
    ctx.audit.append({"tool": name, "ok": True, "class": "products"})
    if ctx.active_product_id and name == "get_product_details":
        data["active_product_context"] = ctx.active_product_id
    return {"ok": True, "data": data}


def _remember_product_evidence(ctx: Any, data: dict[str, Any] | None) -> None:
    """Copy selected product details into Tera evidence. Luna tools are not Tera context."""
    import json

    from services.customer_reply_v2.models import EvidenceRecord

    if not isinstance(data, dict) or not data.get("ok"):
        return
    product = data.get("product")
    if not isinstance(product, dict):
        return
    product_id = str(product.get("id") or "").strip()
    if not product_id:
        return
    source_id = f"products:{product_id}"
    if any(getattr(row, "source_id", "") == source_id for row in (ctx.evidence_acc or [])):
        return
    ctx.evidence_acc.append(
        EvidenceRecord(
            source_id=source_id,
            section_id="products",
            title=str(product.get("name") or product.get("title") or source_id),
            content=json.dumps(product, ensure_ascii=False),
            published_revision=str(getattr(ctx, "published_revision", "") or ""),
        )
    )
