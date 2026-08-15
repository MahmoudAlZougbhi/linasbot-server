"""Binding-scoped deletion of Meta claim and outbound-attempt state.

Plans contain only internal document ids/paths. They are built while the
authorization's inbound rows still retain the selectors needed to find legacy
claim records, then applied and verified before those inbound rows are redacted.
"""

from __future__ import annotations

import json
import stat
import time
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from services.durable_event_claim import (
    _file_claim_path,
    _firestore_claim_document_id,
    local_event_claim_store_lock,
    meta_claim_binding_digest,
)

_APP_ID = "linas-ai-bot-backend"
_GLOBAL_COLLECTIONS = {
    "meta_dm": ("meta_social_dm_global", "meta_social_dm_global_claims"),
    "meta_comment": ("meta_social_comment_global", "meta_social_comment_global_claims"),
}
_CLAIM_COLLECTIONS = (
    "meta_social_dm_global_claims",
    "meta_social_comment_global_claims",
    "ai_turn_claims",
    "ai_turn_claims_file",
    "meta_outbound_attempts",
)


def _claim_root() -> Path:
    import services.durable_event_claim as durable_claims

    return durable_claims._claims_dir()


class MetaClaimDeletionError(RuntimeError):
    """Claim state could not be fully selected, removed, or verified."""


class MetaClaimDeletionActiveError(MetaClaimDeletionError):
    """A selected provider/AI operation is still live."""


def _mapping(value: object) -> dict[str, Any]:
    return cast(dict[str, Any], value) if isinstance(value, dict) else {}


@dataclass(frozen=True)
class MetaClaimDeletionPlan:
    shared_documents: tuple[tuple[str, str], ...] = ()
    local_files: tuple[Path, ...] = ()


@dataclass(frozen=True)
class _ClaimSelectors:
    event_ids: frozenset[str]
    global_claims: tuple[tuple[str, str, str], ...]
    provider_message_ids: frozenset[str]
    stable_identities: frozenset[str]

    @property
    def global_keys(self) -> frozenset[str]:
        return frozenset(item[2] for item in self.global_claims)


def _binding_id(raw: dict[str, Any]) -> str:
    binding = _mapping(raw.get("binding_snapshot"))
    settings = _mapping(raw.get("settings_snapshot"))
    return str(binding.get("binding_id") or settings.get("binding_id") or "").strip()


def _event_stable_identities(raw: dict[str, Any]) -> frozenset[str]:
    payload = _mapping(raw.get("payload"))
    binding = _mapping(raw.get("binding_snapshot"))
    settings = _mapping(raw.get("settings_snapshot"))
    tenant_id = str(raw.get("tenant_id") or binding.get("tenant_id") or settings.get("tenant_id") or "").strip()
    channel = str(payload.get("channel") or binding.get("channel") or "").strip().lower()
    asset_id = str(
        binding.get("asset_id") or settings.get("instagram_account_id") or settings.get("page_id") or ""
    ).strip()
    sender_id = str(payload.get("sender_id") or payload.get("sender") or "").strip()
    if not (tenant_id and channel and asset_id and sender_id):
        return frozenset()
    candidates: set[str] = set()
    try:
        from services.social_user_id import compose_social_user_id

        candidates.add(
            compose_social_user_id(
                tenant_id=tenant_id,
                channel=channel,
                asset_id=asset_id,
                sender_id=sender_id,
            )
        )
    except Exception:
        pass
    # Historical Linas identities changed shape when a channel gained/lost a
    # second active asset. Preserve both exact contracts without consulting the
    # mutable current registry topology.
    if tenant_id.strip().lower() == "linas":
        candidates.update({f"{channel}:{sender_id}", f"{channel}:{asset_id}:{sender_id}"})
    else:
        candidates.add(f"{tenant_id.strip().lower()}:{channel}:{asset_id}:{sender_id}")
    return frozenset(value for value in candidates if value)


def _matching_event_selectors(
    records: Iterable[dict[str, Any]],
    binding_ids: frozenset[str],
) -> _ClaimSelectors:
    event_ids: set[str] = set()
    global_claims: set[tuple[str, str, str]] = set()
    provider_message_ids: set[str] = set()
    stable_identities: set[str] = set()
    for raw in records:
        if _binding_id(raw) not in binding_ids:
            continue
        event_id = str(raw.get("event_id") or "").strip().lower()
        kind = str(raw.get("kind") or "")
        claim_key = str(raw.get("claim_key") or "")
        if event_id.startswith("ibe_") and len(event_id) == 44:
            event_ids.add(event_id)
        contract = _GLOBAL_COLLECTIONS.get(kind)
        if contract and claim_key:
            namespace, collection = contract
            global_claims.add((namespace, collection, claim_key))
        payload = _mapping(raw.get("payload"))
        message_id = str(payload.get("message_id") or "").strip()
        if message_id:
            provider_message_ids.add(message_id)
        stable_identities.update(_event_stable_identities(raw))
    return _ClaimSelectors(
        event_ids=frozenset(event_ids),
        global_claims=tuple(sorted(global_claims)),
        provider_message_ids=frozenset(provider_message_ids),
        stable_identities=frozenset(stable_identities),
    )


def _snapshot_dict(snapshot: Any) -> dict[str, Any]:
    try:
        value = snapshot.to_dict()
    except Exception as exc:
        raise MetaClaimDeletionError("Meta claim document is unreadable") from exc
    if not isinstance(value, dict):
        raise MetaClaimDeletionError("Meta claim document is invalid")
    return value


def _snapshot_document_id(snapshot: Any) -> str:
    document_id = str(getattr(snapshot, "id", "") or "").strip()
    if document_id:
        return document_id
    path = str(getattr(getattr(snapshot, "reference", None), "path", ""))
    document_id = path.rsplit("/", 1)[-1].strip()
    if not document_id:
        raise MetaClaimDeletionError("Meta claim document identity is invalid")
    return document_id


def _historical_claim_matches(raw: dict[str, Any], selectors: _ClaimSelectors) -> bool:
    key_prefix = str(raw.get("key_prefix") or "")
    if key_prefix:
        if key_prefix in selectors.global_keys:
            return True
        components = key_prefix.split("\0", 2)
        if len(components) >= 2 and components[0] in selectors.stable_identities:
            return True
    preview = str(raw.get("inbound_ids_preview") or "")
    if preview and any(item in selectors.provider_message_ids for item in preview.split("|")):
        return True
    stable_identity = str(raw.get("stable_identity") or "")
    return bool(stable_identity and stable_identity in selectors.stable_identities)


def _claim_is_active(raw: dict[str, Any]) -> bool:
    status_value = str(raw.get("status") or "").strip().lower()
    if status_value == "sending":
        return True
    if status_value != "claimed":
        return False
    try:
        expires_at = float(raw.get("expires_at_epoch") or 0.0)
    except (TypeError, ValueError):
        return True
    # Legacy claimed rows without an expiry are ambiguous and require an
    # operator decision instead of deletion beneath a possibly live worker.
    return expires_at <= 0.0 or expires_at > time.time()


def build_shared_meta_claim_deletion_plan(
    db: Any,
    binding_ids: set[str] | frozenset[str],
) -> MetaClaimDeletionPlan:
    """Select all known shared claim rows for the exact bindings."""

    targets = frozenset(str(value).strip() for value in binding_ids if str(value).strip())
    from services.meta_outbound_attempts import (
        MetaOutboundAttemptStoreError,
        reconcile_fenced_image_quota_attempts_for_bindings,
    )

    try:
        reconcile_fenced_image_quota_attempts_for_bindings(db, targets)
    except MetaOutboundAttemptStoreError as exc:
        raise MetaClaimDeletionError("Meta outbound-attempt reconciliation failed") from exc
    digests = {meta_claim_binding_digest(value) for value in targets}
    app = db.collection("artifacts").document(_APP_ID)
    try:
        inbound_records = [_snapshot_dict(snapshot) for snapshot in app.collection("inbound_events").stream()]
    except Exception as exc:
        raise MetaClaimDeletionError("Meta inbound claim selection failed") from exc
    selectors = _matching_event_selectors(inbound_records, targets)
    documents: set[tuple[str, str]] = set()
    for namespace, collection, claim_key in selectors.global_claims:
        document_id = _firestore_claim_document_id(namespace, claim_key)
        try:
            if app.collection(collection).document(document_id).get().exists:
                documents.add((collection, document_id))
        except Exception as exc:
            raise MetaClaimDeletionError("Meta global claim selection failed") from exc

    for collection_name in _CLAIM_COLLECTIONS:
        try:
            snapshots = list(app.collection(collection_name).stream())
        except Exception as exc:
            raise MetaClaimDeletionError("Meta claim collection scan failed") from exc
        for snapshot in snapshots:
            raw = _snapshot_dict(snapshot)
            document_id = _snapshot_document_id(snapshot)
            selected = str(raw.get("binding_id_sha256") or "") in digests
            selected = selected or str(raw.get("inbound_event_id") or "") in selectors.event_ids
            selected = selected or _historical_claim_matches(raw, selectors)
            if collection_name == "meta_outbound_attempts":
                selected = selected or document_id in selectors.event_ids
            if selected:
                if _claim_is_active(raw):
                    raise MetaClaimDeletionActiveError("Meta claim operation is still active")
                documents.add((collection_name, document_id))
    return MetaClaimDeletionPlan(shared_documents=tuple(sorted(documents)))


def verify_shared_meta_claim_deletion_plan(db: Any, plan: MetaClaimDeletionPlan) -> int:
    app = db.collection("artifacts").document(_APP_ID)
    remaining = 0
    for collection_name, document_id in plan.shared_documents:
        try:
            if app.collection(collection_name).document(document_id).get().exists:
                remaining += 1
        except Exception as exc:
            raise MetaClaimDeletionError("Meta claim deletion verification failed") from exc
    return remaining


def apply_shared_meta_claim_deletion_plan(db: Any, plan: MetaClaimDeletionPlan) -> dict[str, int]:
    app = db.collection("artifacts").document(_APP_ID)
    changed = 0
    errors = 0
    for collection_name, document_id in plan.shared_documents:
        reference = app.collection(collection_name).document(document_id)
        try:
            snapshot = reference.get()
            if snapshot.exists:
                reference.delete()
                changed += 1
        except Exception:
            errors += 1
    remaining = verify_shared_meta_claim_deletion_plan(db, plan)
    return {"matched": len(plan.shared_documents), "changed": changed, "remaining": remaining, "errors": errors}


def _read_local_inbound_records() -> list[dict[str, Any]]:
    from services.scale.inbound_event_store import _store_dir

    records: list[dict[str, Any]] = []
    try:
        paths = list(_store_dir().glob("ibe_*.json"))
        for path in paths:
            if path.is_symlink() or not stat.S_ISREG(path.lstat().st_mode):
                raise MetaClaimDeletionError("Local Meta inbound claim selector is unsafe")
            raw = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(raw, dict):
                raise MetaClaimDeletionError("Local Meta inbound claim selector is invalid")
            records.append(raw)
    except MetaClaimDeletionError:
        raise
    except Exception as exc:
        raise MetaClaimDeletionError("Local Meta claim selection failed") from exc
    return records


def _safe_local_claim_files() -> list[tuple[Path, dict[str, Any]]]:
    root = _claim_root().resolve()
    selected: list[tuple[Path, dict[str, Any]]] = []
    try:
        for path in _claim_root().rglob("*"):
            if path.name == ".claims.lock" or path.is_dir():
                continue
            if (
                path.is_symlink()
                or not stat.S_ISREG(path.lstat().st_mode)
                or path.resolve().is_relative_to(root) is False
            ):
                raise MetaClaimDeletionError("Local Meta claim file is unsafe")
            if path.suffix != ".json":
                # A writer cannot coexist while the claim lock is held. Any
                # remaining temp/unknown file may contain historical raw keys.
                raise MetaClaimDeletionError("Local Meta claim orphan requires sanitation")
            raw = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(raw, dict):
                raise MetaClaimDeletionError("Local Meta claim file is invalid")
            selected.append((path, raw))
    except MetaClaimDeletionError:
        raise
    except Exception as exc:
        raise MetaClaimDeletionError("Local Meta claim scan failed") from exc
    return selected


def build_local_meta_claim_deletion_plan(binding_ids: set[str] | frozenset[str]) -> MetaClaimDeletionPlan:
    """Select exact local claim files; caller must hold the claim-store lock."""

    targets = frozenset(str(value).strip() for value in binding_ids if str(value).strip())
    digests = {meta_claim_binding_digest(value) for value in targets}
    selectors = _matching_event_selectors(_read_local_inbound_records(), targets)
    paths = {
        _file_claim_path(namespace, claim_key)
        for namespace, _collection, claim_key in selectors.global_claims
        if _file_claim_path(namespace, claim_key).is_file()
    }
    for path, raw in _safe_local_claim_files():
        selected = str(raw.get("binding_id_sha256") or "") in digests
        selected = selected or str(raw.get("inbound_event_id") or "") in selectors.event_ids
        selected = selected or _historical_claim_matches(raw, selectors)
        if selected:
            if _claim_is_active(raw):
                raise MetaClaimDeletionActiveError("Local Meta claim operation is still active")
            paths.add(path)
    return MetaClaimDeletionPlan(local_files=tuple(sorted(paths)))


def verify_local_meta_claim_deletion_plan(plan: MetaClaimDeletionPlan) -> int:
    return sum(1 for path in plan.local_files if path.exists())


def apply_local_meta_claim_deletion_plan(plan: MetaClaimDeletionPlan) -> dict[str, int]:
    changed = 0
    errors = 0
    for path in plan.local_files:
        try:
            if path.exists():
                path.unlink()
                changed += 1
        except OSError:
            errors += 1
    remaining = verify_local_meta_claim_deletion_plan(plan)
    return {"matched": len(plan.local_files), "changed": changed, "remaining": remaining, "errors": errors}


def delete_and_verify_local_meta_claims(binding_ids: set[str] | frozenset[str]) -> dict[str, int]:
    """Hold the process/host lock across local selection, deletion, and proof."""

    with local_event_claim_store_lock():
        plan = build_local_meta_claim_deletion_plan(binding_ids)
        totals = apply_local_meta_claim_deletion_plan(plan)
        residual = build_local_meta_claim_deletion_plan(binding_ids)
        if residual.local_files:
            totals["remaining"] = len(residual.local_files)
        return totals
