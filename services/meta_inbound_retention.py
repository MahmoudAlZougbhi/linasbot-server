"""Privacy retention and authorization-scoped redaction for Meta inbound ledgers."""

from __future__ import annotations

import os
import time
from collections.abc import Callable
from contextlib import nullcontext
from typing import Any

from services.scale import inbound_event_store as event_store

DEFAULT_META_INBOUND_PAYLOAD_RETENTION_DAYS = 30
_SAFE_REDACTED_SETTINGS_KEYS = frozenset({"app_key", "binding_id", "auth_flow"})
_SAFE_REDACTED_BINDING_KEYS = frozenset(
    {
        "binding_id",
        "channel",
        "app_key",
        "auth_flow",
    }
)


def meta_inbound_payload_retention_seconds() -> float:
    raw = (os.getenv("META_INBOUND_PAYLOAD_RETENTION_DAYS") or str(DEFAULT_META_INBOUND_PAYLOAD_RETENTION_DAYS)).strip()
    try:
        days = int(raw)
    except ValueError:
        days = DEFAULT_META_INBOUND_PAYLOAD_RETENTION_DAYS
    return float(max(1, days) * 24 * 60 * 60)


def _safe_subset(value: object, allowed: frozenset[str]) -> dict[str, Any]:
    source = value if isinstance(value, dict) else {}
    return {
        str(key): item
        for key, item in source.items()
        if str(key) in allowed and (isinstance(item, (str, bool, int, float)) or item is None)
    }


def _binding_id(raw: dict[str, Any]) -> str:
    binding = raw.get("binding_snapshot")
    settings = raw.get("settings_snapshot")
    binding_data = binding if isinstance(binding, dict) else {}
    settings_data = settings if isinstance(settings, dict) else {}
    return str(binding_data.get("binding_id") or settings_data.get("binding_id") or "").strip()


def redacted_inbound_event_tombstone(raw: dict[str, Any], *, reason: str, now: float) -> dict[str, Any]:
    """Build the complete allowlisted representation of a redacted event.

    This deliberately does not merge with ``raw``.  Unknown legacy/future keys
    may contain personal data, so a deletion acknowledgement can only follow a
    full replacement with this closed schema.
    """

    try:
        created_at = float(raw.get("created_at") or now)
    except (TypeError, ValueError):
        created_at = float(now)
    try:
        attempts = max(0, int(raw.get("attempts") or 0))
    except (TypeError, ValueError):
        attempts = 0
    previous_redacted_at = raw.get("retention_redacted_at")
    same_redaction = raw.get("retention_status") == "redacted" and raw.get("retention_reason") == reason
    if same_redaction:
        try:
            redacted_at = float(str(previous_redacted_at))
        except (TypeError, ValueError):
            redacted_at = float(now)
    else:
        redacted_at = float(now)
    kind = str(raw.get("kind") or "meta_dm")
    if kind not in {"meta_dm", "meta_comment"}:
        kind = "meta_dm"
    state = str(raw.get("state") or "dead_letter")
    if state not in event_store.TERMINAL_STATES:
        state = "dead_letter"
    try:
        updated_at = float(str(raw.get("updated_at"))) if same_redaction else float(now)
    except (TypeError, ValueError):
        updated_at = float(now)
    return {
        "event_id": str(raw.get("event_id") or ""),
        "kind": kind,
        "tenant_id": "",
        "claim_namespace": "",
        "payload": {},
        "settings_snapshot": _safe_subset(raw.get("settings_snapshot"), _SAFE_REDACTED_SETTINGS_KEYS),
        "binding_snapshot": _safe_subset(raw.get("binding_snapshot"), _SAFE_REDACTED_BINDING_KEYS),
        "claim_key": "",
        "state": state,
        "created_at": created_at,
        "updated_at": updated_at,
        "conversation_key": "",
        "queue_job_id": None,
        "attempts": attempts,
        "last_error": None,
        "outbound_status": None,
        "ai_output_persisted": False,
        "retention_status": "redacted",
        "retention_reason": reason,
        "retention_redacted_at": redacted_at,
    }


def _already_redacted(raw: dict[str, Any], tombstone: dict[str, Any]) -> bool:
    return raw == tombstone


def _empty_stats(*, apply: bool, include_firestore: bool) -> dict[str, int | bool]:
    return {
        "apply": apply,
        "local_scanned": 0,
        "local_matched": 0,
        "local_changed": 0,
        "local_redacted": 0,
        "local_active_matches": 0,
        "local_orphan_files": 0,
        "local_orphans_removed": 0,
        "local_errors": 0,
        "firestore_requested": include_firestore,
        "firestore_available": False,
        "firestore_scanned": 0,
        "firestore_matched": 0,
        "firestore_changed": 0,
        "firestore_redacted": 0,
        "firestore_active_matches": 0,
        "firestore_errors": 0,
    }


def _redact_ledgers(
    *,
    selector: Callable[[dict[str, Any]], bool],
    older_than: float | None,
    reason: str,
    apply: bool,
    include_local: bool = True,
    include_firestore: bool,
    active_matches_block: bool,
    now: float | None,
) -> dict[str, int | bool]:
    current = time.time() if now is None else float(now)
    stats = _empty_stats(apply=apply, include_firestore=include_firestore)

    if include_local:
        local_lock = event_store.local_inbound_event_ledger_lock() if apply else nullcontext()
        with local_lock:
            try:
                orphan_paths = list(event_store._store_dir().glob(".ibe_*.tmp"))
                if apply:
                    for orphan_path in orphan_paths:
                        try:
                            orphan_path.unlink()
                            stats["local_orphans_removed"] = int(stats["local_orphans_removed"]) + 1
                        except OSError:
                            stats["local_errors"] = int(stats["local_errors"]) + 1
                    orphan_paths = list(event_store._store_dir().glob(".ibe_*.tmp"))
                stats["local_orphan_files"] = len(orphan_paths)
                local_file_count = sum(1 for _ in event_store._store_dir().glob("ibe_*.json"))
                local_documents = list(event_store.iter_local_inbound_event_documents())
            except OSError as exc:
                raise RuntimeError("Local inbound ledger scan failed") from exc
            stats["local_errors"] = int(stats["local_errors"]) + max(0, local_file_count - len(local_documents))
            for path, raw in local_documents:
                stats["local_scanned"] = int(stats["local_scanned"]) + 1
                if not selector(raw):
                    continue
                state = str(raw.get("state") or "").strip().lower()
                if state not in event_store.TERMINAL_STATES:
                    if active_matches_block:
                        stats["local_active_matches"] = int(stats["local_active_matches"]) + 1
                    continue
                try:
                    updated_at = float(raw.get("updated_at") or raw.get("created_at") or 0.0)
                except (TypeError, ValueError):
                    stats["local_errors"] = int(stats["local_errors"]) + 1
                    continue
                if older_than is not None and updated_at > older_than:
                    continue
                stats["local_matched"] = int(stats["local_matched"]) + 1
                tombstone = redacted_inbound_event_tombstone(raw, reason=reason, now=current)
                if _already_redacted(raw, tombstone):
                    continue
                stats["local_changed"] = int(stats["local_changed"]) + 1
                if apply:
                    try:
                        event_store.replace_local_inbound_event_document(path, tombstone)
                        stats["local_redacted"] = int(stats["local_redacted"]) + 1
                    except (OSError, ValueError):
                        stats["local_errors"] = int(stats["local_errors"]) + 1

    if not include_firestore:
        return stats

    from utils.utils import get_firestore_db

    db = get_firestore_db()
    if db is None:
        raise RuntimeError("Firestore is unavailable for inbound ledger redaction")
    stats["firestore_available"] = True
    collection = db.collection("artifacts").document("linas-ai-bot-backend").collection("inbound_events")
    try:
        snapshots = collection.stream()
        for snapshot in snapshots:
            stats["firestore_scanned"] = int(stats["firestore_scanned"]) + 1
            try:
                raw = snapshot.to_dict() or {}
            except Exception:
                stats["firestore_errors"] = int(stats["firestore_errors"]) + 1
                continue
            if not isinstance(raw, dict):
                stats["firestore_errors"] = int(stats["firestore_errors"]) + 1
                continue
            if not selector(raw):
                continue
            state = str(raw.get("state") or "").strip().lower()
            if state not in event_store.TERMINAL_STATES:
                if active_matches_block:
                    stats["firestore_active_matches"] = int(stats["firestore_active_matches"]) + 1
                continue
            try:
                updated_at = float(raw.get("updated_at") or raw.get("created_at") or 0.0)
            except (TypeError, ValueError):
                stats["firestore_errors"] = int(stats["firestore_errors"]) + 1
                continue
            if older_than is not None and updated_at > older_than:
                continue
            stats["firestore_matched"] = int(stats["firestore_matched"]) + 1
            tombstone = redacted_inbound_event_tombstone(raw, reason=reason, now=current)
            if _already_redacted(raw, tombstone):
                continue
            stats["firestore_changed"] = int(stats["firestore_changed"]) + 1
            if apply:
                try:
                    snapshot.reference.set(tombstone)
                    stats["firestore_redacted"] = int(stats["firestore_redacted"]) + 1
                except Exception:
                    stats["firestore_errors"] = int(stats["firestore_errors"]) + 1
    except Exception as exc:
        raise RuntimeError("Firestore inbound ledger scan failed") from exc
    return stats


def redact_expired_terminal_inbound_events(
    *,
    apply: bool,
    include_firestore: bool = True,
    retention_seconds: float | None = None,
    now: float | None = None,
) -> dict[str, int | bool]:
    current = time.time() if now is None else float(now)
    retention = (
        meta_inbound_payload_retention_seconds() if retention_seconds is None else max(0.0, float(retention_seconds))
    )
    return _redact_ledgers(
        selector=lambda _raw: True,
        older_than=current - retention,
        reason="retention_expired",
        apply=apply,
        include_firestore=include_firestore,
        active_matches_block=False,
        now=current,
    )


def redact_inbound_events_for_bindings(
    binding_ids: set[str] | frozenset[str],
    *,
    apply: bool,
    include_firestore: bool = True,
    now: float | None = None,
) -> dict[str, int | bool]:
    targets = frozenset(str(value).strip() for value in binding_ids if str(value).strip())
    return _redact_ledgers(
        selector=lambda raw: bool(targets) and _binding_id(raw) in targets,
        older_than=None,
        reason="authorization_data_deletion",
        apply=apply,
        include_firestore=include_firestore,
        active_matches_block=True,
        now=now,
    )


def redact_local_inbound_events_for_bindings(
    binding_ids: set[str] | frozenset[str],
    *,
    apply: bool,
    now: float | None = None,
) -> dict[str, int | bool]:
    """Redact only this node's private inbound-event ledger."""

    targets = frozenset(str(value).strip() for value in binding_ids if str(value).strip())
    return _redact_ledgers(
        selector=lambda raw: bool(targets) and _binding_id(raw) in targets,
        older_than=None,
        reason="authorization_data_deletion",
        apply=apply,
        include_local=True,
        include_firestore=False,
        active_matches_block=True,
        now=now,
    )


def redact_shared_inbound_events_for_bindings(
    binding_ids: set[str] | frozenset[str],
    *,
    apply: bool,
    now: float | None = None,
) -> dict[str, int | bool]:
    """Redact only the Firestore HA ledger used by the deletion coordinator."""

    targets = frozenset(str(value).strip() for value in binding_ids if str(value).strip())
    return _redact_ledgers(
        selector=lambda raw: bool(targets) and _binding_id(raw) in targets,
        older_than=None,
        reason="authorization_data_deletion",
        apply=apply,
        include_local=False,
        include_firestore=True,
        active_matches_block=True,
        now=now,
    )


def inbound_redaction_has_blockers(
    stats: dict[str, int | bool],
    *,
    require_firestore: bool,
) -> bool:
    return bool(
        int(stats.get("local_errors") or 0)
        or int(stats.get("local_orphan_files") or 0)
        or int(stats.get("firestore_errors") or 0)
        or int(stats.get("local_active_matches") or 0)
        or int(stats.get("firestore_active_matches") or 0)
        or (require_firestore and not bool(stats.get("firestore_available")))
    )
