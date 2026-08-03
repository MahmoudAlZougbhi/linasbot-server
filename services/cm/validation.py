"""Aggregate CM draft validation (notes + restricted conflicts)."""

from __future__ import annotations

from typing import Any

from services.cm.conflict_validation import validate_restricted_conflicts
from services.cm.constants import CM_SECTIONS
from services.cm.notes_validation import validate_notes_in_payload
from services.cm.schemas import ValidationFailure
from services.cm.storage import UnknownSectionError, get_draft


def _notes_failures(section: str, payload: dict[str, object]) -> list[dict[str, Any]]:
    codes = validate_notes_in_payload(payload, path_prefix=f"{section}.payload")
    out: list[dict[str, Any]] = []
    for code in codes:
        out.append(
            {
                "level": "error",
                "severity": "error",
                "code": code,
                "message": f"Notes validation failed: {code}",
                "section": section,
            }
        )
    return out


def _conflict_dict(failure: ValidationFailure, *, section: str | None = None) -> dict[str, Any]:
    return {
        "level": failure.severity,
        "severity": failure.severity,
        "code": failure.code,
        "message": failure.message,
        "path": failure.path,
        "section": section,
        "details": failure.details,
    }


def validate_cm(
    *,
    section: str | None = None,
    payload: dict[str, object] | None = None,
    tenant_id: str | None = None,
) -> dict[str, Any]:
    """Run conflict + notes validation across drafts (optional in-memory section override)."""
    errors: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []

    drafts: dict[str, dict[str, object]] = {}
    for name in CM_SECTIONS:
        try:
            env = get_draft(name, tenant_id=tenant_id, create_default=True)
            drafts[name] = dict(env.payload)
        except UnknownSectionError:
            continue

    if section:
        name = section.strip().replace("-", "_")
        if name not in CM_SECTIONS:
            raise UnknownSectionError(f"Unknown CM section: {section!r}")
        if payload is not None:
            drafts[name] = payload

    for name, section_payload in drafts.items():
        for issue in _notes_failures(name, section_payload):
            (errors if issue["level"] == "error" else warnings).append(issue)

    conflict_failures = validate_restricted_conflicts(
        restricted=drafts.get("restricted") or {},
        services=drafts.get("services"),
        prices=drafts.get("prices"),
        faq=drafts.get("faq"),
        knowledge=drafts.get("knowledge"),
        handoff=drafts.get("handoff"),
    )
    for failure in conflict_failures:
        item = _conflict_dict(failure, section="restricted")
        if failure.severity == "warning":
            warnings.append(item)
        else:
            errors.append(item)

    return {
        "ok": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
        "error_count": len(errors),
        "warning_count": len(warnings),
    }
