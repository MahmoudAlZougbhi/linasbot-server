"""Request rule normalization for CM requests_appointments (title + note per type)."""

from __future__ import annotations

from typing import Any

from services.cm.schemas_content import LocalizedLabels
from services.requests.constants import REQUEST_TYPES

RequestTypeCode = str

_DEFAULT_TYPE: RequestTypeCode = "APPOINTMENT"
_TYPE_DEFAULT_TITLES: dict[str, str] = {
    "ORDER": "Order",
    "APPOINTMENT": "Appointment",
    "OTHER": "Other",
}

_BUILTIN_FIELD_IDS: tuple[str, ...] = (
    "preferred_date",
    "preferred_time",
    "phone",
    "email",
    "fulfillment",
    "address",
    "quantity",
    "notes",
    "service",
    "product",
    "branch",
    "customer_name",
)


def _text(value: object) -> str:
    return str(value or "").strip()


def normalize_request_rule_item(raw: dict[str, Any]) -> dict[str, Any]:
    """Normalize one owner-facing request rule."""
    item = dict(raw)
    if "enabled" not in item:
        item["enabled"] = True
    type_raw = _text(item.get("type")).upper()
    if type_raw not in REQUEST_TYPES:
        type_raw = _DEFAULT_TYPE
    item["type"] = type_raw
    title = _text(item.get("name")) or _text(item.get("title"))
    item["name"] = title
    notes = _text(item.get("notes"))
    item["notes"] = notes or None
    return item


def _label_en(labels: object) -> str:
    if not isinstance(labels, dict):
        return ""
    return _text(labels.get("en")) or _text(labels.get("ar")) or _text(labels.get("fr"))


def migrate_legacy_to_rules(payload: dict[str, object]) -> list[dict[str, object]]:
    """Build rules[] from legacy enabled_types only when rules key is absent."""
    raw_rules = payload.get("rules")
    if raw_rules is not None:
        if not isinstance(raw_rules, list):
            return []
        out: list[dict[str, object]] = []
        for raw in raw_rules:
            if isinstance(raw, dict):
                out.append(normalize_request_rule_item(raw))
        return out

    enabled = payload.get("enabled_types") or []
    if not isinstance(enabled, list) or not enabled:
        return []

    type_labels = payload.get("type_labels")
    labels_map: dict[str, object] = type_labels if isinstance(type_labels, dict) else {}
    section_note = _text(payload.get("notes"))
    rules: list[dict[str, object]] = []
    for index, type_code in enumerate(enabled):
        tc = _text(type_code).upper()
        if tc not in REQUEST_TYPES:
            continue
        title = _label_en(labels_map.get(tc))
        if not title:
            title = _TYPE_DEFAULT_TITLES.get(tc, tc)
        rules.append(
            normalize_request_rule_item(
                {
                    "id": f"req_legacy_{tc.lower()}_{index}",
                    "type": tc,
                    "name": title,
                    "notes": section_note or None,
                    "enabled": True,
                }
            )
        )
    return rules


def seed_builtin_fields(existing: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Server-side default capture fields when owner enables rules but fields were never configured."""
    seen = {str(f.get("id") or "") for f in existing if isinstance(f, dict)}
    seeded: list[dict[str, Any]] = list(existing)
    order_base = len(seeded)
    for index, field_id in enumerate(_BUILTIN_FIELD_IDS):
        if field_id in seen:
            continue
        seeded.append(
            {
                "id": field_id,
                "labels": LocalizedLabels(en=field_id.replace("_", " ")).model_dump(mode="json"),
                "required": False,
                "enabled": True,
                "order": order_base + index,
                "applies_to": [],
                "validation": "phone" if field_id == "phone" else "email" if field_id == "email" else "",
                "notes": None,
            }
        )
    return seeded


def apply_derived_from_rules(payload: dict[str, object], rules: list[dict[str, object]]) -> dict[str, object]:
    """Derive module_enabled / enabled_types from rules; preserve hidden runtime fields."""
    out = dict(payload)
    out["rules"] = rules

    active_types: list[str] = []
    seen: set[str] = set()
    for rule in rules:
        if not rule.get("enabled", True):
            continue
        tc = _text(rule.get("type")).upper()
        if tc in REQUEST_TYPES and tc not in seen:
            seen.add(tc)
            active_types.append(tc)

    out["module_enabled"] = len(rules) > 0
    out["enabled_types"] = active_types

    if rules:
        raw_fields = out.get("fields")
        fields: list[dict[str, Any]] = []
        if isinstance(raw_fields, list):
            fields = [f for f in raw_fields if isinstance(f, dict)]
        if not fields:
            out["fields"] = seed_builtin_fields(fields)

    return out


def sanitize_requests_appointments_payload(payload: dict[str, object]) -> dict[str, object]:
    """Normalize rules on draft read/write; migrate legacy enabled_types when needed."""
    base = dict(payload)
    rules = migrate_legacy_to_rules(base)
    return apply_derived_from_rules(base, rules)


def request_rule_has_content(rule: dict[str, Any]) -> bool:
    return bool(_text(rule.get("name")) or _text(rule.get("notes")))


def format_request_rules_for_ai(
    payload: dict[str, Any],
    *,
    selected_ids: list[str] | None = None,
) -> str:
    """Compact guidance block for Answer Tera when capture is active.

    When Luna selected specific request definitions, only those rules are included.
    Never dump the tenant's full rule list into Tera.
    """
    rules_raw = payload.get("rules")
    if not isinstance(rules_raw, list) or not rules_raw:
        return ""
    wanted: set[str] | None = None
    if selected_ids is not None:
        wanted = {str(x).strip() for x in selected_ids if str(x).strip()}
        wanted = {item.split(":", 1)[-1] for item in wanted}
    lines: list[str] = []
    for raw in rules_raw:
        if not isinstance(raw, dict) or not raw.get("enabled", True):
            continue
        rule_id = _text(raw.get("id"))
        if wanted is not None and rule_id not in wanted:
            continue
        title = _text(raw.get("name")) or _TYPE_DEFAULT_TITLES.get(_text(raw.get("type")).upper(), "Request")
        note = _text(raw.get("notes"))
        type_code = _text(raw.get("type")).upper()
        line = f"- [{type_code}] {title}"
        if note:
            line += f": {note}"
        lines.append(line)
    if wanted is not None and not lines:
        return (
            "Request capture is active. Use only request definitions already in evidence. "
            "Do not assume other unpublished-to-this-turn request rules apply."
        )
    if not lines:
        return ""
    return "Published customer request rules (use for capture guidance only):\n" + "\n".join(lines)
