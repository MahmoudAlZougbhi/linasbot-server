"""Tenant-scoped custom role templates (name + permission map)."""

from __future__ import annotations

import re
import uuid
from datetime import datetime
from typing import Any

from modules.api_security import PERMISSION_KEYS
from utils.utils import get_firestore_db

_SLUG_RE = re.compile(r"^[a-z][a-z0-9_-]{1,39}$")
_RESERVED = frozenset({"admin", "operator", "viewer", "platform_owner", "owner"})
_COLLECTION = "tenant_custom_roles"


def _normalize_permissions(raw: dict[str, Any] | None) -> dict[str, bool]:
    out = {key: False for key in PERMISSION_KEYS}
    if not raw:
        return out
    for key, value in raw.items():
        if key in PERMISSION_KEYS:
            out[key] = bool(value)
    return out


def _slugify(name: str) -> str:
    lowered = (name or "").strip().lower()
    slug = re.sub(r"[^a-z0-9]+", "-", lowered).strip("-")[:40]
    if not slug or not slug[0].isalpha():
        slug = f"role-{slug}" if slug else "role"
    slug = slug.strip("-")[:40]
    if not _SLUG_RE.fullmatch(slug):
        slug = f"role-{uuid.uuid4().hex[:8]}"
    return slug


class TenantCustomRolesStore:
    def __init__(self) -> None:
        self._db = None

    @property
    def db(self) -> Any:
        if self._db is None:
            self._db = get_firestore_db()
        return self._db

    def _doc(self, tenant_id: str) -> Any:
        if not self.db:
            raise RuntimeError("Firestore not initialized")
        return (
            self.db.collection("artifacts").document("linas-ai-bot-backend").collection(_COLLECTION).document(tenant_id)
        )

    def list_roles(self, tenant_id: str) -> list[dict[str, Any]]:
        snap = self._doc(tenant_id).get(timeout=6, retry=None)
        data = snap.to_dict() if snap.exists else None
        roles = list((data or {}).get("roles") or [])
        cleaned: list[dict[str, Any]] = []
        for role in roles:
            if not isinstance(role, dict):
                continue
            role_id = str(role.get("id") or "").strip().lower()
            name = str(role.get("name") or "").strip()
            if not role_id or not name:
                continue
            cleaned.append(
                {
                    "id": role_id,
                    "name": name[:80],
                    "system": False,
                    "permissions": _normalize_permissions(role.get("permissions")),
                }
            )
        return cleaned

    def role_ids(self, tenant_id: str) -> frozenset[str]:
        return frozenset(role["id"] for role in self.list_roles(tenant_id))

    def create_role(self, tenant_id: str, name: str, permissions: dict[str, Any] | None) -> dict[str, Any]:
        label = (name or "").strip()
        if len(label) < 2:
            raise ValueError("Role name is required")
        if len(label) > 80:
            raise ValueError("Role name is too long")
        existing = self.list_roles(tenant_id)
        taken = {role["id"] for role in existing} | {role["name"].strip().lower() for role in existing}
        if label.lower() in taken or label.lower() in _RESERVED:
            raise ValueError("A role with this name already exists")
        slug = _slugify(label)
        if slug in taken or slug in _RESERVED:
            slug = f"{slug[:31]}-{uuid.uuid4().hex[:8]}"
        role = {
            "id": slug,
            "name": label[:80],
            "system": False,
            "permissions": _normalize_permissions(permissions),
            "createdAt": datetime.utcnow().isoformat(),
        }
        next_roles = [
            {
                "id": item["id"],
                "name": item["name"],
                "permissions": item["permissions"],
                "createdAt": item.get("createdAt"),
            }
            for item in existing
        ]
        next_roles.append(
            {
                "id": role["id"],
                "name": role["name"],
                "permissions": role["permissions"],
                "createdAt": role["createdAt"],
            }
        )
        self._doc(tenant_id).set(
            {"roles": next_roles, "updatedAt": datetime.utcnow().isoformat()},
            timeout=5,
            retry=None,
        )
        return {
            "id": role["id"],
            "name": role["name"],
            "system": False,
            "permissions": role["permissions"],
        }


tenant_custom_roles = TenantCustomRolesStore()


def system_role_payloads() -> list[dict[str, Any]]:
    from modules.api_security import SYSTEM_ROLE_PERMISSIONS

    names = {"admin": "Admin", "operator": "Support", "viewer": "Viewer"}
    out: list[dict[str, Any]] = []
    for role_id, label in names.items():
        perms = SYSTEM_ROLE_PERMISSIONS.get(role_id) or {}
        out.append(
            {
                "id": role_id,
                "name": label,
                "system": True,
                "permissions": {key: bool(perms.get(key)) for key in PERMISSION_KEYS},
            }
        )
    return out
