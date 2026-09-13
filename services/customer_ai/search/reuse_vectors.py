"""Reuse Voyage vectors when content_hash is unchanged across index versions."""

from __future__ import annotations

from typing import Any

from services.customer_ai.search.store import _MEMORY


def row_reuse_key(row: dict[str, Any]) -> tuple[str, str, str, str, str]:
    return (
        str(row.get("tenant_id") or ""),
        str(row.get("space_id") or ""),
        str(row.get("source_id") or ""),
        str(row.get("chunk_id") or ""),
        str(row.get("content_hash") or ""),
    )


def _as_vector(value: Any) -> list[float] | None:
    if isinstance(value, list) and value and all(isinstance(item, (int, float)) for item in value):
        return [float(item) for item in value]
    if isinstance(value, str) and value.startswith("[") and value.endswith("]"):
        try:
            parts = [float(item) for item in value[1:-1].split(",") if item.strip()]
        except ValueError:
            return None
        return parts or None
    return None


def _memory_lookup(
    tenant_id: str, wanted: set[tuple[str, str, str, str, str]]
) -> dict[tuple[str, str, str, str, str], list[float]]:
    found: dict[tuple[str, str, str, str, str], list[float]] = {}
    for item in _MEMORY.get(tenant_id, []):
        if not isinstance(item, dict):
            continue
        key = row_reuse_key(item)
        if key not in wanted or not key[-1]:
            continue
        vector = _as_vector(item.get("embedding"))
        if vector:
            found[key] = vector
    return found


def _sql_lookup(
    session: Any,
    tenant_id: str,
    space_id: str,
    wanted: set[tuple[str, str, str, str, str]],
) -> dict[tuple[str, str, str, str, str], list[float]]:
    if not wanted:
        return {}
    hashes = sorted({key[-1] for key in wanted if key[-1]})
    if not hashes:
        return {}
    try:
        from sqlalchemy import text

        rows = session.execute(
            text(
                """
                SELECT space_id, source_id, chunk_id, content_hash, embedding::text AS embedding
                FROM customer_ai_search_documents
                WHERE tenant_id = :tenant_id
                  AND space_id = :space_id
                  AND content_hash = ANY(:hashes)
                """
            ),
            {"tenant_id": tenant_id, "space_id": space_id, "hashes": hashes},
        )
    except Exception:
        return {}
    found: dict[tuple[str, str, str, str, str], list[float]] = {}
    for row in rows:
        mapping = row._mapping if hasattr(row, "_mapping") else None
        data = dict(mapping) if mapping is not None else {}
        vector = _as_vector(data.get("embedding"))
        if not vector:
            continue
        key = (
            tenant_id,
            str(data.get("space_id") or space_id),
            str(data.get("source_id") or ""),
            str(data.get("chunk_id") or ""),
            str(data.get("content_hash") or ""),
        )
        if key in wanted:
            found[key] = vector
    return found


def lookup_prior_vectors(session: Any | None, rows: list[dict[str, Any]]) -> list[list[float] | None]:
    """Return prior embedding per row, or None when that hash must be embedded."""
    if not rows:
        return []
    wanted = {row_reuse_key(row) for row in rows if row_reuse_key(row)[-1]}
    tenant_id = str(rows[0].get("tenant_id") or "")
    space_id = str(rows[0].get("space_id") or "")
    found = _memory_lookup(tenant_id, wanted)
    if session is not None:
        found.update(_sql_lookup(session, tenant_id, space_id, wanted - found.keys()))
    out: list[list[float] | None] = []
    for row in rows:
        key = row_reuse_key(row)
        out.append(found.get(key) if key[-1] else None)
    return out


def merge_prior_and_fresh(
    prior: list[list[float] | None],
    fresh: list[list[float]],
) -> list[list[float]]:
    missing = [index for index, vector in enumerate(prior) if vector is None]
    if len(fresh) != len(missing):
        raise ValueError(f"fresh_vector_mismatch:{len(fresh)}!={len(missing)}")
    merged: list[list[float]] = []
    fresh_i = 0
    for vector in prior:
        if vector is None:
            merged.append(fresh[fresh_i])
            fresh_i += 1
        else:
            merged.append(vector)
    return merged


def group_row_slices(groups: list[list[str]]) -> list[tuple[int, int]]:
    slices: list[tuple[int, int]] = []
    start = 0
    for group in groups:
        end = start + len(group)
        slices.append((start, end))
        start = end
    return slices
