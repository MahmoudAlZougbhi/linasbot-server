"""Owner Copilot: propose soft-delete (archive/clear) of CM FAQ / articles / section items.

Never writes until the owner Approves the in-chat bar (same Approve→Live path as CM patches).
"""

from __future__ import annotations

from typing import Any

from modules.api_security import resolve_permissions
from services.owner_ai_tools_base import ToolResult

# Sections whose payload is primarily ``{items: [...]}``.
ITEMS_SECTIONS = frozenset(
    {
        "faq",
        "knowledge",
        "care",
        "services",
        "branches",
        "prices",
        "opening_hours",
        "dynamic_messages",
        "actions",
    }
)
# Soft-archive via ``status`` when present.
STATUS_ARCHIVE_SECTIONS = frozenset({"faq", "knowledge", "care"})
# Soft-hide via ``available=False``.
AVAILABLE_SECTIONS = frozenset({"services", "branches"})

# Field-shaped sections: "delete" clears non-empty string/list fields (with confirm bar).
FIELD_SECTIONS = frozenset(
    {
        "ai_basics",
        "languages",
        "style",
        "philosophy",
        "handoff",
        "comments",
        "ai_limits",
        "off_days",
    }
)

_SKIP_FIELD_KEYS = frozenset({"notes", "tenant_id", "permissions", "role", "platform_rules"})


def _require(role: str, permission: str) -> None:
    if not resolve_permissions(role, None).get(permission):
        raise PermissionError(f"Missing permission: {permission}")


def _normalize_section(section: str) -> str:
    return (section or "").strip().replace("-", "_")


def _item_id(section: str, item: dict[str, Any]) -> str:
    if section == "faq":
        return str(item.get("qa_group_id") or "").strip()
    return str(item.get("id") or "").strip()


def _item_title(section: str, item: dict[str, Any]) -> str:
    if section == "faq":
        variants = item.get("variants") if isinstance(item.get("variants"), list) else []
        for row in variants:
            if not isinstance(row, dict):
                continue
            q = str(row.get("question") or "").strip()
            if q:
                return q[:120]
        return str(item.get("qa_group_id") or "FAQ")[:120]
    title = str(item.get("title") or "").strip()
    if title:
        return title[:120]
    labels = item.get("labels")
    if isinstance(labels, dict):
        for key in ("en", "ar", "fr"):
            lab = str(labels.get(key) or "").strip()
            if lab:
                return lab[:120]
    return _item_id(section, item) or "item"


def _is_already_deleted(section: str, item: dict[str, Any]) -> bool:
    status = str(item.get("status") or "").lower()
    if status in {"archived", "stale"}:
        return True
    if section in AVAILABLE_SECTIONS and item.get("available") is False:
        return True
    return False


def _field_title(key: str, value: Any) -> str:
    label = key.replace("_", " ").strip().title()
    preview = ""
    if isinstance(value, str) and value.strip():
        preview = value.strip()[:80]
    elif isinstance(value, (list, tuple)) and value:
        preview = ", ".join(str(x) for x in value[:4])[:80]
    elif isinstance(value, dict) and value:
        preview = str(next(iter(value.values()), ""))[:80]
    return f"{label}: {preview}" if preview else label


def _load_items(tenant_id: str, section: str) -> tuple[list[dict[str, Any]], Any]:
    from services.cm.storage import get_draft

    env = get_draft(section, tenant_id=tenant_id, create_default=True)
    payload = dict(env.payload) if isinstance(env.payload, dict) else {}
    raw = payload.get("items")
    items: list[dict[str, Any]] = []
    if isinstance(raw, list):
        for row in raw:
            if isinstance(row, dict):
                items.append(dict(row))
    return items, env


def build_cm_delete_proposal(
    *,
    tenant_id: str,
    section: str,
    item_ids: list[str] | None = None,
    delete_all: bool = False,
    field_keys: list[str] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Return (patch, preview) for soft-delete. Does not write storage."""
    from services.cm.constants import CM_SECTIONS
    from services.cm.storage import get_draft

    name = _normalize_section(section)
    if name not in CM_SECTIONS:
        raise ValueError(f"Unknown CM section: {section}")

    wanted = {str(x).strip() for x in (item_ids or []) if str(x).strip()}
    fields_wanted = {str(x).strip() for x in (field_keys or []) if str(x).strip()}

    if name in ITEMS_SECTIONS:
        items, env = _load_items(tenant_id, name)
        active = [row for row in items if not _is_already_deleted(name, row)]
        if delete_all:
            selected = list(active)
        elif wanted:
            selected = [row for row in active if _item_id(name, row) in wanted]
        else:
            raise ValueError("Provide item_ids or delete_all=true")
        if not selected:
            raise ValueError("No matching items to delete (already archived or not found)")

        selected_ids = {_item_id(name, row) for row in selected}
        targets: list[dict[str, Any]] = []
        new_items: list[dict[str, Any]] = []
        for row in items:
            iid = _item_id(name, row)
            out = dict(row)
            if iid in selected_ids:
                targets.append({"id": iid, "title": _item_title(name, row), "kind": "item"})
                if name in STATUS_ARCHIVE_SECTIONS:
                    out["status"] = "archived"
                elif name in AVAILABLE_SECTIONS:
                    out["available"] = False
                else:
                    # Drop from list (still requires Confirm — not silent Live).
                    continue
            new_items.append(out)

        titles = [t["title"] for t in targets]
        preview = {
            "section": name,
            "kind": "cm_delete",
            "action": "delete",
            "delete_all": bool(delete_all),
            "mode": "archive" if name in STATUS_ARCHIVE_SECTIONS else (
                "hide" if name in AVAILABLE_SECTIONS else "remove"
            ),
            "targets": targets,
            "field": f"{len(targets)} item(s)",
            "changed_keys": ["items"],
            "proposed_value": "\n".join(f"• {t}" for t in titles)[:4000],
            "current_value": "",
            "revision": getattr(env, "revision", None),
            "item_count_after": len(new_items),
        }
        return {"items": new_items}, preview

    # Field-shaped (and any non-items section): clear non-empty authoring fields.
    if True:
        env = get_draft(name, tenant_id=tenant_id, create_default=True)
        payload = dict(env.payload) if isinstance(env.payload, dict) else {}
        clearable: list[str] = []
        for key, val in payload.items():
            if key in _SKIP_FIELD_KEYS:
                continue
            if isinstance(val, str) and val.strip():
                clearable.append(key)
            elif isinstance(val, (list, tuple)) and len(val) > 0:
                clearable.append(key)
            elif isinstance(val, dict) and val:
                clearable.append(key)
        if delete_all:
            keys = clearable
        elif fields_wanted:
            keys = [k for k in clearable if k in fields_wanted]
        elif wanted:
            # Allow item_ids alias for field keys when deleting from field sections.
            keys = [k for k in clearable if k in wanted]
        else:
            raise ValueError("Provide field_keys / item_ids or delete_all=true")
        if not keys:
            raise ValueError("No matching fields to clear")

        patch: dict[str, Any] = {}
        targets = []
        for key in keys:
            cur = payload.get(key)
            targets.append({"id": key, "title": _field_title(key, cur), "kind": "field"})
            if isinstance(cur, list):
                patch[key] = []
            elif isinstance(cur, dict):
                patch[key] = {}
            else:
                patch[key] = ""
        titles = [t["title"] for t in targets]
        preview = {
            "section": name,
            "kind": "cm_delete",
            "action": "delete",
            "delete_all": bool(delete_all),
            "mode": "clear_fields",
            "targets": targets,
            "field": ", ".join(keys[:8]),
            "changed_keys": keys,
            "proposed_value": "\n".join(f"• {t}" for t in titles)[:4000],
            "current_value": "",
            "revision": getattr(env, "revision", None),
        }
        return patch, preview


def filter_delete_targets(
    *,
    tenant_id: str,
    section: str,
    targets: list[dict[str, Any]],
    keep_ids: list[str],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Rebuild delete proposal keeping only ``keep_ids`` (after per-item X removals)."""
    allowed = {str(x).strip() for x in keep_ids if str(x).strip()}
    remaining = [t for t in targets if str(t.get("id") or "") in allowed]
    if not remaining:
        raise ValueError("Nothing left to delete")
    ids = [str(t["id"]) for t in remaining]
    kinds = {str(t.get("kind") or "item") for t in remaining}
    if kinds == {"field"} or "field" in kinds and "item" not in kinds:
        return build_cm_delete_proposal(tenant_id=tenant_id, section=section, field_keys=ids)
    return build_cm_delete_proposal(tenant_id=tenant_id, section=section, item_ids=ids)


async def tool_propose_cm_delete(
    *,
    tenant_id: str,
    role: str,
    user_id: str,
    section: str,
    item_ids: list[str] | None = None,
    field_keys: list[str] | None = None,
    delete_all: bool = False,
    replace_proposal_id: str | None = None,
) -> ToolResult:
    """Propose soft-delete; shows DeleteConfirm / Proposal bar until Approve."""
    _require(role, "contentManagers")
    from services.owner_ai_cm_approval import cm_patch_proposal_store, reject_cm_patch

    try:
        patch, preview = build_cm_delete_proposal(
            tenant_id=tenant_id,
            section=section,
            item_ids=item_ids,
            field_keys=field_keys,
            delete_all=delete_all,
        )
    except Exception as exc:
        return ToolResult(
            ok=False,
            name="propose_cm_delete",
            data={},
            error=f"{type(exc).__name__}: {exc}",
        )

    if replace_proposal_id:
        try:
            reject_cm_patch(tenant_id=tenant_id, user_id=user_id, proposal_id=str(replace_proposal_id))
        except Exception:
            pass

    prop = cm_patch_proposal_store.create(
        tenant_id=tenant_id,
        user_id=user_id,
        section=preview["section"],
        patch=patch,
        preview=preview,
    )
    data = {
        "proposal_id": prop.id,
        "confirmation_token": f"approve_cm_patch:{prop.id}",
        "preview": preview,
        "status": prop.status,
        "requires_confirmation": True,
        "section": preview["section"],
        "action": "delete",
        "target_count": len(preview.get("targets") or []),
    }
    return ToolResult(
        ok=True,
        name="propose_cm_delete",
        data=data,
        requires_confirmation=True,
        confirmation_token=str(data["confirmation_token"]),
        error="Confirmation required before delete is applied (Approve on the bar — do not ask for موافق just to show it)",
    )
