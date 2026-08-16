"""Bridge normalized Meta social events into the existing AI conversation pipeline."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any, cast

import config
from handlers.text_handlers import handle_message
from handlers.text_handlers_firestore import _delayed_processing_tasks
from services.meta_messaging import (
    SOCIAL_DISPLAY_NAME_FALLBACK,
    MetaMessagingAdapter,
    MetaMessagingSettings,
    is_unresolved_social_display_name,
    pick_meta_participant_display_name,
    resolve_meta_send_account_id,
)
from utils.utils import get_user_state_from_firestore, save_user_name_to_firestore

SendFunc = Callable[..., Awaitable[Any]]
_TERMINAL_META_DELIVERIES = frozenset({"delivered", "blocked_quota", "no_text", "permanent_block"})


def meta_social_outcome_requires_retry(outcome: dict[str, Any] | None) -> bool:
    """Classify provider/intent outcomes consistently across webhook and queue paths."""

    result = outcome if isinstance(outcome, dict) else {}
    explicit = result.get("retryable")
    if isinstance(explicit, bool):
        return explicit
    delivery = str(result.get("delivery") or "unknown").strip().lower()
    return delivery not in _TERMINAL_META_DELIVERIES


def _is_image_attachment(item: Any) -> bool:
    return bool(item) and (not isinstance(item, dict) or str(item.get("type") or "").lower() == "image")


def _truncate_image_attachments(attachments: list[Any], allowed_amount: int) -> list[Any]:
    kept: list[Any] = []
    seen = 0
    limit = max(0, int(allowed_amount))
    for item in attachments:
        if _is_image_attachment(item):
            if seen < limit:
                kept.append(item)
            seen += 1
        else:
            kept.append(item)
    return kept


async def _deliver_image_quota_notice(
    *,
    message: str,
    user_id: str,
    sender_id: str,
    channel: str,
    binding_id: str,
    inbound_event_id: str | None,
    quota_disposition: str,
    quota_allowed_amount: int,
    adapter: MetaMessagingAdapter | None,
    capture_send: SendFunc | None,
) -> dict[str, Any] | None:
    if not message:
        return None
    if capture_send is not None:
        await capture_send(user_id, message, None, None)
        return None
    if adapter is None:
        return None
    if inbound_event_id:
        from services.meta_controlled_evidence import meta_evidence_surface
        from services.meta_outbound_attempts import execute_guarded_meta_send

        result = await execute_guarded_meta_send(
            event_id=inbound_event_id,
            surface=meta_evidence_surface(kind="meta_dm", channel=channel),
            binding_id=binding_id,
            purpose="image_quota_notice",
            image_quota_disposition=quota_disposition,
            image_quota_allowed_amount=quota_allowed_amount,
            image_quota_notice_text=message,
            send=lambda: adapter.send_text_message(sender_id, message),
        )
    else:
        result = await adapter.send_text_message(sender_id, message)

    from services.ai_reply_delivery import classify_send_result

    evidence = classify_send_result(result)
    if evidence.get("success") or evidence.get("duplicate_suppressed"):
        return None
    if evidence.get("needs_owner_action"):
        return {
            "ok": False,
            "delivery": "needs_owner_action",
            "retryable": False,
            "terminal": True,
        }
    retryable = bool(evidence.get("retryable", True))
    return {
        "ok": False,
        "delivery": "quota_notice_failed",
        "retryable": retryable,
        "terminal": not retryable,
    }


async def _await_delayed_processing(user_id: str) -> None:
    """Await the latest combine task without deleting a newer replacement.

    Rapid messages intentionally cancel the old combine-delay task and install a
    replacement that owns the whole pending batch. Every accepted webhook waiter
    must follow that replacement so its durable event reaches the same terminal
    outcome; an older waiter must never pop or cancel the newer task.
    """

    while True:
        maybe_task = cast(asyncio.Task[Any] | None, _delayed_processing_tasks.get(user_id))
        if maybe_task is None:
            return
        task: asyncio.Task[Any] = maybe_task
        try:
            # Multiple accepted events may await the same replacement. Shield it
            # so cancellation of one webhook waiter cannot cancel the shared work.
            await asyncio.shield(task)
        except asyncio.CancelledError:
            current = asyncio.current_task()
            if current is not None and current.cancelling():
                raise
            replacement = _delayed_processing_tasks.get(user_id)
            if replacement is None or replacement is task:
                raise
            continue
        finally:
            if _delayed_processing_tasks.get(user_id) is task and task.done():
                _delayed_processing_tasks.pop(user_id, None)

        replacement = _delayed_processing_tasks.get(user_id)
        if replacement is None or replacement is task:
            return


async def _resolve_social_customer_display_name(
    *,
    user_id: str,
    sender_id: str,
    event: dict[str, Any],
    adapter: MetaMessagingAdapter | None,
    persisted_state: dict[str, Any] | None,
    skip_persist: bool,
) -> str:
    """
    Resolve the Meta participant's display name for Live Chat + AI context.

    Order: webhook fields → in-memory → Firestore → Graph User Profile → honest fallback.
    Never invent names. Never keep "Instagram Customer" / "Facebook Customer".
    """
    webhook_name = pick_meta_participant_display_name(
        name=str(event.get("sender_name") or event.get("name") or ""),
        username=str(event.get("sender_username") or event.get("username") or ""),
    )
    if webhook_name:
        config.user_names[user_id] = webhook_name
        if not skip_persist:
            try:
                await save_user_name_to_firestore(user_id, webhook_name)
            except Exception as exc:
                print(f"[meta-social] name_persist_skipped type={type(exc).__name__}")
        return webhook_name

    cached = str(config.user_names.get(user_id) or "").strip()
    if cached and not is_unresolved_social_display_name(cached):
        return cached

    persisted_name = pick_meta_participant_display_name(name=(persisted_state or {}).get("name"))
    if persisted_name:
        config.user_names[user_id] = persisted_name
        return persisted_name

    if adapter is not None:
        profile = await adapter.fetch_participant_profile(sender_id)
        graph_name = pick_meta_participant_display_name(
            name=profile.get("name"),
            first_name=profile.get("first_name"),
            last_name=profile.get("last_name"),
            username=profile.get("username"),
        )
        if graph_name:
            config.user_names[user_id] = graph_name
            if not skip_persist:
                try:
                    await save_user_name_to_firestore(user_id, graph_name)
                except Exception as exc:
                    print(f"[meta-social] name_persist_skipped type={type(exc).__name__}")
            return graph_name

    # Honest temporary label — not channel-branded placeholders.
    config.user_names[user_id] = SOCIAL_DISPLAY_NAME_FALLBACK
    return SOCIAL_DISPLAY_NAME_FALLBACK


async def process_meta_social_event(
    event: dict[str, Any],
    settings: MetaMessagingSettings,
    *,
    capture_send: SendFunc | None = None,
    simulation: bool = False,
    combine_delay: float | None = None,
    inbound_event_id: str | None = None,
    tenant_id: str = "",
    binding_id: str = "",
) -> dict[str, Any]:
    """
    Process one normalized Meta IG/FB event through the canonical AI path.

    When ``simulation`` is True (Testing Lab), external Graph sends are skipped and
    ``capture_send`` is used instead. Production webhooks must leave simulation=False.
    """
    channel = str(event["channel"])
    sender_id = str(event["sender_id"])
    resolved_tenant_id = str(tenant_id or settings.tenant_id or "").strip()
    if not resolved_tenant_id:
        raise ValueError("tenant_id required for social messaging")
    account_id = resolve_meta_send_account_id(channel, event, settings)
    resolved_binding_id = str(binding_id or settings.binding_id or "").strip()
    asset_id = settings.instagram_account_id if channel == "instagram" else settings.page_id
    from services.social_user_id import compose_social_user_id

    user_id = compose_social_user_id(
        tenant_id=resolved_tenant_id,
        channel=channel,
        asset_id=asset_id,
        sender_id=sender_id,
    )

    adapter = None
    if not simulation:
        adapter = MetaMessagingAdapter(
            access_token=settings.page_access_token,
            account_id=account_id,
            channel=channel,
            graph_api_version=settings.graph_api_version,
            graph_base_url=settings.graph_base_url,
        )
    try:
        if user_id not in config.user_data_whatsapp:
            config.user_data_whatsapp[user_id] = {
                "user_preferred_lang": "ar",
                "initial_user_query_to_process": None,
                "awaiting_human_handover_confirmation": False,
                "current_conversation_id": None,
                **config.DEFAULT_CONVERSATION_STATE,
            }
        user_data = config.user_data_whatsapp[user_id]
        from services.ai_reply_turn_runtime import reset_turn_runtime_state

        reset_turn_runtime_state(user_data)
        user_data.update(
            {
                "channel": channel,
                "social_sender_id": sender_id,
                "meta_account_id": account_id,
                "tenant_id": resolved_tenant_id,
                "meta_app_key": str(event.get("meta_app_key") or settings.app_key),
                "meta_binding_id": resolved_binding_id,
                # Namespaced non-phone identity so CRM phone tools never treat this as a mobile.
                "phone_number": f"room:{user_id}",
                "_source_message_id": str(event.get("message_id") or ""),
            }
        )
        if inbound_event_id:
            user_data["_inbound_event_id"] = inbound_event_id
        else:
            user_data.pop("_inbound_event_id", None)
        if simulation:
            user_data["_meta_social_lab_simulation"] = True
        # Bounded handoff TTL: drop expired channel-scoped social_contact_flow blobs.
        from services.social_contact_routing import (
            expire_social_contact_flows_in_user_data,
            restore_social_booking_preference,
        )

        expire_social_contact_flows_in_user_data(user_data)

        persisted_state: dict[str, Any] = {}
        try:
            persisted_state = await get_user_state_from_firestore(user_id) or {}
        except Exception as exc:
            # A social identity contains a platform-scoped sender ID. Keep it and
            # exception text out of logs; the error type is sufficient to operate.
            print(f"[meta-social] state_restore_skipped type={type(exc).__name__}")

        restore_social_booking_preference(user_data, persisted_state)

        display_name = await _resolve_social_customer_display_name(
            user_id=user_id,
            sender_id=sender_id,
            event=event,
            adapter=adapter,
            persisted_state=persisted_state,
            skip_persist=bool(simulation),
        )

        # Social booking uses only the scope-isolated customer-selected preference
        # restored above.  Do not restore the legacy unscoped profile gender here.

        text = str(event.get("text") or "").strip()
        attachments = event.get("attachments") or []
        image_attachment_count = 0
        if isinstance(attachments, list):
            image_attachment_count = sum(1 for item in attachments if _is_image_attachment(item))
        if image_attachment_count > 0:
            from services.ai_limits_enforcement import (
                customer_image_limit_message,
                enforce_image_analysis_quota,
            )
            from services.meta_controlled_evidence import meta_evidence_surface
            from services.meta_outbound_attempts import (
                confirm_image_quota_consumed,
                finalize_allowed_image_quota,
                reconcile_image_quota_receipt,
                reserve_image_quota_notice,
            )

            surface = meta_evidence_surface(kind="meta_dm", channel=channel)
            guarded_quota = bool(inbound_event_id and capture_send is None and adapter is not None)
            receipt = None
            if guarded_quota:
                receipt = await reconcile_image_quota_receipt(
                    event_id=str(inbound_event_id),
                    surface=surface,
                    binding_id=resolved_binding_id,
                )
            quota_disposition = ""
            quota_allowed_amount = 0
            quota_message = ""
            quota_reason = ""
            if receipt is not None:
                quota_disposition = receipt.image_quota_disposition
                quota_allowed_amount = receipt.image_quota_allowed_amount
                quota_message = receipt.image_quota_notice_text
                quota_reason = "image_quota_replay"
                if receipt.status == "needs_owner_action" or (
                    receipt.status == "sending" and receipt.image_quota_phase in {"reserved", "provider"}
                ):
                    return {
                        "ok": False,
                        "delivery": "needs_owner_action",
                        "retryable": False,
                        "terminal": True,
                    }
                if quota_disposition == "allowed" and receipt.status == "sending":
                    if not await finalize_allowed_image_quota(
                        event_id=str(inbound_event_id),
                        surface=surface,
                        binding_id=resolved_binding_id,
                        allowed_amount=quota_allowed_amount,
                    ):
                        return {
                            "ok": False,
                            "delivery": "needs_owner_action",
                            "retryable": False,
                            "terminal": True,
                        }
            else:
                planned_quota = enforce_image_analysis_quota(
                    user_id=user_id,
                    user_data=user_data,
                    amount=image_attachment_count,
                    consume=False,
                )
                planned_allowed = int(planned_quota.allowed_amount or 0)
                if not planned_quota.allowed:
                    quota_disposition = "blocked"
                    quota_allowed_amount = 0
                elif planned_allowed < image_attachment_count:
                    quota_disposition = "truncated"
                    quota_allowed_amount = planned_allowed
                else:
                    quota_disposition = "allowed"
                    quota_allowed_amount = planned_allowed

                if quota_disposition in {"blocked", "truncated"}:
                    quota_message = customer_image_limit_message(planned_quota)
                quota_reason = str(planned_quota.reason or "image_quota_limited")
                reservation = None
                if guarded_quota:
                    reservation = await reserve_image_quota_notice(
                        event_id=str(inbound_event_id),
                        surface=surface,
                        binding_id=resolved_binding_id,
                        disposition=quota_disposition,
                        allowed_amount=quota_allowed_amount,
                        notice_text=quota_message,
                    )
                    if reservation.kind == "needs_owner_action":
                        return {
                            "ok": False,
                            "delivery": "needs_owner_action",
                            "retryable": False,
                            "terminal": True,
                        }
                    if reservation.kind not in {
                        "quota_reserved",
                        "duplicate_suppressed",
                        "nonproduction_bypass",
                    }:
                        return {
                            "ok": False,
                            "delivery": "needs_owner_action",
                            "retryable": False,
                            "terminal": True,
                        }
                if reservation is None or reservation.kind != "duplicate_suppressed":
                    # The quota store has no idempotency key. Publish the exact
                    # decision first, then consume once. A crash before the
                    # consumed marker deliberately requires owner action.
                    consumed_quota = enforce_image_analysis_quota(
                        user_id=user_id,
                        user_data=user_data,
                        amount=image_attachment_count,
                        consume=True,
                    )
                    consumed_allowed = int(consumed_quota.allowed_amount or 0)
                    consumed_matches = (
                        quota_disposition == "blocked" and not consumed_quota.allowed and consumed_allowed == 0
                    ) or (
                        quota_disposition in {"allowed", "truncated"}
                        and consumed_quota.allowed
                        and consumed_allowed == quota_allowed_amount
                    )
                    if not consumed_matches:
                        return {
                            "ok": False,
                            "delivery": "needs_owner_action",
                            "retryable": False,
                            "terminal": True,
                        }
                    if reservation is not None and not await confirm_image_quota_consumed(reservation):
                        return {
                            "ok": False,
                            "delivery": "needs_owner_action",
                            "retryable": False,
                            "terminal": True,
                        }
                if quota_disposition == "allowed" and guarded_quota:
                    if not await finalize_allowed_image_quota(
                        event_id=str(inbound_event_id),
                        surface=surface,
                        binding_id=resolved_binding_id,
                        allowed_amount=quota_allowed_amount,
                    ):
                        return {
                            "ok": False,
                            "delivery": "needs_owner_action",
                            "retryable": False,
                            "terminal": True,
                        }

            if quota_disposition in {"blocked", "truncated"}:
                notice_failure = await _deliver_image_quota_notice(
                    message=quota_message,
                    user_id=user_id,
                    sender_id=sender_id,
                    channel=channel,
                    binding_id=resolved_binding_id,
                    inbound_event_id=inbound_event_id,
                    quota_disposition=quota_disposition,
                    quota_allowed_amount=quota_allowed_amount,
                    adapter=adapter,
                    capture_send=capture_send,
                )
                if notice_failure is not None:
                    return notice_failure
                if quota_disposition == "blocked":
                    print(
                        f"[ai_limits] social_image_blocked tenant={resolved_tenant_id} "
                        f"count={image_attachment_count} reason={quota_reason}",
                        flush=True,
                    )
                    return {
                        "ok": True,
                        "delivery": "blocked_quota",
                        "reason": quota_reason,
                        "retryable": False,
                        "terminal": True,
                    }
                if isinstance(attachments, list):
                    kept = _truncate_image_attachments(attachments, quota_allowed_amount)
                    event["attachments"] = kept
                    attachments = kept
        if not text and event.get("attachments"):
            text = "أرسلت صورة أو ملف. اكتبلي شو حابب تعرف عنه كرمال ساعدك."
        if not text:
            return {
                "ok": True,
                "delivery": "no_text",
                "skipped": True,
                "retryable": False,
                "terminal": True,
            }

        async def send_message(
            _namespaced_id: str,
            message_text: str | None = None,
            image_url: str | None = None,
            audio_url: str | None = None,
        ) -> Any:
            from services.meta_social_text_send import send_meta_social_outbound

            return await send_meta_social_outbound(
                namespaced_id=_namespaced_id,
                message_text=message_text,
                image_url=image_url,
                audio_url=audio_url,
                capture_send=capture_send,
                adapter=adapter,
                inbound_event_id=inbound_event_id,
                channel=channel,
                binding_id=resolved_binding_id,
                sender_id=sender_id,
                user_data=user_data,
            )

        from services.ai_reply_delivery import wrap_tracked_send

        send_tracked = wrap_tracked_send(send_message, user_data)

        async def send_action(_namespaced_id: str) -> Any:
            if simulation or adapter is None:
                return {"success": True, "simulated": True}
            return await adapter.send_typing(sender_id)

        skip_firestore_save = bool(simulation)
        message_combine_delay: float | None = None
        if simulation:
            message_combine_delay = 0.0 if combine_delay is None else float(combine_delay)

        await handle_message(
            user_id=user_id,
            user_name=display_name,
            user_input_text=text,
            user_data=user_data,
            send_message_func=send_tracked,
            send_action_func=send_action,
            skip_firestore_save=skip_firestore_save,
            message_combine_delay=message_combine_delay,
        )
        await _await_delayed_processing(user_id)
        from services.ai_reply_turn_runtime import finalize_delivery

        delivery_summary = finalize_delivery({"user_data": user_data})
        return {
            "ok": True,
            "delivery": delivery_summary.get("delivery", "unknown"),
            "logical_reply_id": delivery_summary.get("logical_reply_id"),
            "credit_captured": delivery_summary.get("credit_captured"),
            "retryable": delivery_summary.get("retryable", True),
            "terminal": delivery_summary.get("terminal", False),
            "provider_message_id_present": delivery_summary.get("provider_message_id_present", False),
        }
    finally:
        if adapter is not None:
            await adapter.close()
