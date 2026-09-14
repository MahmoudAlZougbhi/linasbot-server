"""Inspect Graph comment reply lists before posting a public AI reply.

Facebook's ``/{comment-id}/comments`` edge can reject nested ``from{id}``
(HTTP 400). That must not dead-letter the inbound event: after field
fallbacks, an unavailable list is treated as "no proven page reply" so
generation can proceed. Timeouts, 429, and 5xx stay fail-closed/retryable.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

_runtime_logger = logging.getLogger("uvicorn.error")

_COMMENT_REPLY_PAGE_SIZE = 100
_COMMENT_REPLY_MAX_PAGES = 100
_REPLY_LIST_FIELD_ATTEMPTS = ("id,from", "id")
_RETRYABLE_CLIENT_STATUSES = frozenset({408, 425, 429})


class MetaCommentReplyInspectionError(RuntimeError):
    """The provider reply list could not be proven complete and trustworthy."""


def _inspect_http_status(reason: str) -> int | None:
    text = str(reason or "").strip()
    if not text.startswith("http_"):
        return None
    digits = text[5:].split("_", 1)[0]
    if not digits.isdigit():
        return None
    return int(digits)


def _inspect_error_is_unavailable(reason: str) -> bool:
    status = _inspect_http_status(reason)
    if status is None:
        return False
    return 400 <= status < 500 and status not in _RETRYABLE_CLIENT_STATUSES


def _reply_owner_id(from_raw: object) -> str:
    if not isinstance(from_raw, dict):
        return ""
    return str(from_raw.get("id") or "").strip()


async def _graph_get_json(
    client: httpx.AsyncClient,
    path: str,
    *,
    token: str,
    params: dict[str, str] | None = None,
) -> dict[str, Any]:
    try:
        response = await client.get(path, params=params or {}, headers={"Authorization": f"Bearer {token}"})
    except httpx.HTTPError as exc:
        raise MetaCommentReplyInspectionError("request_failed") from exc
    if response.status_code < 200 or response.status_code >= 300:
        raise MetaCommentReplyInspectionError(f"http_{response.status_code}")
    try:
        payload = response.json()
    except ValueError as exc:
        raise MetaCommentReplyInspectionError("invalid_json") from exc
    if not isinstance(payload, dict) or payload.get("error"):
        raise MetaCommentReplyInspectionError("invalid_response")
    return payload


async def _fetch_reply_list_page(
    client: httpx.AsyncClient,
    graph_url: str,
    *,
    token: str,
    after: str,
) -> dict[str, Any] | None:
    """Return one reply-list page, or None when Graph cannot prove ownership.

    None means the list edge is a definitive client error, or the only
    successful shape omitted ``from`` so a page reply cannot be proven.
    """

    for fields in _REPLY_LIST_FIELD_ATTEMPTS:
        params = {"fields": fields, "limit": str(_COMMENT_REPLY_PAGE_SIZE)}
        if after:
            params["after"] = after
        try:
            payload = await _graph_get_json(client, graph_url, token=token, params=params)
        except MetaCommentReplyInspectionError as exc:
            reason = str(exc)
            if _inspect_error_is_unavailable(reason):
                _runtime_logger.warning(
                    "[meta-comment] reply_list_fields_unavailable fields=%s reason=%s",
                    fields,
                    reason,
                )
                continue
            raise
        if fields == "id":
            _runtime_logger.warning("[meta-comment] reply_list_missing_from treating_as_unreplied")
            return None
        return payload
    _runtime_logger.warning("[meta-comment] reply_list_unavailable treating_as_unreplied")
    return None


async def _comment_has_page_reply(
    client: httpx.AsyncClient,
    *,
    comment_id: str,
    owner_id: str,
    token: str,
    graph_url: str,
) -> bool:
    del comment_id  # Graph path is already bound in graph_url; do not log ids.
    if not owner_id:
        raise MetaCommentReplyInspectionError("missing_owner_id")

    seen_cursors: set[str] = set()
    after = ""
    for _page_number in range(_COMMENT_REPLY_MAX_PAGES):
        payload = await _fetch_reply_list_page(client, graph_url, token=token, after=after)
        if payload is None:
            return False
        rows = payload.get("data")
        if not isinstance(rows, list):
            raise MetaCommentReplyInspectionError("invalid_rows")
        for row in rows:
            if not isinstance(row, dict):
                raise MetaCommentReplyInspectionError("invalid_row")
            owner = _reply_owner_id(row.get("from"))
            if not owner:
                continue
            if owner == owner_id:
                return True

        paging_raw = payload.get("paging")
        if paging_raw is None:
            return False
        if not isinstance(paging_raw, dict):
            raise MetaCommentReplyInspectionError("invalid_paging")
        if not str(paging_raw.get("next") or "").strip():
            return False
        cursors_raw = paging_raw.get("cursors")
        cursors = cursors_raw if isinstance(cursors_raw, dict) else {}
        next_after = str(cursors.get("after") or "").strip()
        if not next_after or next_after in seen_cursors:
            raise MetaCommentReplyInspectionError("invalid_paging_cursor")
        seen_cursors.add(next_after)
        after = next_after

    raise MetaCommentReplyInspectionError("pagination_limit_exceeded")
