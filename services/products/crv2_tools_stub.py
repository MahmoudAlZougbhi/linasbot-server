"""Backward-compatible re-exports — use services.products.crv2_tools."""

from __future__ import annotations

from services.products.crv2_tools import (  # noqa: F401
    crv2_find_product_by_image,
    crv2_find_product_by_url,
    crv2_get_product_details,
    crv2_get_product_images,
    crv2_search_product_by_title,
)
