"""Typed structured business facts for Customer Brain generation context."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

FactKind = Literal[
    "price",
    "service",
    "product",
    "branch",
    "hours",
    "contact",
    "availability",
    "request",
    "resource",
]


class StructuredFact(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: FactKind
    entity_id: str = ""
    value: str = ""
    unit: str = ""
    currency: str = ""
    source: str = "published"
    version: str = ""
    updated_at: str = ""
    authority: int = 50
    tenant_id: str = ""
    task_ids: list[str] = Field(default_factory=list)
    extra: dict[str, Any] = Field(default_factory=dict)


def facts_from_tool_data(tool: str, data: Any, *, tenant_id: str = "", task_id: str = "") -> list[StructuredFact]:
    rows: list[StructuredFact] = []
    if data is None:
        return rows
    items = data if isinstance(data, list) else [data]
    for item in items:
        if not isinstance(item, dict):
            continue
        if tool in {"get_price", "get_service", "search_services"}:
            price = item.get("price") or item.get("base_price")
            rows.append(
                StructuredFact(
                    kind="price" if price is not None else "service",
                    entity_id=str(item.get("id") or ""),
                    value=str(price if price is not None else item.get("title") or item.get("text") or ""),
                    currency=str(item.get("currency") or ""),
                    source=f"tool:{tool}",
                    authority=110 if price is not None else 95,
                    tenant_id=tenant_id,
                    task_ids=[task_id] if task_id else [],
                    extra={
                        "title": item.get("title"),
                        "entity_id": item.get("service_id") or item.get("id"),
                        "price_entry_id": item.get("id"),
                        "bundle": item.get("bundle"),
                    },
                )
            )
        elif tool in {"get_branch_hours", "get_branch"}:
            hours = item.get("hours") if isinstance(item.get("hours"), dict) else item
            rows.append(
                StructuredFact(
                    kind="hours",
                    entity_id=str(item.get("id") or ""),
                    value=str(hours),
                    source=f"tool:{tool}",
                    authority=100,
                    tenant_id=tenant_id,
                    task_ids=[task_id] if task_id else [],
                    extra={"name": item.get("name") or item.get("title"), "phone": item.get("phone")},
                )
            )
            if item.get("phone"):
                rows.append(
                    StructuredFact(
                        kind="contact",
                        entity_id=str(item.get("id") or ""),
                        value=str(item.get("phone")),
                        source=f"tool:{tool}",
                        authority=100,
                        tenant_id=tenant_id,
                        task_ids=[task_id] if task_id else [],
                    )
                )
        elif tool in {"get_product", "search_products"}:
            rows.append(
                StructuredFact(
                    kind="product",
                    entity_id=str(item.get("id") or ""),
                    value=str(item.get("title") or item.get("text") or ""),
                    source=f"tool:{tool}",
                    authority=95,
                    tenant_id=tenant_id,
                    task_ids=[task_id] if task_id else [],
                )
            )
        elif tool == "get_faq":
            rows.append(
                StructuredFact(
                    kind="service",
                    entity_id=str(item.get("id") or ""),
                    value=str(item.get("answer") or item.get("title") or ""),
                    source=f"tool:{tool}",
                    authority=85,
                    tenant_id=tenant_id,
                    task_ids=[task_id] if task_id else [],
                )
            )
        elif tool in {"check_setup_resources", "list_resources", "resolve_resource"}:
            media_items = item.get("items") if isinstance(item.get("items"), list) else None
            if media_items is not None:
                rows.append(
                    StructuredFact(
                        kind="resource",
                        entity_id="inventory",
                        value=(
                            f"images={int(item.get('images') or 0)} "
                            f"videos={int(item.get('videos') or 0)} "
                            f"files={int(item.get('files') or 0)} "
                            f"links={int(item.get('links') or 0)}"
                        ),
                        source=f"tool:{tool}",
                        authority=120,
                        tenant_id=tenant_id,
                        task_ids=[task_id] if task_id else [],
                        extra={"inventory": True},
                    )
                )
                for media in media_items:
                    if not isinstance(media, dict):
                        continue
                    rows.append(
                        StructuredFact(
                            kind="resource",
                            entity_id=str(media.get("id") or ""),
                            value=f"{media.get('kind')}:{media.get('title') or media.get('id')}",
                            source=f"tool:{tool}",
                            authority=120,
                            tenant_id=tenant_id,
                            task_ids=[task_id] if task_id else [],
                        )
                    )
            elif item.get("id") or item.get("attachment"):
                rows.append(
                    StructuredFact(
                        kind="resource",
                        entity_id=str(item.get("id") or ""),
                        value=str(item.get("title") or item.get("id") or ""),
                        source=f"tool:{tool}",
                        authority=95,
                        tenant_id=tenant_id,
                        task_ids=[task_id] if task_id else [],
                    )
                )
    return rows


def format_facts_block(facts: list[StructuredFact]) -> str:
    if not facts:
        return ""
    lines = ["STRUCTURED_FACTS:"]
    for fact in facts:
        lines.append(
            f"- [{fact.kind}] id={fact.entity_id} value={fact.value}"
            + (f" {fact.currency}" if fact.currency else "")
            + f" source={fact.source} authority={fact.authority}"
        )
    return "\n".join(lines)
