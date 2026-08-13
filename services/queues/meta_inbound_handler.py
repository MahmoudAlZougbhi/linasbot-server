"""Worker handler for durable Meta inbound events."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from services.meta_app_registry import MetaAssetBinding
from services.meta_comment_events import ResolvedMetaCommentEvent
from services.meta_messaging import MetaMessagingSettings
from services.queues.handlers import PermanentJobError
from services.queues.models import QueueJob
from services.scale.inbound_event_store import get_inbound_event, mark_inbound_state


def _settings_from_snapshot(data: dict[str, Any]) -> MetaMessagingSettings:
    return MetaMessagingSettings(
        enabled=bool(data.get("enabled", True)),
        app_secret=str(data.get("app_secret") or ""),
        page_id=str(data.get("page_id") or ""),
        page_access_token=str(data.get("page_access_token") or ""),
        instagram_account_id=str(data.get("instagram_account_id") or ""),
        verify_token=str(data.get("verify_token") or ""),
        graph_api_version=str(data.get("graph_api_version") or "v21.0"),
        app_id=str(data.get("app_id") or ""),
        app_key=str(data.get("app_key") or "linas_first_party"),
        tenant_id=str(data.get("tenant_id") or ""),
        binding_id=str(data.get("binding_id") or ""),
        auth_flow=str(data.get("auth_flow") or "facebook_login"),
        graph_base_url=str(data.get("graph_base_url") or "https://graph.facebook.com"),
    )


def _binding_from_snapshot(data: dict[str, Any]) -> MetaAssetBinding:
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
    if rec.state == "completed":
        return {"skipped": True, "reason": "already_completed", "event_id": event_id}

    mark_inbound_state(event_id, state="processing", bump_attempts=True)
    try:
        if rec.kind == "meta_dm":
            from services.durable_event_claim import complete_event_claim
            from services.meta_cross_flow_dedup import GLOBAL_DM_CLAIM_NAMESPACE
            from services.social_messaging_processor import process_meta_social_event

            settings = _settings_from_snapshot(rec.settings_snapshot)
            outcome = await process_meta_social_event(
                rec.payload,
                settings,
                inbound_event_id=event_id,
            )
            delivered = str((outcome or {}).get("delivery") or "") == "delivered"
            if delivered:
                mark_inbound_state(
                    event_id,
                    state="completed",
                    ai_output_persisted=True,
                    outbound_status="delivered",
                )
                await complete_event_claim(
                    GLOBAL_DM_CLAIM_NAMESPACE,
                    rec.claim_key,
                    firestore_collection="meta_social_dm_global_claims",
                )
            else:
                from services.durable_event_claim import release_event_claim

                mark_inbound_state(
                    event_id,
                    state="failed",
                    ai_output_persisted=bool((outcome or {}).get("logical_reply_id")),
                    outbound_status=str((outcome or {}).get("delivery") or "delivery_pending"),
                    last_error=f"delivery:{(outcome or {}).get('delivery')}",
                )
                await release_event_claim(
                    GLOBAL_DM_CLAIM_NAMESPACE,
                    rec.claim_key,
                    firestore_collection="meta_social_dm_global_claims",
                )
            return {"ok": delivered, "kind": "meta_dm", "event_id": event_id, "outcome": outcome}

        if rec.kind == "meta_comment":
            from services.durable_event_claim import complete_event_claim
            from services.meta_comment_replies import process_meta_comment_event
            from services.meta_cross_flow_dedup import GLOBAL_COMMENT_CLAIM_NAMESPACE

            settings = _settings_from_snapshot(rec.settings_snapshot)
            binding = _binding_from_snapshot(rec.binding_snapshot)
            resolved = ResolvedMetaCommentEvent(event=rec.payload, settings=settings, binding=binding)
            result = await process_meta_comment_event(resolved)
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
            )
            return {
                "ok": True,
                "kind": "meta_comment",
                "event_id": event_id,
                "result": asdict(result) if hasattr(result, "__dataclass_fields__") else str(result),
            }
        raise PermanentJobError(f"unsupported_kind:{rec.kind}")
    except PermanentJobError:
        mark_inbound_state(event_id, state="dead_letter", last_error="permanent")
        raise
    except Exception as exc:
        mark_inbound_state(event_id, state="failed", last_error=f"{type(exc).__name__}:{exc}")
        raise
