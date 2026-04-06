# -*- coding: utf-8 -*-
"""Resolve human-readable booking hints to CRM IDs using live API lists."""

from __future__ import annotations

import json
import os
import re
from difflib import SequenceMatcher
from typing import Any, Dict, List, Optional, Tuple

from services import api_integrations
import config

from services.booking.constants import (
    ANTELIAS_BRANCH_ID,
    BEIRUT_BRANCH_ID,
    HAIR_MEN,
    HAIR_WOMEN,
    HAIR_REMOVAL_MACHINE_IDS,
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


def _alnum_compact(s: str) -> str:
    return re.sub(r"[^a-z0-9\u0600-\u06ff]", "", (s or "").lower())


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
        return None, "machine_id"
    nu = _alnum_compact(n)
    best = None
    best_score = 0.0
    for m in machines:
        mn_raw = str(m.get("name") or "")
        mn = mn_raw.lower()
        if not mn:
            continue
        mid_c = _safe_int(m.get("id"))
        if mid_c is None:
            continue
        if n in mn or mn in n:
            return mid_c, None
        mu = _alnum_compact(mn_raw)
        if nu and mu and len(nu) >= 2 and (nu in mu or mu in nu):
            return mid_c, None
        for kw in ("neo", "candela", "quadro", "trio", "dpl", "pico"):
            if kw in n and kw in mn:
                return mid_c, None
        sc = SequenceMatcher(None, n, mn).ratio()
        if sc > best_score:
            best_score = sc
            best = mid_c
    if best is not None and best_score >= 0.4:
        return best, None
    # Last resort: map common spoken names to hair-removal devices present in CRM
    for m in machines:
        mid_c = _safe_int(m.get("id"))
        mn = str(m.get("name") or "").lower()
        if mid_c is None or mid_c not in HAIR_REMOVAL_MACHINE_IDS or not mn:
            continue
        for kw in ("neo", "candela", "quadro", "trio", "dpl"):
            if kw in n and kw in mn:
                return mid_c, None
    return None, "machine_id"


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


def _split_composite_body_label(label: str) -> List[str]:
    """
    Split user-written multi-area phrases (Arabic و, commas, +) into one label per CRM row.
    Example: «بكيني ومؤخرة» → [«بكيني», «مؤخرة»]
    """
    s = (label or "").strip()
    if not s:
        return []
    if "و" in s and len(s) > 2:
        parts = [p.strip() for p in s.split("و") if p.strip()]
        if len(parts) >= 2:
            return parts
    parts = re.split(r"\s*[،,/+]\s*", s)
    parts = [p.strip() for p in parts if p.strip()]
    return parts if len(parts) > 1 else [s]


def _match_body_part_label_to_id(rows: List[dict], segment: str) -> Optional[int]:
    """Map one human phrase to a single body_part id from API rows."""
    if not rows or not (segment or "").strip():
        return None
    ll = segment.strip().lower()
    best_id: Optional[int] = None
    best_score = 0.0
    for row in rows:
        bid = _safe_int(row.get("id") or row.get("body_part_id"))
        nm = str(row.get("name") or row.get("body_part") or row.get("title") or "").strip().lower()
        if bid is None or not nm:
            continue
        if ll in nm or nm in ll:
            return bid
        sc = SequenceMatcher(None, ll, nm).ratio()
        if sc > best_score:
            best_score = sc
            best_id = bid
    if best_id is not None and best_score >= 0.35:
        return best_id
    return None


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

    async def _fetch_rows(mid: Optional[int]) -> Tuple[List[dict], bool]:
        r = await api_integrations.get_body_parts(service_id=service_id, machine_id=mid)
        ok = bool(r.get("success"))
        rows = _norm_api_list(r.get("data")) if ok else []
        return rows, ok

    rows, r_ok = await _fetch_rows(machine_id)
    if not rows and machine_id is not None:
        rows, r_ok = await _fetch_rows(None)

    if service_id == TATTOO_SERVICE_ID and label and (not r_ok or not rows):
        env_id = _tattoo_body_part_id_from_env_synonyms(label)
        if env_id is not None and env_id > 0:
            return [env_id], None
    if not rows:
        return [], "body_part"

    segments = _split_composite_body_label(label)
    collected: List[int] = []
    for seg in segments:
        bid = _match_body_part_label_to_id(rows, seg)
        if bid is None:
            return [], "body_part"
        if bid not in collected:
            collected.append(bid)
    return collected, None


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


def server_may_infer_body_parts() -> bool:
    """
    When True, chat_response may map free-text body areas to CRM body_part_ids
    (conversation hints, auxiliary JSON recovery). Controlled by LINASLASER_BOOKING_LEGACY_INFERENCE / config.
    """
    return bool(getattr(config, "BOOKING_LEGACY_INFERENCE", False))


def match_best_body_part_row(rows: List[dict], label: str) -> Optional[int]:
    """
    Pick the best CRM body_part id from get_body_parts rows for a human label (substring then fuzzy).
    Used by chat_response recovery paths; same scoring as resolve_body_part_ids.
    """
    return _match_body_part_label_to_id(rows, label)
