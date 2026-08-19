"""Accept search metadata only when title+description are ready for live Save."""

from __future__ import annotations

import re

from services.search_metadata.english import looks_like_english
from services.search_metadata.errors import MetadataPreparationError
from services.search_metadata.generate import SearchMetadata
from services.search_metadata.limits import (
    AI_SEARCH_DESCRIPTION_MAX,
    AI_SEARCH_KEYWORD_MAX,
    AI_SEARCH_TITLE_MAX,
)

_DIGIT_RUN = re.compile(r"\d{2,}")

# Product keywords may be an empty list when the owner description is weak and
# invented category/use terms were stripped. Title and description must still
# be non-empty English. Keywords are never a substitute for those two fields.


def metadata_is_ready(
    meta: SearchMetadata,
    *,
    include_keywords: bool,
    content: str,
    original_title: str,
) -> bool:
    title = " ".join(str(meta.title or "").split())
    description = " ".join(str(meta.description or "").split())
    if not title or not description:
        return False
    if len(title) > AI_SEARCH_TITLE_MAX or len(description) > AI_SEARCH_DESCRIPTION_MAX:
        return False
    if not looks_like_english(title) or not looks_like_english(description):
        return False
    haystack = f"{original_title}\n{content}"
    blob = f"{title} {description}"
    if include_keywords:
        keywords = [str(word).strip() for word in list(meta.keywords or []) if str(word).strip()]
        if any(len(word) > AI_SEARCH_KEYWORD_MAX for word in keywords):
            return False
        blob = f"{blob} {' '.join(keywords)}"
    return _digit_runs_grounded(blob, haystack=haystack)


def require_ready_metadata(
    meta: SearchMetadata,
    *,
    include_keywords: bool,
    content: str,
    original_title: str,
) -> SearchMetadata:
    if metadata_is_ready(
        meta,
        include_keywords=include_keywords,
        content=content,
        original_title=original_title,
    ):
        return meta
    raise MetadataPreparationError()


def _digit_runs_grounded(blob: str, *, haystack: str) -> bool:
    """Reject compact metadata that invents multi-digit facts absent from the item."""
    for run in _DIGIT_RUN.findall(blob or ""):
        if run not in (haystack or ""):
            return False
    return True
