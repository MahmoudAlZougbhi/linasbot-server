"""Per-tenant staff alert numbers. E.164 only. No default country prefix."""

from __future__ import annotations

import json
import re
from typing import Any

from sqlalchemy import text

from db.session import whatsapp_session

_E164 = re.compile(r"^\+[1-9]\d{7,14}$")
_READY = False

_CREATE = """
CREATE TABLE IF NOT EXISTS linas_staff_alert_settings (
    tenant_id TEXT PRIMARY KEY,
    template_name TEXT NOT NULL DEFAULT '',
    template_language TEXT NOT NULL DEFAULT '',
    numbers_json TEXT NOT NULL DEFAULT '[]'
)
"""


def parse_e164_list(raw: str) -> list[str]:
    found: list[str] = []
    seen: set[str] = set()
    for part in re.split(r"[,;\n]+", str(raw or "")):
        cleaned = re.sub(r"[^\d+]", "", part.strip())
        if not _E164.fullmatch(cleaned) or cleaned in seen:
            continue
        seen.add(cleaned)
        found.append(cleaned)
    return found


def _ensure(session: Any) -> None:
    global _READY
    if _READY:
        return
    session.execute(text(_CREATE))
    _READY = True


def load_staff_alerts(tenant_id: str) -> dict[str, Any]:
    tid = str(tenant_id or "").strip()
    empty = {"numbers": [], "template_name": "", "template_language": ""}
    if not tid:
        return empty
    with whatsapp_session(require=True) as session:
        _ensure(session)
        row = session.execute(
            text(
                """
                SELECT template_name, template_language, numbers_json
                FROM linas_staff_alert_settings
                WHERE tenant_id = :tenant_id
                """
            ),
            {"tenant_id": tid},
        ).first()
    if row is None:
        return empty
    try:
        parsed = json.loads(row[2] or "[]")
    except json.JSONDecodeError:
        parsed = []
    numbers = [item for item in parsed if isinstance(item, str) and _E164.fullmatch(item)]
    return {
        "numbers": numbers,
        "template_name": str(row[0] or "").strip(),
        "template_language": str(row[1] or "").strip(),
    }


def save_staff_alerts(
    tenant_id: str,
    numbers: list[str],
    *,
    template_name: str = "",
    template_language: str = "",
) -> None:
    tid = str(tenant_id or "").strip()
    if not tid:
        raise ValueError("tenant_id required")
    clean = [item for item in numbers if _E164.fullmatch(item)]
    with whatsapp_session(require=True) as session:
        _ensure(session)
        session.execute(
            text(
                """
                INSERT INTO linas_staff_alert_settings
                    (tenant_id, template_name, template_language, numbers_json)
                VALUES (:tenant_id, :template_name, :template_language, :numbers_json)
                ON CONFLICT (tenant_id) DO UPDATE SET
                    template_name = excluded.template_name,
                    template_language = excluded.template_language,
                    numbers_json = excluded.numbers_json
                """
            ),
            {
                "tenant_id": tid,
                "template_name": template_name.strip(),
                "template_language": template_language.strip(),
                "numbers_json": json.dumps(clean),
            },
        )
