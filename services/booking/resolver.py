# -*- coding: utf-8 -*-
"""Resolve human-readable booking hints to CRM IDs using live API lists."""

from __future__ import annotations

import json
import os
import re
from difflib import SequenceMatcher
from typing import Any, Dict, List, Optional, Tuple

from services import api_integrations

from services.booking.constants import (
    ANTELIAS_BRANCH_ID,
    BEIRUT_BRANCH_ID,
    HAIR_MEN,
    HAIR_WOMEN,
    LASER_HAIR_REMOVAL_SERVICE_IDS,
    TATTOO_SERVICE_ID,
)


def _norm_api_list(raw: Any) -> List[dict]:
    if isinstance(raw, list):
        return [x for x in raw if isinstance(x, dict)]
    if isinstance(raw, dict):
        inner = raw.get("data")
        if isinstance(inner, list):
            return [x for x in inner if isinstance(x, dict)]
    return []


async def load_services() -> List[dict]:
    r = await api_integrations.get_services()
    if not r.get("success"):
        return []
    return _norm_api_list(r.get("data"))


async def load_branches() -> List[dict]:
    r = await api_integrations.get_branches()
    if not r.get("success"):
        return []
    return _norm_api_list(r.get("data"))


async def load_machines() -> List[dict]:
    r = await api_integrations.get_machines()
    if not r.get("success"):
        return []
    return _norm_api_list(r.get("data"))


def _safe_int(v: Any) -> Optional[int]:
    if v is None or v is False:
        return None
    if isinstance(v, bool):
        return None
    try:
        i = int(v)
        return i if i > 0 else None
    except (TypeError, ValueError):
        return None


def resolve_branch_id(
    name: Optional[str], branch_id: Optional[int], branches: List[dict]
) -> Tuple[Optional[int], Optional[str]]:
    bid = _safe_int(branch_id)
    if bid in (BEIRUT_BRANCH_ID, ANTELIAS_BRANCH_ID):
        return bid, None
    allowed = {_safe_int(b.get("id")) for b in branches}
    allowed.discard(None)
    if bid is not None and bid in allowed:
        return bid, None
    n = (name or "").strip().lower()
    if not n:
        return None, "branch"
    if "beirut" in n or "بيروت" in n:
        return BEIRUT_BRANCH_ID, None
    if "antelias" in n or "انطلياس" in n or "antaliyas" in n:
        return ANTELIAS_BRANCH_ID, None
    best = None
    best_score = 0.0
    for b in branches:
        bn = str(b.get("name") or "").lower()
        if not bn:
            continue
        sc = SequenceMatcher(None, n, bn).ratio()
        if sc > best_score:
            best_score = sc
            best = _safe_int(b.get("id"))
    if best is not None and best_score >= 0.45:
        return best, None
    return None, "branch"


def resolve_service_id(
    name: Optional[str],
    service_id: Optional[int],
    gender: str,
    services: List[dict],
) -> Tuple[Optional[int], Optional[str]]:
    sid = _safe_int(service_id)
    allowed = {_safe_int(s.get("id")) for s in services}
    allowed.discard(None)
    if sid is not None and sid in allowed:
        return sid, None

    n = (name or "").strip().lower()
    g = (gender or "").strip().lower()

    # Keyword shortcuts when API list is empty or fuzzy fails
    if not n and sid is None:
        return None, "service"

    if any(k in n for k in ("tattoo", "وشم", "pico", "tatoo")):
        return 13, None
    if any(k in n for k in ("co2", "scar", "stretch", "acne scar", "ندوب", "تشقق")):
        return 2, None
    if any(k in n for k in ("whiten", "dpl", "dark area", "تبييض", "تفتيح")):
        return 5, None
    hair_kw = ("hair", "laser hair", "شعر", "candela", "neo", "quadro", "bikini", "beard", "underarm", "إبط")
    if any(k in n for k in hair_kw):
        if g == "female":
            return HAIR_WOMEN, None
        if g == "male":
            return HAIR_MEN, None
        return None, "gender"

    best = None
    best_score = 0.0
    for s in services:
        sn = str(s.get("name") or "").lower()
        if not sn:
            continue
        sc = SequenceMatcher(None, n, sn).ratio()
        if sc > best_score:
            best_score = sc
            best = _safe_int(s.get("id"))
    if best is not None and best_score >= 0.42:
        return best, None
    return None, "service"


def resolve_machine_id(
    name: Optional[str],
    machine_id: Optional[int],
    machines: List[dict],
) -> Tuple[Optional[int], Optional[str]]:
    mid = _safe_int(machine_id)
    allowed = {_safe_int(m.get("id")) for m in machines}
    allowed.discard(None)
    if mid is not None and mid in allowed:
        return mid, None
    n = (name or "").strip().lower()
    if not n:
        return None, "machine"
    best = None
    best_score = 0.0
    for m in machines:
        mn = str(m.get("name") or "").lower()
        if not mn:
            continue
        if n in mn or mn in n:
            return _safe_int(m.get("id")), None
        sc = SequenceMatcher(None, n, mn).ratio()
        if sc > best_score:
            best_score = sc
            best = _safe_int(m.get("id"))
    if best is not None and best_score >= 0.4:
        return best, None
    return None, "machine"


def pick_default_machine_for_non_hair(service_id: int, machines: List[dict]) -> Optional[int]:
    """When the customer does not choose a device, any valid CRM machine id satisfies the API."""
    for m in machines:
        mid = _safe_int(m.get("id"))
        if mid is not None:
            return mid
    return None


def _tattoo_body_part_id_from_env_synonyms(label: str) -> Optional[int]:
    """
    When GET body-parts is down or empty, map user wording to a CRM id for service 13 only.
    Env: LINASLASER_TATTOO_BODY_SYNONYMS_JSON e.g. {"ra2be": 5, "رقبة": 5, "neck": 5, "عنق": 5}
    """
    raw = (os.getenv("LINASLASER_TATTOO_BODY_SYNONYMS_JSON") or "").strip()
    if not raw:
        return None
    try:
        m = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if not isinstance(m, dict):
        return None
    ll = (label or "").strip().lower()
    if not ll:
        return None
    for k, v in m.items():
        ks = str(k).strip().lower()
        if not ks:
            continue
        if ks in ll or ll in ks:
            return _safe_int(v)
    return None


def pick_pico_or_default_machine(machines: List[dict]) -> Optional[int]:
    """Prefer a Pico-labeled machine for tattoo; else first available id."""
    for m in machines:
        mid = _safe_int(m.get("id"))
        mn = str(m.get("name") or "").lower()
        if mid is not None and "pico" in mn:
            return mid
    return pick_default_machine_for_non_hair(0, machines)


def _text_suggests_legs(label: str) -> bool:
    """User wording for legs (LB/FR/AR/EN) — distinct from generic 'legacy' etc."""
    if not label or not str(label).strip():
        return False
    low = label.lower()
    compact = re.sub(r"[\s_\-]+", "", low)
    if re.search(r"\blegs?\b", low):
        return True
    if any(x in low for x in ("thigh", "فخذ", "cuisse")):
        return True
    if any(x in compact for x in ("ejren", "ejrin", "ejeren", "sa2en", "s2en", "se2en", "ejrin")):
        return True
    if any(x in label for x in ("رجلين", "رجل", "ساقين", "ساق")):
        return True
    return False


def _crm_row_is_leg(crm_name: str) -> bool:
    n = (crm_name or "").lower()
    return any(
        x in n
        for x in (
            "leg",
            "legs",
            "thigh",
            "فخذ",
            "ساق",
            "رجل",
            "lower limb",
            "jambe",
            "cuiss",
        )
    )


def _legs_scope_from_label(label: str) -> str:
    """
    Classify legs intent for CRM rows like 'Full Legs' vs 'Half Legs'.
    Returns: 'full' | 'half' | 'unspecified'
    """
    low = label.lower()
    compact = re.sub(r"[\s_\-]+", "", low)
    half_patterns = (
        "half leg",
        "half legs",
        "halfejren",
        "nosejren",
        "nos ejren",
        "ejren nos",
        "ejrennos",
        "nosejre",
        "media leg",
        "partial leg",
        "نص رجل",
        "نص رجلين",
        "نص ساق",
        "نص ساقين",
    )
    for p in half_patterns:
        if p in low:
            return "half"
    if "نص" in label and ("رجل" in label or "ساق" in label or "ejren" in compact):
        return "half"
    full_patterns = (
        "full leg",
        "full legs",
        "fullejren",
        "ejrenkamel",
        "ejrenkamle",
        "kamelejren",
        "kamel ejren",
        "both legs",
        "رجلين كامل",
        "ساقين كامل",
        "كل الرجلين",
    )
    for p in full_patterns:
        if p in low:
            return "full"
    if "كامل" in label and ("رجل" in label or "ساق" in label or "ejren" in compact):
        return "full"
    if re.search(r"kamel.*ejren|ejren.*kamel|kamle.*ejren", compact):
        return "full"
    return "unspecified"


def _score_leg_row(crm_name: str, scope: str) -> float:
    """Higher = better match for a leg row given full/half/unspecified user intent."""
    n = crm_name.lower()
    if not _crm_row_is_leg(n):
        return 0.0
    score = 0.12
    if scope == "full":
        if any(x in n for x in ("full", "كامل", "complete", "entier", "entire")):
            score += 0.72
        if any(x in n for x in ("half", "نص", "partial", "media")):
            score -= 0.58
    elif scope == "half":
        if any(x in n for x in ("half", "نص", "partial", "media", "lower")):
            score += 0.72
        if any(x in n for x in ("full", "كامل", "complete", "entier")):
            score -= 0.48
    else:
        score += 0.28
        if any(x in n for x in ("full", "half", "نص", "كامل")):
            score += 0.08
    return score


def _expand_body_area_synonyms(label: str) -> str:
    """
    Add English / normalized glosses for common LB/AR/FR wording so CRM labels (often EN) score better.
    This is not exhaustive—any zone still falls through to fuzzy matching on the full list.
    """
    label = (label or "").strip()
    if not label:
        return ""
    low = label.lower()
    compact = re.sub(r"[\s_\-]+", "", low)
    extras: List[str] = []
    if any(x in compact for x in ("ejren", "ejrin", "ejeren", "sa2en", "s2en", "se2en")):
        extras.extend(["legs", "leg"])
    if any(x in label for x in ("رجلين", "رجل", "ساقين", "ساق")):
        extras.extend(["legs", "leg"])
    if any(
        x in compact
        for x in (
            "ta7telbat",
            "tahtelbat",
            "t7telbat",
            "7telbat",
            "ta7tlbat",
        )
    ) or "ابط" in label or "إبط" in label:
        extras.extend(["underarm", "armpit"])
    if "bikini" in low or "بيكيني" in label or "bikine" in compact:
        extras.append("bikini")
    if any(x in compact for x in ("dahre", "dahr", "dahra", "zahr")) or "ظهر" in label or "ضهر" in label:
        extras.append("back")
    if "ذقن" in label or "d2n" in compact or "d2en" in compact or "chin" in low:
        extras.extend(["chin", "face"])
    if "بطن" in label or "batn" in compact or "belly" in low or "abdomen" in low:
        extras.extend(["abdomen", "stomach", "belly"])
    if "صدر" in label or "sdr" in compact or "chest" in low or "breast" in low:
        extras.extend(["chest", "breast"])
    if "رقبة" in label or "ra2be" in compact or "ra2bet" in compact or "neck" in low:
        extras.append("neck")
    if "شفايف" in label or "lip" in low or "lips" in low:
        extras.extend(["lip", "lips"])
    if not extras:
        return label
    return f"{label} {' '.join(extras)}".strip()


def match_best_body_part_row(rows: List[dict], label: str) -> Optional[int]:
    """
    Pick one CRM body_part id from live API rows using user text (LB franco, Arabic, English).
    Generally: substring / expanded synonyms, then fuzzy (SequenceMatcher) across all rows.
    Extra logic for **legs** only when the CRM splits e.g. Full Legs vs Half Legs (common example;
    same idea applies elsewhere—map user wording to the closest row name from get_body_parts).
    """
    label = (label or "").strip()
    if not label or not rows:
        return None
    ll = label.lower()
    expanded = _expand_body_area_synonyms(label).lower()
    leg_rows: List[Tuple[int, str]] = []
    best_id: Optional[int] = None
    best_score = 0.0

    for row in rows:
        bid = _safe_int(row.get("id") or row.get("body_part_id"))
        nm = str(row.get("name") or row.get("body_part") or row.get("title") or "").strip().lower()
        if bid is None or not nm:
            continue
        if ll in nm or nm in ll:
            return bid
        if expanded and expanded != ll and (expanded in nm or nm in expanded):
            return bid
        if _crm_row_is_leg(nm):
            leg_rows.append((bid, nm))

    if _text_suggests_legs(label) and leg_rows:
        scope = _legs_scope_from_label(label)
        if scope == "unspecified":
            for bid, nm in leg_rows:
                for src in (expanded, ll):
                    sc = SequenceMatcher(None, src, nm).ratio()
                    if sc > best_score:
                        best_score = sc
                        best_id = bid
            if best_id is not None and best_score >= 0.38:
                return best_id
            if len(leg_rows) == 1:
                return leg_rows[0][0]
        else:
            best_leg: Optional[Tuple[int, float]] = None
            for bid, nm in leg_rows:
                sc = _score_leg_row(nm, scope)
                if best_leg is None or sc > best_leg[1]:
                    best_leg = (bid, sc)
            if best_leg is not None and best_leg[1] >= 0.35:
                return best_leg[0]

    for row in rows:
        bid = _safe_int(row.get("id") or row.get("body_part_id"))
        nm = str(row.get("name") or row.get("body_part") or row.get("title") or "").strip().lower()
        if bid is None or not nm:
            continue
        sc = max(
            SequenceMatcher(None, expanded, nm).ratio(),
            SequenceMatcher(None, ll, nm).ratio(),
        )
        if sc > best_score:
            best_score = sc
            best_id = bid
    if best_id is not None and best_score >= 0.35:
        return best_id
    return None


def server_may_infer_body_parts() -> bool:
    """
    When LINASLASER_BODY_PART_IDS_FROM_AI_ONLY=1 (true/yes/on), the server does not map free-text
    area names to CRM ids — the model must supply body_part_ids from get_body_parts. Tattoo env
    synonyms may still apply for service 13 when the API list is empty.
    """
    v = (os.getenv("LINASLASER_BODY_PART_IDS_FROM_AI_ONLY") or "").strip().lower()
    return v not in ("1", "true", "yes", "on")


async def resolve_body_part_ids(
    service_id: int,
    body_part_label: Optional[str],
    explicit_ids: Optional[List[Any]],
    machine_id: Optional[int] = None,
) -> Tuple[List[int], Optional[str]]:
    raw_ids = explicit_ids or []
    out: List[int] = []
    for x in raw_ids:
        i = _safe_int(x)
        if i is not None:
            out.append(i)
    if out:
        return out, None
    label = (body_part_label or "").strip()
    if not label:
        return [], "body_part"
    if not server_may_infer_body_parts():
        if service_id == TATTOO_SERVICE_ID:
            env_id = _tattoo_body_part_id_from_env_synonyms(label)
            if env_id is not None and env_id > 0:
                return [env_id], None
        return [], "body_part"
    r = await api_integrations.get_body_parts(service_id=service_id, machine_id=machine_id)
    rows = _norm_api_list(r.get("data")) if r.get("success") else []
    if service_id == TATTOO_SERVICE_ID and label and (not r.get("success") or not rows):
        env_id = _tattoo_body_part_id_from_env_synonyms(label)
        if env_id is not None and env_id > 0:
            return [env_id], None
    if not rows:
        return [], "body_part"
    matched = match_best_body_part_row(rows, label)
    if matched is not None:
        return [matched], None
    return [], "body_part"


def machine_label_for(machine_id: int, machines: List[dict]) -> str:
    for m in machines:
        if _safe_int(m.get("id")) == machine_id:
            return str(m.get("name") or "")
    return ""


def is_pico_machine(machine_id: Optional[int], machines: List[dict]) -> bool:
    if machine_id is None:
        return False
    lab = machine_label_for(machine_id, machines).lower()
    return "pico" in lab
