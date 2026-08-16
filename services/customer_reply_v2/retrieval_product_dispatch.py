"""Product retrieval tool dispatch (tenant-scoped)."""

from __future__ import annotations

from typing import Any

PRODUCT_TOOL_NAMES = {
    "search_product_by_title",
    "get_product_details",
    "get_product_images",
    "find_product_by_url",
    "find_product_by_image",
    "get_active_product_context",
    "resolve_reply_to_product",
}


def dispatch_product_tool(name: str, args: dict[str, Any], ctx: Any) -> dict[str, Any]:
    from db.session import whatsapp_session
    from services.products.crv2_tools import (
        crv2_find_product_by_image,
        crv2_find_product_by_url,
        crv2_get_active_product_context,
        crv2_get_product_details,
        crv2_get_product_images,
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
                data = crv2_search_product_by_title(
                    db,
                    tenant_id=ctx.tenant_id,
                    title=str(args.get("title") or "").strip(),
                    limit=int(args.get("limit") or 5),
                    use_luna_fallback=True,
                    conversation_id=conversation_id,
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
                media_id = str(args.get("image_media_id") or "").strip()
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
