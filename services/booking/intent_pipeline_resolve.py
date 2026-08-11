"""Resolve CRM ids / datetime for submit_booking_intent (LOC split)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import config
from services.booking.constants import (
    BEIRUT_BRANCH_ID,
    BOOKING_TIMEZONE_LABEL,
    DEFAULT_BODY_PART_REQUIRED_SERVICE_IDS,
    HAIR_REMOVAL_MACHINE_IDS,
    LASER_HAIR_REMOVAL_SERVICE_IDS,
    TATTOO_SERVICE_ID,
    _service_requires_machine,
)
from services.booking.intent_pipeline_helpers import (
    _build_api_datetime,
    _coerce_int_id,
)
from services.booking.resolver import (
    is_pico_machine,
    load_branches,
    load_machines,
    load_services,
    pick_default_machine_for_non_hair,
    pick_pico_or_default_machine,
    resolve_body_part_ids,
    resolve_branch_id,
    resolve_machine_id,
    resolve_service_id,
)
from services.booking_service_mapping import validate_service_mapping_from_text
from utils.datetime_utils import BOT_FIXED_TZ


@dataclass
class SubmitResolveResult:
    intent: dict[str, Any]
    services: list[Any]
    branches: list[Any]
    machines: list[Any]
    missing: list[str] = field(default_factory=list)
    conflicts: dict[str, Any] = field(default_factory=dict)
    ambiguities: list[Any] = field(default_factory=list)
    invalid: dict[str, Any] = field(default_factory=dict)
    svc_id: int | None = None
    br_id: int | None = None
    mach_id: int | None = None
    body_ids: list[int] = field(default_factory=list)
    machine_required: bool = False
    dt_local: Any = None
    dt_resolution: str | None = None
    norm_vals: dict[str, Any] = field(default_factory=dict)


async def resolve_submit_booking_entities(
    *,
    intent: dict[str, Any],
    raw_msg: str,
    user_input: str,
    gender_raw: str,
    backend_resolves: bool,
    execute: bool,
) -> SubmitResolveResult:
    """Load catalogs and resolve service/branch/machine/body/datetime for submit."""
    services = await load_services()
    branches = await load_branches()
    machines = await load_machines()

    missing: list[str] = []
    conflicts: dict[str, Any] = {}
    svc_id: int | None = None
    br_id: int | None = None
    mach_id: int | None = None
    mach_miss: str | None = None
    body_ids: list[int] = []
    had_branch_hint = bool(intent.get("branch_name")) or intent.get("branch_id") is not None
    machine_required = False

    if backend_resolves:
        svc_miss: str | None
        svc_id, svc_miss = resolve_service_id(
            intent.get("service_name"),
            intent.get("service_id"),
            gender_raw,
            services,
        )
        br_miss: str | None
        br_id, br_miss = resolve_branch_id(intent.get("branch_name"), intent.get("branch_id"), branches)
        if br_id is None:
            br_id = int(config.DEFAULT_BRANCH_ID or BEIRUT_BRANCH_ID)
        if svc_miss:
            missing.append(svc_miss)
        if br_miss and had_branch_hint:
            missing.append(br_miss)

        machine_required = _service_requires_machine(svc_id)
        if machine_required and svc_id in LASER_HAIR_REMOVAL_SERVICE_IDS:
            mach_id, mach_miss = resolve_machine_id(
                intent.get("machine_name"),
                intent.get("machine_id"),
                machines,
            )
            if mach_miss:
                missing.append(mach_miss)
        elif machine_required and svc_id == TATTOO_SERVICE_ID:
            mach_id, _ = resolve_machine_id(
                intent.get("machine_name"),
                intent.get("machine_id"),
                machines,
            )
            if mach_id is None or not is_pico_machine(mach_id, machines):
                mach_id = pick_pico_or_default_machine(machines)
            if mach_id is None:
                missing.append("machine_id")
                mach_miss = "machine_id"
        elif machine_required:
            mach_id = resolve_machine_id(
                intent.get("machine_name"),
                intent.get("machine_id"),
                machines,
            )[0]
            if mach_id is None:
                mach_id = pick_default_machine_for_non_hair(svc_id or 0, machines)
            if mach_id is None:
                missing.append("machine_id")
                mach_miss = "machine_id"
        else:
            mach_id = None

        if svc_id == TATTOO_SERVICE_ID and not str(intent.get("body_part") or "").strip():
            um = (raw_msg or "").lower()
            if any(
                tok in um
                for tok in (
                    "ra2be",
                    "ra2bet",
                    "ra2bte",
                    "رقبة",
                    "رقبت",
                    "neck",
                    "عنق",
                    "3an2",
                )
            ):
                intent = dict(intent)
                intent["body_part"] = (raw_msg or "").strip()[:280]

        bp_miss: str | None = None
        if svc_id is not None:
            explicit = intent.get("body_part_ids")
            if isinstance(explicit, list) and explicit:
                body_ids, bp_miss = await resolve_body_part_ids(svc_id, intent.get("body_part"), explicit, mach_id)
            else:
                body_ids, bp_miss = await resolve_body_part_ids(svc_id, intent.get("body_part"), None, mach_id)
            if bp_miss:
                missing.append(bp_miss)
    else:
        # Executor-only: AI must supply CRM IDs from get_* tools — no server-side name→id mapping.
        svc_id = _coerce_int_id(intent.get("service_id"))
        if svc_id is None:
            missing.append("service_id")
        allowed_sids = {_coerce_int_id(s.get("id")) for s in services}
        allowed_sids.discard(None)
        if svc_id is not None and svc_id not in allowed_sids:
            conflicts["service_id"] = {
                "detail": "service_id not found in live CRM services list; call get_services and resend.",
                "service_id": svc_id,
            }

        br_id = _coerce_int_id(intent.get("branch_id"))
        if br_id is None:
            missing.append("branch_id")
        allowed_bids = {_coerce_int_id(b.get("id")) for b in branches}
        allowed_bids.discard(None)
        if br_id is not None and br_id not in allowed_bids:
            conflicts["branch_id"] = {
                "detail": "branch_id not found in live CRM branch list; call get_branches and resend.",
                "branch_id": br_id,
            }

        mach_id = _coerce_int_id(intent.get("machine_id"))
        machine_required = _service_requires_machine(svc_id)
        if not machine_required:
            mach_id = None
        if svc_id is not None:
            if machine_required and svc_id in LASER_HAIR_REMOVAL_SERVICE_IDS:
                if mach_id is None:
                    missing.append("machine_id")
                elif mach_id not in HAIR_REMOVAL_MACHINE_IDS:
                    conflicts["machine_service"] = {
                        "detail": "machine_id must be a hair-removal device from get_machines for this service.",
                        "machine_id": mach_id,
                        "allowed_machine_ids": sorted(HAIR_REMOVAL_MACHINE_IDS),
                    }
            elif machine_required and svc_id == TATTOO_SERVICE_ID:
                if mach_id is None:
                    missing.append("machine_id")
            elif machine_required:
                if mach_id is None:
                    missing.append("machine_id")

        ex_bp = intent.get("body_part_ids")
        if isinstance(ex_bp, list):
            for x in ex_bp:
                i = _coerce_int_id(x)
                if i is not None and i > 0:
                    body_ids.append(i)
        if svc_id is not None and svc_id in DEFAULT_BODY_PART_REQUIRED_SERVICE_IDS and not body_ids:
            missing.append("body_part_ids")

    dt_local, dt_missing, ambiguities, dt_resolution = _build_api_datetime(intent)
    for m in dt_missing:
        if m not in missing:
            missing.append(m)

    _require_resolved_dt = bool(getattr(config, "BOOKING_REQUIRE_RESOLVED_DATETIME", False)) or not backend_resolves
    if execute and _require_resolved_dt and dt_resolution == "legacy_raw" and dt_local is not None:
        missing.append("resolved_datetime")
        ambiguities.append("booking_requires_explicit_date_and_time_not_raw_nl_only")

    if intent.get("needs_clarification"):
        ambiguities.extend([str(x) for x in (intent.get("ambiguities") or [])])

    invalid: dict[str, Any] = {}

    if svc_id in LASER_HAIR_REMOVAL_SERVICE_IDS and mach_id is not None:
        if mach_id not in HAIR_REMOVAL_MACHINE_IDS and "machine_service" not in conflicts:
            conflicts["machine_service"] = {
                "detail": "Selected machine is not in the allowed hair-removal device set for this bot.",
                "machine_id": mach_id,
                "allowed_machine_ids": sorted(HAIR_REMOVAL_MACHINE_IDS),
            }

    if svc_id is not None and user_input:
        map_chk = validate_service_mapping_from_text(user_input, svc_id)
        if not map_chk.get("is_valid"):
            conflicts["service_text_intent"] = {
                "detail": "User wording suggests a different service family than service_id.",
                "mapping_check": map_chk,
            }

    norm_vals: dict[str, Any] = {
        "service_id": svc_id,
        "branch_id": br_id,
        "machine_id": mach_id,
        "machine_required": machine_required,
        "body_part_ids": body_ids,
        "timezone": BOOKING_TIMEZONE_LABEL,
        "datetime_resolution_source": dt_resolution,
    }
    if dt_local is not None:
        norm_vals["api_date"] = dt_local.astimezone(BOT_FIXED_TZ).strftime("%Y-%m-%d %H:%M:%S")

    return SubmitResolveResult(
        intent=intent,
        services=services,
        branches=branches,
        machines=machines,
        missing=missing,
        conflicts=conflicts,
        ambiguities=ambiguities,
        invalid=invalid,
        svc_id=svc_id,
        br_id=br_id,
        mach_id=mach_id,
        body_ids=body_ids,
        machine_required=machine_required,
        dt_local=dt_local,
        dt_resolution=dt_resolution,
        norm_vals=norm_vals,
    )
