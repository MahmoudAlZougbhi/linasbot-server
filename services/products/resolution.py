"""Product resolution priority — server-enforced order before Luna/image."""

from __future__ import annotations

import asyncio
import re
from typing import Any
from urllib.parse import urlparse

from sqlalchemy.orm import Session

from services.products.active_context import get_active_product
from services.products.availability import is_customer_searchable
from services.products.reply_to_map import resolve_reply_to_product
from services.products.repository import ProductsRepository
from services.products.schemas import product_to_dict
from services.products.search import search_product_by_title_with_scores

_URL_RE = re.compile(r"https?://\S+|www\.\S+", re.IGNORECASE)


def _normalize_url(url: str) -> str:
    text = str(url or "").strip().lower()
    if not text:
        return ""
    parsed = urlparse(text if "://" in text else f"https://{text}")
    host = (parsed.netloc or "").removeprefix("www.")
    path = (parsed.path or "").rstrip("/")
    return f"{host}{path}"


def extract_url_from_text(text: str) -> str | None:
    match = _URL_RE.search(str(text or ""))
    if not match:
        return None
    return match.group(0).strip().rstrip(".,);]")


def extract_product_name_hint(text: str) -> str | None:
    """Heuristic: non-URL text that looks like a product name query."""
    raw = str(text or "").strip()
    if not raw:
        return None
    without_urls = _URL_RE.sub(" ", raw).strip()
    cleaned = re.sub(r"\s+", " ", without_urls).strip()
    if len(cleaned) < 2:
        return None
    # Skip pure greetings / very short noise.
    if len(cleaned.split()) == 1 and len(cleaned) < 4:
        return None
    return cleaned


def resolve_product_priority(
    session: Session,
    *,
    tenant_id: str,
    message: str,
    channel: str,
    conversation_id: str | None = None,
    reply_to_message_id: str | None = None,
    image_bytes: bytes | None = None,
    use_luna_fallback: bool = True,
) -> dict[str, Any]:
    """Apply resolution priority: name → reply-to → URL → context → image → Luna."""
    from services.products.crv2_tools import crv2_find_product_by_image
    from services.products.luna_title_resolver import resolve_product_titles_with_luna

    result: dict[str, Any] = {
        "resolver": None,
        "match": None,
        "matches": [],
        "ambiguous": False,
        "conflict": None,
    }

    name_hint = extract_product_name_hint(message)
    url_hint = extract_url_from_text(message)

    name_matches: list[dict[str, Any]] = []
    if name_hint:
        scored = search_product_by_title_with_scores(session, tenant_id=tenant_id, title=name_hint, limit=5)
        name_matches = [product for _, product in scored]

    url_match: dict[str, Any] | None = None
    if url_hint:
        row = ProductsRepository(session).find_by_link_url(
            tenant_id=tenant_id,
            normalized_url=_normalize_url(url_hint),
        )
        if row is not None and is_customer_searchable(row.availability):
            url_match = product_to_dict(row)

    # Conflict: clear name + different URL product → ask clarification.
    if name_matches and url_match:
        name_id = str(name_matches[0].get("id") or "")
        url_id = str(url_match.get("id") or "")
        if name_id and url_id and name_id != url_id:
            result.update(
                resolver="conflict",
                conflict={"name_match": name_matches[0], "url_match": url_match},
                matches=[name_matches[0], url_match],
                ambiguous=True,
            )
            return result

    # 1. Clear explicit product name → name search first.
    if name_matches:
        if len(name_matches) == 1:
            result.update(resolver="title_search", match=name_matches[0], matches=name_matches)
            return result
        result.update(resolver="title_search", matches=name_matches, ambiguous=True)
        return result

    # 2. Reply-to known product message (0 credits).
    if reply_to_message_id:
        product_id = resolve_reply_to_product(
            session,
            tenant_id=tenant_id,
            channel=channel,
            reply_to_message_id=reply_to_message_id,
        )
        if product_id:
            row = ProductsRepository(session).get_product(tenant_id=tenant_id, product_id=product_id)
            if row is not None and is_customer_searchable(row.availability):
                match = product_to_dict(row)
                result.update(resolver="reply_to", match=match, matches=[match])
                return result

    # 3. Registered URL (0 credits).
    if url_match:
        result.update(resolver="url_match", match=url_match, matches=[url_match])
        return result

    # 4. Active product context.
    if conversation_id:
        ctx = get_active_product(session, tenant_id=tenant_id, conversation_id=conversation_id)
        if ctx:
            row = ProductsRepository(session).get_product(
                tenant_id=tenant_id,
                product_id=str(ctx.get("active_product_id") or ""),
            )
            if row is not None and is_customer_searchable(row.availability):
                match = product_to_dict(row)
                result.update(resolver="active_context", match=match, matches=[match])
                return result

    # 5. Image matching (only if name failed / no clear name).
    if image_bytes and not name_matches:
        image_hit = crv2_find_product_by_image(
            session,
            tenant_id=tenant_id,
            image_bytes=image_bytes,
            conversation_id=conversation_id,
        )
        matches = list(image_hit.get("matches") or [])
        if image_hit.get("matches") and not image_hit.get("ambiguous"):
            result.update(
                resolver=image_hit.get("resolver") or "image_match",
                match=matches[0] if matches else None,
                matches=matches,
            )
            return result
        if matches:
            result.update(
                resolver="image_match",
                matches=matches,
                ambiguous=bool(image_hit.get("ambiguous")),
            )
            return result

    # 6. Luna only when local name search fails.
    if use_luna_fallback and name_hint:
        try:
            asyncio.get_running_loop()
            from concurrent.futures import ThreadPoolExecutor

            with ThreadPoolExecutor(max_workers=1) as pool:
                luna_matches = pool.submit(
                    asyncio.run,
                    resolve_product_titles_with_luna(session, tenant_id=tenant_id, query=name_hint),
                ).result(timeout=45)
        except RuntimeError:
            luna_matches = asyncio.run(resolve_product_titles_with_luna(session, tenant_id=tenant_id, query=name_hint))
        if len(luna_matches) == 1:
            result.update(resolver="luna_title_match", match=luna_matches[0], matches=luna_matches)
        elif luna_matches:
            result.update(resolver="luna_title_match", matches=luna_matches, ambiguous=True)

    # Unknown URL alone → no guess (handled by empty result).
    if url_hint and not name_hint and not result.get("matches"):
        result["resolver"] = "url_unknown"

    return result
