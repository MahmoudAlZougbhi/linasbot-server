"""Retrieve published sol_app_knowledge articles into EVIDENCE (not a second system novel)."""

from __future__ import annotations

from typing import Any

_MAX_BLOCK_CHARS = 3500
_TOP_K = 4


def _published_items(tenant_id: str) -> list[dict[str, Any]]:
    tid = (tenant_id or "").strip()
    if not tid:
        return []
    try:
        from services.ai_setup.version_store import load_published_content

        _pointer, sections = load_published_content(tid)
    except Exception:
        return []
    payload = sections.get("sol_app_knowledge")
    if not isinstance(payload, dict):
        return []
    rows = payload.get("items")
    if not isinstance(rows, list):
        return []
    out: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        status = str(row.get("status") or "active").strip().lower()
        if status in {"archived", "draft", "deleted", "inactive"}:
            continue
        title = str(row.get("title") or "").strip()
        body = str(row.get("body") or "").strip()
        if title or body:
            out.append({"id": str(row.get("id") or ""), "title": title, "body": body})
    return out


def _score(query: str, item: dict[str, Any]) -> int:
    text = (query or "").strip().lower()
    blob = f"{item.get('title') or ''} {item.get('body') or ''}".lower()
    if not text or not blob:
        return 1
    score = 0
    for token in text.replace("/", " ").split():
        if len(token) < 3:
            continue
        if token in blob:
            score += 2
    return score


def retrieve_sol_app_knowledge(tenant_id: str, query: str, *, limit: int = _TOP_K) -> list[dict[str, Any]]:
    items = _published_items(tenant_id)
    if not items:
        return []
    ranked = sorted(items, key=lambda row: (-_score(query, row), str(row.get("title") or "")))
    return ranked[: max(1, limit)]


def sol_knowledge_prompt_block(items: list[dict[str, Any]]) -> str:
    if not items:
        return ""
    lines = ["EVIDENCE (published sol_app_knowledge, targeted — not a full dump):"]
    used = 0
    for item in items:
        chunk = f"- {item.get('title') or 'Untitled'}: {(item.get('body') or '')[:700]}"
        if used + len(chunk) > _MAX_BLOCK_CHARS:
            break
        lines.append(chunk)
        used += len(chunk)
    return "\n".join(lines)
