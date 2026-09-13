"""Isolated live-test CM payloads. Not proven production clinic hours."""

from __future__ import annotations

from typing import Any

TENANT_LINAS = "linas"
TENANT_TEST = "lab_linas_test"
TENANT_TEST_2 = "lab_linas_test_2"

MARKER_LINAS = "LinasLaserMarkerAlpha"
MARKER_TEST = "LinasTestOneMarker"
MARKER_TEST_2 = "LinasTestTwoMarker"
_INTERNAL_GREETING_RULE = "Use this rule only if the user message is only"


def keep_knowledge_item(row: dict[str, Any]) -> bool:
    blob = " ".join(
        str(row.get(key) or "") for key in ("body", "title", "content", "text", "description", "ar", "en", "fr")
    )
    return _INTERNAL_GREETING_RULE not in blob


def scrub_internal_rules(sections: dict[str, Any]) -> dict[str, Any]:
    out = dict(sections)
    for name, payload in list(out.items()):
        if not isinstance(payload, dict):
            continue
        copied = dict(payload)
        for key in ("items", "topics", "rules", "catalog"):
            rows = copied.get(key)
            if not isinstance(rows, list):
                continue
            copied[key] = [row for row in rows if not isinstance(row, dict) or keep_knowledge_item(row)]
        out[name] = copied
    return out


def week(open_t: str, close_t: str, *, sunday_off: bool = False) -> dict[str, Any]:
    day = {"enabled": True, "open": open_t, "close": close_t, "off_day": False}
    off = {"enabled": True, "open": "", "close": "", "off_day": True}
    out = {name: dict(day) for name in ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday")}
    out["sunday"] = dict(off) if sunday_off else dict(day)
    return out


def _att(att_id: str, kind: str, title: str, caption: str, url: str = "") -> dict[str, Any]:
    row = {
        "id": att_id,
        "kind": kind,
        "title": title,
        "description": caption,
        "caption": caption,
        "status": "active",
    }
    if kind == "link":
        row["url"] = url
    return row


def _greeting(name: str, ar: str, en: str) -> dict[str, Any]:
    return {
        "items": [
            {
                "id": f"greet_{name}",
                "enabled": True,
                "name": "session hello",
                "trigger_mode": "session_start",
                "ar": ar,
                "en": en,
                "fr": en,
            }
        ]
    }


def _requests(types: list[str], *, prefix: str) -> dict[str, Any]:
    titles = {"APPOINTMENT": "Appointment", "ORDER": "Product order", "HUMAN": "Human handoff"}
    rules = []
    for code in types:
        rules.append(
            {
                "id": f"{prefix}_{code.lower()}",
                "type": code,
                "name": titles[code],
                "enabled": True,
                "scope": "handoff" if code == "HUMAN" else "general",
                "confirmation_required": code != "HUMAN",
            }
        )
    return {"module_enabled": True, "enabled_types": list(types), "rules": rules}


def _branch(
    item_id: str,
    en: str,
    ar: str,
    aliases: list[str],
    schedule: dict[str, Any],
    phone: str = "",
) -> dict[str, Any]:
    row = {
        "id": item_id,
        "labels": {"en": en, "ar": ar},
        "aliases": aliases,
        "weekly_schedule": schedule,
        "available": True,
        "status": "active",
        "ai_search_description": f"{en} {ar} hours دوام",
    }
    if phone:
        row["phone"] = phone
    return row


def _catalog(
    item_id: str,
    item_type: str,
    en: str,
    ar: str,
    attachments: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "id": item_id,
        "item_type": item_type,
        "labels": {"en": en, "ar": ar},
        "aliases": [en, ar, item_id],
        "description": en,
        "active": True,
        "attachments": attachments,
    }


def test1_sections() -> dict[str, Any]:
    return {
        "ai_basics": {
            "assistant_name": "Lina Test",
            "clinic_name": "Linas Test",
            "identity_summary": "Isolated Linas Test tenant. Never use Linas Laser facts.",
        },
        "dynamic_messages": _greeting("test1", "مرحبا من Linas Test", "Hello from Linas Test"),
        "knowledge": {
            "items": [
                {
                    "id": "marker",
                    "title": "Linas Test marker",
                    "body": f"Parking is Hamra street only. Code {MARKER_TEST}.",
                    "status": "active",
                    "ai_search_description": "parking hamra marker",
                }
            ]
        },
        "branches": {
            "items": [_branch("hamra", "Hamra", "حمرا", ["hamra", "حمرا"], week("09:00", "15:00", sunday_off=True))]
        },
        "opening_hours": {
            "items": [
                {
                    "id": "oh_hamra",
                    "title": "Hamra hours",
                    "aliases": ["hamra hours", "حمرا"],
                    "monday": {"open": "09:00", "close": "15:00"},
                    "sunday": {"closed": True},
                    "status": "active",
                }
            ]
        },
        "prices": {
            "catalog": [
                _catalog(
                    "alpha",
                    "product",
                    "Product Alpha",
                    "منتج ألفا",
                    [
                        _att("t1_alpha_img", "image", "Alpha photo", "Send Alpha photo"),
                        _att("t1_alpha_vid", "video", "Alpha video", "Send Alpha video"),
                        _att(
                            "t1_alpha_link",
                            "link",
                            "Alpha link",
                            "Send Alpha page",
                            "https://qa.linastest.example/alpha",
                        ),
                    ],
                )
            ],
            "price_entries": [{"id": "alpha_hamra", "catalog_item_id": "alpha", "amount": 99, "currency": "USD"}],
        },
        "requests_appointments": _requests(["ORDER"], prefix="t1"),
    }


def test2_sections() -> dict[str, Any]:
    return {
        "ai_basics": {
            "assistant_name": "Lina Test Two",
            "clinic_name": "Linas Test 2",
            "identity_summary": "Isolated Linas Test 2 tenant. Never use Linas Laser or Linas Test facts.",
        },
        "dynamic_messages": _greeting("test2", "مرحبا من Linas Test 2", "Hello from Linas Test 2"),
        "knowledge": {
            "items": [
                {
                    "id": "marker",
                    "title": "Linas Test 2 marker",
                    "body": f"Parking is Jounieh garage only. Code {MARKER_TEST_2}.",
                    "status": "active",
                    "ai_search_description": "parking jounieh marker",
                }
            ]
        },
        "branches": {
            "items": [
                _branch("jounieh", "Jounieh", "جونيه", ["jounieh", "جونيه"], week("08:00", "16:00", sunday_off=True))
            ]
        },
        "opening_hours": {
            "items": [
                {
                    "id": "oh_jounieh",
                    "title": "Jounieh hours",
                    "aliases": ["jounieh hours", "جونيه"],
                    "monday": {"open": "08:00", "close": "16:00"},
                    "sunday": {"closed": True},
                    "status": "active",
                }
            ]
        },
        "prices": {
            "catalog": [
                _catalog(
                    "alpha",
                    "product",
                    "Product Alpha",
                    "منتج ألفا",
                    [_att("t2_alpha_img", "image", "Alpha 2 photo", "Send Test 2 Alpha photo")],
                )
            ],
            "price_entries": [{"id": "alpha_jounieh", "catalog_item_id": "alpha", "amount": 5, "currency": "USD"}],
        },
        "requests_appointments": _requests(["HUMAN"], prefix="t2"),
    }


def merge_linas_hours(branches_payload: dict[str, Any]) -> dict[str, Any]:
    """Keep existing Linas branches; write test clocks. No Sunday off."""
    payload = dict(branches_payload)
    items = [dict(row) for row in (payload.get("items") or []) if isinstance(row, dict)]
    clocks = {"beirut": week("10:00", "20:00"), "antelias": week("11:00", "19:00")}
    seen: set[str] = set()
    for item in items:
        item_id = str(item.get("id") or "").strip().lower()
        seen.add(item_id)
        if item_id in clocks:
            item["weekly_schedule"] = clocks[item_id]
            item["available"] = True
            item["status"] = str(item.get("status") or "active")
    if "beirut" not in seen:
        items.append(_branch("beirut", "Beirut", "بيروت", ["beirut", "بيروت"], clocks["beirut"]))
    if "antelias" not in seen:
        items.append(_branch("antelias", "Antelias", "أنطلياس", ["antelias", "أنطلياس"], clocks["antelias"]))
    payload["items"] = items
    return payload


def merge_linas_opening_hours(hours_payload: dict[str, Any]) -> dict[str, Any]:
    payload = dict(hours_payload)
    items = [dict(row) for row in (payload.get("items") or []) if isinstance(row, dict)]
    wanted = {
        "oh_beirut": {
            "id": "oh_beirut",
            "title": "Beirut Opening Hours",
            "aliases": ["beirut hours", "بيروت"],
            "monday": {"open": "10:00", "close": "20:00"},
            "sunday": {"open": "10:00", "close": "20:00"},
            "status": "active",
        },
        "oh_antelias": {
            "id": "oh_antelias",
            "title": "Antelias Opening Hours",
            "aliases": ["antelias hours", "أنطلياس"],
            "monday": {"open": "11:00", "close": "19:00"},
            "sunday": {"open": "11:00", "close": "19:00"},
            "status": "active",
        },
    }
    by_id = {str(row.get("id") or ""): row for row in items}
    for key, row in wanted.items():
        current = dict(by_id.get(key) or {})
        current.update(row)
        by_id[key] = current
    payload["items"] = list(by_id.values())
    return payload


def merge_linas_extras(sections: dict[str, Any]) -> dict[str, Any]:
    """Add greeting, marker, laser/product media, and request types without wiping other drafts."""
    out = dict(sections)
    greet = dict(out.get("dynamic_messages") or {})
    items = [row for row in (greet.get("items") or []) if isinstance(row, dict) and keep_knowledge_item(row)]
    if not any(str(row.get("id") or "") == "greet_linas" for row in items):
        items.extend(_greeting("linas", "مرحباً من ليناز ليزر", "Hello from Lina's Laser")["items"])
    greet["items"] = items
    out["dynamic_messages"] = greet

    knowledge = dict(out.get("knowledge") or {})
    kn_items = [
        dict(row) for row in (knowledge.get("items") or []) if isinstance(row, dict) and keep_knowledge_item(row)
    ]
    if not any(str(row.get("id") or "") == "marker" for row in kn_items):
        kn_items.append(
            {
                "id": "marker",
                "title": "Linas Laser marker",
                "body": f"Street parking at both branches. Code {MARKER_LINAS}.",
                "status": "active",
                "ai_search_description": "parking marker linas",
            }
        )
    knowledge["items"] = kn_items
    out["knowledge"] = knowledge

    prices = dict(out.get("prices") or {})
    catalog = [dict(row) for row in (prices.get("catalog") or []) if isinstance(row, dict)]
    entries = [dict(row) for row in (prices.get("price_entries") or []) if isinstance(row, dict)]
    ids = {str(row.get("id") or "") for row in catalog}
    if "laser" not in ids:
        catalog.append(
            _catalog(
                "laser",
                "service",
                "Laser hair removal",
                "ليزر",
                [
                    _att("linas_laser_img", "image", "Laser photo", "Send laser photo"),
                    _att("linas_laser_vid", "video", "Laser video", "Send laser video"),
                    _att(
                        "linas_laser_link",
                        "link",
                        "Laser booking link",
                        "Send laser booking page",
                        "https://qa.linaslaser.example/book/laser",
                    ),
                ],
            )
        )
        entries.extend(
            [
                {
                    "id": "laser_beirut",
                    "catalog_item_id": "laser",
                    "branch_id": "beirut",
                    "amount": 80,
                    "currency": "USD",
                },
                {
                    "id": "laser_antelias",
                    "catalog_item_id": "laser",
                    "branch_id": "antelias",
                    "amount": 70,
                    "currency": "USD",
                },
            ]
        )
    if "aftercare" not in ids:
        catalog.append(
            _catalog(
                "aftercare",
                "product",
                "After Care Cream",
                "كريم العناية",
                [_att("linas_cream_img", "image", "Cream photo", "Send after care photo")],
            )
        )
        entries.append({"id": "aftercare_global", "catalog_item_id": "aftercare", "amount": 25, "currency": "USD"})
    prices["catalog"] = catalog
    prices["price_entries"] = entries
    out["prices"] = prices
    out["requests_appointments"] = _requests(["APPOINTMENT", "ORDER", "HUMAN"], prefix="linas")
    return out
