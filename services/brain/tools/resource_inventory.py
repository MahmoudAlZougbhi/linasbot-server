"""Read-only published media/link inventory. Never sends on the channel."""

from __future__ import annotations

from typing import Any

from services.ai_setup.setup_resources import index_published_resources
from services.ai_setup.version_store import PublishedVersionError
from services.brain.contracts.evidence import EvidenceBundle, EvidenceItem
from services.brain.contracts.turn import ConversationState, CustomerTurn

_KIND_COUNT = {"image": "images", "video": "videos", "link": "links", "file": "files"}


def empty_inventory() -> dict[str, Any]:
    return {"images": 0, "videos": 0, "files": 0, "links": 0, "items": []}


def _source_hit(source_item_id: str, wanted: set[str]) -> bool:
    if not wanted:
        return True
    sid = str(source_item_id or "")
    if sid in wanted:
        return True
    return any(sid.endswith(f":{item}") or item in sid for item in wanted if item)


def format_inventory_receipt(inventory: dict[str, Any], *, prefix: str = "inventory") -> str:
    items = [row for row in (inventory.get("items") or []) if isinstance(row, dict)]
    bits = [
        f"{prefix} images={int(inventory.get('images') or 0)}",
        f"videos={int(inventory.get('videos') or 0)}",
        f"files={int(inventory.get('files') or 0)}",
        f"links={int(inventory.get('links') or 0)}",
    ]
    for row in items[:12]:
        bits.append(f"{row.get('kind')}:{row.get('id')}:{row.get('title')}")
    return " ".join(str(bit) for bit in bits)


def format_inventory_text(inventory: dict[str, Any]) -> str:
    items = [row for row in (inventory.get("items") or []) if isinstance(row, dict)]
    lines = [
        "Published resource inventory (customer-visible attachments only).",
        (
            f"images={int(inventory.get('images') or 0)} "
            f"videos={int(inventory.get('videos') or 0)} "
            f"files={int(inventory.get('files') or 0)} "
            f"links={int(inventory.get('links') or 0)}"
        ),
    ]
    if not items:
        lines.append("No photos, video, files, or links on the matched published topics.")
        return "\n".join(lines)
    for row in items:
        lines.append(f"- {row.get('kind')} id={row.get('id')} title={row.get('title')}")
    return "\n".join(lines)


def attach_inventory_evidence(bundle: EvidenceBundle, inventory: dict[str, Any] | None) -> EvidenceBundle:
    if not isinstance(inventory, dict):
        return bundle
    item = EvidenceItem(
        evidence_id="resources:inventory",
        source_family="knowledge",
        source_id="inventory",
        title="Published resource inventory",
        text=format_inventory_text(inventory),
        extra={"inventory": True, "counts": {k: inventory.get(k) for k in ("images", "videos", "files", "links")}},
    )
    items = [item, *[row for row in bundle.items if row.evidence_id != "resources:inventory"]]
    return bundle.model_copy(update={"items": items, "outcome": "found"})


def persist_inventory(turn: CustomerTurn, inventory: dict[str, Any]) -> None:
    payload = dict(inventory or empty_inventory())
    extra = dict(turn.extra or {})
    extra["last_resource_inventory"] = payload
    extra["resource_inventory"] = payload
    state = turn.state.model_copy(update={"resource_inventory": payload})
    object.__setattr__(turn, "extra", extra)
    object.__setattr__(turn, "state", state)


def list_published_inventory(
    *,
    tenant_id: str,
    query: str = "",
    source_ids: list[str] | None = None,
    limit: int = 20,
) -> dict[str, Any]:
    out = empty_inventory()
    if not (tenant_id or "").strip():
        return out
    try:
        index = index_published_resources(tenant_id)
    except PublishedVersionError:
        return out
    except Exception:
        return out
    wanted = {str(item).strip() for item in (source_ids or []) if str(item).strip()}
    needle = (query or "").strip().casefold()
    scored: list[tuple[int, dict[str, Any]]] = []
    for ref, record in index.items():
        if not _source_hit(str(record.get("source_item_id") or ""), wanted):
            continue
        title = str(record.get("title") or "")
        blob = f"{title} {record.get('description') or ''}".casefold()
        score = 2 if wanted else 0
        if needle:
            score += sum(1 for token in needle.split() if len(token) > 2 and token in blob)
        if wanted or score > 0 or not needle:
            kind = str(record.get("resource_type") or "file")
            scored.append(
                (
                    score,
                    {
                        "id": ref,
                        "kind": kind,
                        "title": title or ref,
                        "source_item_id": str(record.get("source_item_id") or ""),
                    },
                )
            )
    scored.sort(key=lambda row: (-row[0], str(row[1].get("id") or "")))
    items = [row for _score, row in scored[: max(1, limit)]]
    counts = empty_inventory()
    for row in items:
        key = _KIND_COUNT.get(str(row.get("kind") or "file"), "files")
        counts[key] = int(counts.get(key) or 0) + 1
    counts["items"] = items
    return counts


def run_check(args: dict[str, Any], turn: CustomerTurn) -> dict[str, Any]:
    source_ids = args.get("source_ids") or args.get("evidence_source_ids") or turn.extra.get("evidence_source_ids")
    if not isinstance(source_ids, list):
        source_ids = []
    query = str(args.get("query") or args.get("q") or args.get("text") or "").strip()
    inventory = list_published_inventory(
        tenant_id=turn.tenant_id,
        query=query,
        source_ids=[str(item) for item in source_ids],
    )
    persist_inventory(turn, inventory)
    return {"ok": True, "data": inventory, "error": None}


def remember_previous_inventory(turn: CustomerTurn) -> dict[str, Any] | None:
    stored = turn.state.resource_inventory if isinstance(turn.state, ConversationState) else None
    if isinstance(stored, dict) and stored:
        return stored
    extra = turn.extra.get("last_resource_inventory") or turn.extra.get("resource_inventory")
    return extra if isinstance(extra, dict) else None
