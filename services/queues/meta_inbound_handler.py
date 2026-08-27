"""Worker handler for durable Meta inbound events."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import asdict
from typing import Any

from services.meta_app_registry import MetaAssetBinding
from services.meta_comment_events import ResolvedMetaCommentEvent
from services.meta_controlled_evidence import log_meta_controlled_evidence, meta_evidence_surface
from services.meta_messaging import MetaMessagingSettings
from services.queues.handlers import PermanentJobError
from services.queues.models import QueueJob
from services.scale.inbound_event_store import TERMINAL_STATES, get_inbound_event, mark_inbound_state

_runtime_logger = logging.getLogger("uvicorn.error")


def _evidence_channel(data: dict[str, Any], binding_data: dict[str, Any]) -> str:
    channel = str(data.get("channel") or binding_data.get("channel") or "").strip().lower()
    return channel if channel in {"facebook", "instagram"} else "unknown"


async def _settle_failed_event_claim(rec: Any, *, terminal: bool, claim_handle: Any) -> None:
    """Complete terminal claims or release retryable ones without leaking payloads."""

    from services.durable_event_claim import complete_event_claim, release_event_claim
    from services.meta_cross_flow_dedup import GLOBAL_COMMENT_CLAIM_NAMESPACE, GLOBAL_DM_CLAIM_NAMESPACE

    if rec.kind == "meta_dm":
        namespace = GLOBAL_DM_CLAIM_NAMESPACE
        collection = "meta_social_dm_global_claims"
    elif rec.kind == "meta_comment":
        namespace = GLOBAL_COMMENT_CLAIM_NAMESPACE
        collection = "meta_social_comment_global_claims"
    else:
        return
    operation = complete_event_claim if terminal else release_event_claim
    try:
        await operation(
            namespace,
            rec.claim_key,
            firestore_collection=collection,
            claim_handle=claim_handle,
        )
    except Exception as exc:
        _runtime_logger.warning(
            "[meta-inbound] claim_settle_failed kind=%s terminal=%s type=%s",
            rec.kind,
            terminal,
            type(exc).__name__,
        )


def _same_binding_identity(left: MetaAssetBinding, right: MetaAssetBinding) -> bool:
    return (
        left.tenant_id == right.tenant_id
        and left.channel == right.channel
        and left.asset_id == right.asset_id
        and left.app_key == right.app_key
        and left.auth_flow == right.auth_flow
    )


def _resolve_active_registry_binding(
    data: dict[str, Any],
    binding_data: dict[str, Any],
) -> MetaAssetBinding:
    """Follow an authenticated binding's replacement chain without crossing assets."""

    from services.meta_app_registry import get_meta_app_registry

    binding_id = str(binding_data.get("binding_id") or data.get("binding_id") or "").strip()
    if not binding_id or binding_id == "legacy-single-app":
        raise PermanentJobError("meta binding identifier is unavailable")
    registry = get_meta_app_registry()
    all_bindings = registry.list_bindings(include_inactive=True, include_superseded=True)
    original = next((item for item in all_bindings if item.binding_id == binding_id), None)
    if original is None:
        raise PermanentJobError("meta binding is unavailable")

    expected_identity = (
        str(binding_data.get("tenant_id") or data.get("tenant_id") or "").strip(),
        str(binding_data.get("channel") or data.get("channel") or "").strip(),
        str(binding_data.get("asset_id") or "").strip(),
        str(binding_data.get("app_key") or data.get("app_key") or "").strip(),
        str(binding_data.get("auth_flow") or data.get("auth_flow") or "").strip(),
    )
    actual_identity = (
        original.tenant_id,
        original.channel,
        original.asset_id,
        original.app_key,
        original.auth_flow,
    )
    if any(not value for value in expected_identity) or actual_identity != expected_identity:
        raise PermanentJobError("meta binding snapshot identity is invalid")

    by_id = {item.binding_id: item for item in all_bindings if _same_binding_identity(item, original)}
    connected: dict[str, MetaAssetBinding] = {}
    pending = [original]
    while pending:
        current = pending.pop()
        if current.binding_id in connected:
            continue
        connected[current.binding_id] = current
        if current.previous_binding_id and current.previous_binding_id in by_id:
            pending.append(by_id[current.previous_binding_id])
        pending.extend(
            item
            for item in by_id.values()
            if item.previous_binding_id == current.binding_id and item.binding_id not in connected
        )
    active = [item for item in connected.values() if item.active]
    if len(active) != 1:
        raise PermanentJobError("meta binding has no unique active replacement")
    return active[0]


def _settings_from_snapshot(
    data: dict[str, Any],
    binding_data: dict[str, Any],
) -> MetaMessagingSettings:
    """Rehydrate secrets from their source of truth, never from the event ledger.

    Registry-backed events use the current encrypted credential.  Legacy events
    re-read process environment settings.  Old ledger rows may still contain
    plaintext secret keys; this function deliberately ignores those values.
    """

    binding_id = str(binding_data.get("binding_id") or data.get("binding_id") or "").strip()
    if binding_id and binding_id != "legacy-single-app":
        from services.meta_app_registry import get_meta_app_configs, get_meta_app_registry
        from services.meta_graph_routing import build_messaging_settings_for_binding

        registry = get_meta_app_registry()
        binding = _resolve_active_registry_binding(data, binding_data)
        credential = registry.get_credential(binding)
        app_config = get_meta_app_configs().get(binding.app_key)
        if app_config is None:
            raise PermanentJobError("meta app configuration is unavailable")
        return build_messaging_settings_for_binding(
            binding,
            credential=credential,
            app_config=app_config,
        )

    from services.meta_messaging import get_meta_messaging_settings

    settings = get_meta_messaging_settings()
    if not settings.page_access_token:
        raise RuntimeError("legacy Meta credential is unavailable")
    return settings


def _binding_from_snapshot(data: dict[str, Any], *, resolved_binding_id: str = "") -> MetaAssetBinding:
    if resolved_binding_id and resolved_binding_id != "legacy-single-app":
        binding = _resolve_active_registry_binding(
            {"binding_id": str(data.get("binding_id") or "")},
            data,
        )
        if binding.binding_id != resolved_binding_id:
            raise PermanentJobError("resolved Meta binding changed during processing")
        return binding
    return MetaAssetBinding(
        binding_id=str(data.get("binding_id") or "unknown"),
        tenant_id=str(data.get("tenant_id") or ""),
        channel=str(data.get("channel") or "facebook"),  # type: ignore[arg-type]
        asset_id=str(data.get("asset_id") or ""),
        page_id=str(data.get("page_id") or ""),
        instagram_account_id=str(data.get("instagram_account_id") or ""),
        app_key=str(data.get("app_key") or "linas_first_party"),
        credential_id=str(data.get("credential_id") or ""),
        status=str(data.get("status") or "active"),  # type: ignore[arg-type]
        generation=int(data.get("generation") or 1),
        created_at=float(data.get("created_at") or 0.0),
        updated_at=float(data.get("updated_at") or 0.0),
        auth_flow=str(data.get("auth_flow") or "facebook_login"),  # type: ignore[arg-type]
    )


async def handle_meta_inbound_process(job: QueueJob) -> dict[str, Any]:
    event_id = str((job.payload or {}).get("event_id") or "").strip()
    if not event_id:
        raise PermanentJobError("missing event_id")
    rec = get_inbound_event(event_id)
    if rec is None:
        raise PermanentJobError(f"inbound_event_missing:{event_id}")
    if rec.state in TERMINAL_STATES:
        return {"skipped": True, "reason": f"already_{rec.state}", "event_id": event_id}

    from services.durable_event_claim import (
        event_claim_handle_from_token,
        meta_claim_binding_digest,
        renew_event_claim,
        try_claim_event_handle,
    )
    from services.meta_cross_flow_dedup import GLOBAL_COMMENT_CLAIM_NAMESPACE, GLOBAL_DM_CLAIM_NAMESPACE

    if rec.kind == "meta_dm":
        claim_namespace = GLOBAL_DM_CLAIM_NAMESPACE
        claim_collection = "meta_social_dm_global_claims"
    elif rec.kind == "meta_comment":
        claim_namespace = GLOBAL_COMMENT_CLAIM_NAMESPACE
        claim_collection = "meta_social_comment_global_claims"
    else:
        raise PermanentJobError(f"unsupported_kind:{rec.kind}")
    claim_token = str((job.payload or {}).get("_claim_token") or "").strip()
    claim_generation = int((job.payload or {}).get("_claim_generation") or 1)
    claim_handle = None
    if claim_token:
        try:
            candidate = event_claim_handle_from_token(
                claim_namespace,
                rec.claim_key,
                firestore_collection=claim_collection,
                owner_token=claim_token,
                generation=claim_generation,
            )
        except ValueError as exc:
            raise PermanentJobError("invalid Meta inbound claim capability") from exc
        if await renew_event_claim(candidate, ttl_seconds=300.0):
            claim_handle = candidate
    if claim_handle is None:
        # Legacy queued jobs carry no capability. They may safely adopt only an
        # expired/released generation; an active peer owner remains untouched.
        claim_handle = await try_claim_event_handle(
            claim_namespace,
            rec.claim_key,
            ttl_seconds=300.0,
            firestore_collection=claim_collection,
            firestore_claim_metadata={
                "binding_id_sha256": meta_claim_binding_digest(
                    str(rec.binding_snapshot.get("binding_id") or rec.settings_snapshot.get("binding_id") or "")
                ),
                "inbound_event_id": event_id,
            },
            meta_binding_id=str(
                rec.binding_snapshot.get("binding_id") or rec.settings_snapshot.get("binding_id") or ""
            ),
        )
    if claim_handle is None:
        return {"skipped": True, "reason": "claim_owned_by_peer", "event_id": event_id}

    mark_inbound_state(event_id, state="processing", bump_attempts=True)
    try:
        if rec.kind == "meta_dm":
            from services.durable_event_claim import complete_event_claim
            from services.meta_cross_flow_dedup import GLOBAL_DM_CLAIM_NAMESPACE
            from services.social_messaging_processor import (
                meta_social_outcome_requires_retry,
                process_meta_social_event,
            )

            settings = _settings_from_snapshot(rec.settings_snapshot, rec.binding_snapshot)
            outbound_tenant_id = str(rec.tenant_id or rec.binding_snapshot.get("tenant_id") or "").strip()
            outbound_binding_id = str(rec.binding_snapshot.get("binding_id") or "").strip()
            if not outbound_binding_id:
                # Only the legacy settings branch above can reach an old row
                # without a durable binding snapshot.
                outbound_binding_id = "legacy-single-app"
            evidence_surface = meta_evidence_surface(
                kind="meta_dm",
                channel=_evidence_channel(rec.payload, rec.binding_snapshot),
            )
            from services.durable_event_claim import run_under_event_claim

            outcome = await run_under_event_claim(
                claim_handle,
                ttl_seconds=300.0,
                operation=lambda: process_meta_social_event(
                    rec.payload,
                    settings,
                    inbound_event_id=event_id,
                    tenant_id=outbound_tenant_id,
                    binding_id=outbound_binding_id,
                ),
            )
            delivery = str((outcome or {}).get("delivery") or "unknown")
            retryable = meta_social_outcome_requires_retry(outcome)
            if delivery in {"combine_scheduled", "combine_superseded"}:
                mark_inbound_state(event_id, state="queued", outbound_status=delivery)
                await complete_event_claim(
                    GLOBAL_DM_CLAIM_NAMESPACE,
                    rec.claim_key,
                    firestore_collection="meta_social_dm_global_claims",
                    claim_handle=claim_handle,
                )
                return {
                    "ok": True,
                    "kind": "meta_dm",
                    "event_id": event_id,
                    "outcome": outcome,
                    "deferred": True,
                }
            if not retryable:
                extra_ids = [
                    str(item) for item in list((outcome or {}).get("combined_event_ids") or []) if str(item).strip()
                ]
                skip_reason = str((outcome or {}).get("reason") or "").strip() if delivery == "skipped" else ""
                for eid in [event_id, *[item for item in extra_ids if item != event_id]]:
                    mark_inbound_state(
                        eid,
                        state="completed",
                        ai_output_persisted=bool((outcome or {}).get("logical_reply_id")),
                        outbound_status=delivery,
                        last_error=skip_reason or None,
                    )
                await complete_event_claim(
                    GLOBAL_DM_CLAIM_NAMESPACE,
                    rec.claim_key,
                    firestore_collection="meta_social_dm_global_claims",
                    claim_handle=claim_handle,
                )
                if delivery == "delivered" and (outcome or {}).get("provider_message_id_present") is True:
                    log_meta_controlled_evidence(
                        _runtime_logger,
                        event_id=event_id,
                        surface=evidence_surface,
                        outcome="provider_accepted",
                    )
                elif delivery == "duplicate_suppressed":
                    log_meta_controlled_evidence(
                        _runtime_logger,
                        event_id=event_id,
                        surface=evidence_surface,
                        outcome="duplicate_suppressed",
                    )
                else:
                    log_meta_controlled_evidence(
                        _runtime_logger,
                        event_id=event_id,
                        surface=evidence_surface,
                        outcome="failed",
                    )
            else:
                mark_inbound_state(
                    event_id,
                    state="failed",
                    ai_output_persisted=bool((outcome or {}).get("logical_reply_id")),
                    outbound_status=delivery,
                    last_error=f"delivery:{delivery}",
                )
                log_meta_controlled_evidence(
                    _runtime_logger,
                    event_id=event_id,
                    surface=evidence_surface,
                    outcome="retry",
                )
                raise RuntimeError(f"retryable Meta DM outcome: {delivery}")
            return {"ok": not retryable, "kind": "meta_dm", "event_id": event_id, "outcome": outcome}

        if rec.kind == "meta_comment":
            from services.durable_event_claim import complete_event_claim
            from services.meta_comment_replies import comment_reply_requires_retry, process_meta_comment_event
            from services.meta_cross_flow_dedup import GLOBAL_COMMENT_CLAIM_NAMESPACE

            settings = _settings_from_snapshot(rec.settings_snapshot, rec.binding_snapshot)
            evidence_surface = meta_evidence_surface(
                kind="meta_comment",
                channel=_evidence_channel(rec.payload, rec.binding_snapshot),
            )
            binding = _binding_from_snapshot(
                rec.binding_snapshot,
                resolved_binding_id=settings.binding_id,
            )
            resolved = ResolvedMetaCommentEvent(event=rec.payload, settings=settings, binding=binding)
            from services.durable_event_claim import run_under_event_claim

            result = await run_under_event_claim(
                claim_handle,
                ttl_seconds=300.0,
                operation=lambda: process_meta_comment_event(resolved, inbound_event_id=event_id),
            )
            if comment_reply_requires_retry(result):
                mark_inbound_state(
                    event_id,
                    state="failed",
                    ai_output_persisted=False,
                    outbound_status=f"{result.status}:{result.reason}",
                    last_error=f"comment:{result.status}:{result.reason}",
                )
                log_meta_controlled_evidence(
                    _runtime_logger,
                    event_id=event_id,
                    surface=evidence_surface,
                    outcome="retry",
                )
                raise RuntimeError(f"retryable Meta comment outcome: {result.reason}")
            mark_inbound_state(
                event_id,
                state="completed",
                ai_output_persisted=True,
                outbound_status=f"{result.status}:{result.reason}",
            )
            await complete_event_claim(
                GLOBAL_COMMENT_CLAIM_NAMESPACE,
                rec.claim_key,
                firestore_collection="meta_social_comment_global_claims",
                claim_handle=claim_handle,
            )
            if result.status in {"sent", "sent_dm"}:
                log_meta_controlled_evidence(
                    _runtime_logger,
                    event_id=event_id,
                    surface=evidence_surface,
                    outcome="provider_accepted",
                )
            elif result.status == "ignored" and result.reason == "already_replied":
                log_meta_controlled_evidence(
                    _runtime_logger,
                    event_id=event_id,
                    surface=evidence_surface,
                    outcome="duplicate_suppressed",
                )
            else:
                log_meta_controlled_evidence(
                    _runtime_logger,
                    event_id=event_id,
                    surface=evidence_surface,
                    outcome="failed",
                )
            return {
                "ok": True,
                "kind": "meta_comment",
                "event_id": event_id,
                "result": asdict(result) if hasattr(result, "__dataclass_fields__") else str(result),
            }
        raise PermanentJobError(f"unsupported_kind:{rec.kind}")
    except PermanentJobError:
        log_meta_controlled_evidence(
            _runtime_logger,
            event_id=event_id,
            surface=meta_evidence_surface(
                kind=rec.kind,
                channel=_evidence_channel(rec.payload, rec.binding_snapshot),
            ),
            outcome="failed",
        )
        mark_inbound_state(event_id, state="dead_letter", last_error="permanent")
        await _settle_failed_event_claim(rec, terminal=True, claim_handle=claim_handle)
        raise
    except asyncio.CancelledError:
        log_meta_controlled_evidence(
            _runtime_logger,
            event_id=event_id,
            surface=meta_evidence_surface(
                kind=rec.kind,
                channel=_evidence_channel(rec.payload, rec.binding_snapshot),
            ),
            outcome="failed",
        )
        mark_inbound_state(event_id, state="failed", last_error="processing_cancelled")
        await _settle_failed_event_claim(rec, terminal=False, claim_handle=claim_handle)
        raise
    except Exception as exc:
        log_meta_controlled_evidence(
            _runtime_logger,
            event_id=event_id,
            surface=meta_evidence_surface(
                kind=rec.kind,
                channel=_evidence_channel(rec.payload, rec.binding_snapshot),
            ),
            outcome="failed",
        )
        # Keep the durable ledger free of raw provider/AI exception messages.
        mark_inbound_state(event_id, state="failed", last_error=f"exception:{type(exc).__name__}")
        await _settle_failed_event_claim(rec, terminal=False, claim_handle=claim_handle)
        raise
