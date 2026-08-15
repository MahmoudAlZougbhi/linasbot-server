"""Exact, cancellation-safe compensation for manual Page subscription cutovers."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

import httpx

from services.meta_app_registry import MetaAppRegistry, MetaAssetBinding, get_meta_app_configs
from services.meta_oauth_graph import (
    META_GRAPH_BASE_URL,
    MetaOAuthError,
    PageWebhookSubscriptionSnapshot,
    _await_safety_task,
    _restore_binding_webhook_subscription_locked,
    inspect_binding_webhook_subscription,
)


@dataclass(frozen=True)
class PageSubscriptionMutation:
    """One provider write and the exact state needed to undo only that write."""

    binding: MetaAssetBinding
    before: PageWebhookSubscriptionSnapshot
    expected_after: PageWebhookSubscriptionSnapshot


def page_subscription_identity(binding: MetaAssetBinding) -> tuple[str, str]:
    return binding.app_key, binding.page_id


def reconcile_page_activation_after_exception(
    staged: tuple[MetaAssetBinding, ...],
    *,
    expected_fields: dict[str, tuple[str, ...]],
    registry: MetaAppRegistry,
) -> tuple[MetaAssetBinding, ...] | None:
    """Classify an ambiguous registry activation before provider compensation.

    ``None`` means every target is still the exact source generation and it is
    safe to restore the provider snapshots.  A returned tuple means the local
    commit durably won despite an ACK/connection error, so compensation would
    break an active binding.  Any mixed/unknown state is retained for explicit
    owner reconciliation.
    """

    if not staged:
        return None
    try:
        latest = {
            item.binding_id: item for item in registry.list_bindings(include_inactive=True, include_superseded=True)
        }
    except Exception as exc:
        raise MetaOAuthError("Meta activation outcome is unknown; provider state was retained") from exc
    rows = [latest.get(item.binding_id) for item in staged]
    if any(item is None for item in rows):
        raise MetaOAuthError("Meta activation outcome is mixed; provider state was retained")
    resolved = tuple(item for item in rows if item is not None)
    source = all(
        current.generation == original.generation and current.status in {"testing", "inactive"}
        for original, current in zip(staged, resolved, strict=True)
    )
    committed = all(
        current.active
        and current.generation == original.generation + 1
        and current.webhook_subscription_status == "ready"
        and current.webhook_subscription_checked_at > 0
        and tuple(sorted(current.webhook_subscribed_fields))
        == tuple(sorted(expected_fields.get(original.binding_id, ())))
        and original.binding_id in expected_fields
        for original, current in zip(staged, resolved, strict=True)
    )
    if committed:
        return resolved
    if source:
        return None
    raise MetaOAuthError("Meta activation outcome is mixed; provider state was retained")


def reconcile_page_rollback_after_exception(
    current: MetaAssetBinding,
    previous: MetaAssetBinding,
    *,
    expected_previous_fields: tuple[str, ...],
    registry: MetaAppRegistry,
) -> MetaAssetBinding | None:
    """Classify an ambiguous rollback commit without undoing a committed cutover."""

    try:
        latest = {
            item.binding_id: item for item in registry.list_bindings(include_inactive=True, include_superseded=True)
        }
    except Exception as exc:
        raise MetaOAuthError("Meta rollback outcome is unknown; provider state was retained") from exc
    latest_current = latest.get(current.binding_id)
    latest_previous = latest.get(previous.binding_id)
    if latest_current is None or latest_previous is None:
        raise MetaOAuthError("Meta rollback outcome is mixed; provider state was retained")
    source = (
        latest_current.active
        and latest_current.generation == current.generation
        and not latest_previous.active
        and latest_previous.generation == previous.generation
    )
    committed = (
        not latest_current.active
        and latest_current.generation == current.generation + 1
        and latest_current.superseded_by_binding_id == previous.binding_id
        and latest_previous.active
        and latest_previous.generation == previous.generation + 1
        and latest_previous.webhook_subscription_status == "ready"
        and latest_previous.webhook_subscription_checked_at > 0
        and tuple(sorted(latest_previous.webhook_subscribed_fields)) == tuple(sorted(expected_previous_fields))
    )
    if committed:
        return latest_previous
    if source:
        return None
    raise MetaOAuthError("Meta rollback outcome is mixed; provider state was retained")


async def capture_page_subscription_snapshots(
    bindings: tuple[MetaAssetBinding, ...],
    *,
    registry: MetaAppRegistry,
) -> dict[tuple[str, str], PageWebhookSubscriptionSnapshot]:
    """Read every distinct app/Page state before the first provider mutation."""

    snapshots: dict[tuple[str, str], PageWebhookSubscriptionSnapshot] = {}
    for binding in bindings:
        identity = page_subscription_identity(binding)
        if identity not in snapshots:
            snapshots[identity] = await inspect_binding_webhook_subscription(
                binding,
                registry=registry,
                client=None,
            )
    return snapshots


async def _compensate_page_subscription_mutations(
    mutations: list[PageSubscriptionMutation],
    *,
    registry: MetaAppRegistry,
) -> bool:
    failed = False
    for mutation in reversed(mutations):
        try:
            app = get_meta_app_configs()[mutation.binding.app_key]
            async with httpx.AsyncClient(
                base_url=f"{META_GRAPH_BASE_URL}/{app.graph_api_version}",
                timeout=20.0,
            ) as client:
                await _restore_binding_webhook_subscription_locked(
                    mutation.binding,
                    mutation.before,
                    expected_current=mutation.expected_after,
                    registry=registry,
                    client=client,
                )
        except Exception:
            failed = True
    return failed


async def compensate_page_subscription_failure(
    original: BaseException,
    mutations: list[PageSubscriptionMutation],
    *,
    registry: MetaAppRegistry,
) -> None:
    """Finish compensation under cancellation, then let the original failure win."""

    if not mutations:
        return
    cleanup_task = asyncio.create_task(_compensate_page_subscription_mutations(mutations, registry=registry))
    compensation_failed, cancelled, cleanup_error = await _await_safety_task(cleanup_task)
    if isinstance(original, asyncio.CancelledError):
        return
    if cancelled:
        raise asyncio.CancelledError from original
    if cleanup_error is not None or compensation_failed:
        raise MetaOAuthError(
            "Meta provider cutover failed and the prior Page subscriptions could not be verified"
        ) from (cleanup_error or original)
