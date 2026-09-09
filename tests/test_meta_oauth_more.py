"""Meta Business Login lineage, reconnect, and multi-page tests."""

from __future__ import annotations

import asyncio

import httpx
import pytest

from services.meta_app_registry import (
    APP_A_KEY,
    MetaAppRegistry,
)
from services.meta_oauth import (
    MetaOAuthError,
    complete_meta_business_login,
)
from tests.meta_oauth_support import (
    PAGE_SCOPES,
    _start_state,
    _transport,
)

pytest_plugins = ('tests.meta_oauth_support',)

@pytest.mark.asyncio
async def test_facebook_page_accepts_new_pages_experience_task_names(
    registry: MetaAppRegistry,
) -> None:
    state = _start_state(registry)
    async with httpx.AsyncClient(
        base_url="https://graph.facebook.com/v24.0/",
        transport=_transport(page_tasks=("PROFILE_PLUS_MESSAGING", "PROFILE_PLUS_MODERATE")),
    ) as client:
        result = await complete_meta_business_login(
            code="profile-plus-page-task-code",
            state=state,
            registry=registry,
            client=client,
        )
    assert result.binding.active


@pytest.mark.asyncio
async def test_facebook_page_full_control_label_does_not_infer_specific_tasks(
    registry: MetaAppRegistry,
) -> None:
    state = _start_state(registry)
    async with httpx.AsyncClient(
        base_url="https://graph.facebook.com/v24.0/",
        transport=_transport(page_tasks=("PROFILE_PLUS_FULL_CONTROL",)),
    ) as client:
        with pytest.raises(MetaOAuthError, match="MESSAGING"):
            await complete_meta_business_login(
                code="full-control-label-only-code",
                state=state,
                registry=registry,
                client=client,
            )


@pytest.mark.asyncio
async def test_different_facebook_authorizer_gets_versioned_binding_lineage(
    registry: MetaAppRegistry,
) -> None:
    first_state = _start_state(registry)
    async with httpx.AsyncClient(
        base_url="https://graph.facebook.com/v24.0/",
        transport=_transport(authorized_user_id="112233445566"),
    ) as client:
        first = await complete_meta_business_login(
            code="first-owner-code",
            state=first_state,
            registry=registry,
            client=client,
        )

    second_state = _start_state(registry)
    async with httpx.AsyncClient(
        base_url="https://graph.facebook.com/v24.0/",
        transport=_transport(authorized_user_id="998877665544"),
    ) as client:
        second = await complete_meta_business_login(
            code="second-owner-code",
            state=second_state,
            registry=registry,
            client=client,
        )

    assert first.binding.binding_id != second.binding.binding_id
    assert second.binding.previous_binding_id == first.binding.binding_id
    by_id = {binding.binding_id: binding for binding in registry.list_bindings()}
    assert by_id[first.binding.binding_id].active is False
    assert by_id[first.binding.binding_id].superseded_by_binding_id == second.binding.binding_id
    assert by_id[second.binding.binding_id].active is True
    old_owner = registry.find_authorization_bindings(
        app_key=APP_A_KEY,
        auth_flow="facebook_login",
        authorized_meta_user_id="112233445566",
    )
    new_owner = registry.find_authorization_bindings(
        app_key=APP_A_KEY,
        auth_flow="facebook_login",
        authorized_meta_user_id="998877665544",
    )
    assert [binding.binding_id for binding in old_owner] == [first.binding.binding_id]
    assert [binding.binding_id for binding in new_owner] == [second.binding.binding_id]

    third_state = _start_state(registry)
    async with httpx.AsyncClient(
        base_url="https://graph.facebook.com/v24.0/",
        transport=_transport(authorized_user_id="998877665544"),
    ) as client:
        same_owner = await complete_meta_business_login(
            code="same-second-owner-code",
            state=third_state,
            registry=registry,
            client=client,
        )
    assert same_owner.binding.binding_id != second.binding.binding_id
    assert same_owner.binding.previous_binding_id == second.binding.binding_id


@pytest.mark.asyncio
async def test_disconnected_facebook_authorizer_gets_fresh_binding_id(
    registry: MetaAppRegistry,
) -> None:
    first_state = _start_state(registry)
    async with httpx.AsyncClient(
        base_url="https://graph.facebook.com/v24.0/",
        transport=_transport(authorized_user_id="112233445566"),
    ) as client:
        first = await complete_meta_business_login(
            code="first-authorization-code",
            state=first_state,
            registry=registry,
            client=client,
        )
    registry.revoke_authorization(
        app_key=APP_A_KEY,
        auth_flow="facebook_login",
        authorized_meta_user_id="112233445566",
    )

    reconnect_state = _start_state(registry)
    async with httpx.AsyncClient(
        base_url="https://graph.facebook.com/v24.0/",
        transport=_transport(authorized_user_id="112233445566"),
    ) as client:
        reconnected = await complete_meta_business_login(
            code="fresh-authorization-code",
            state=reconnect_state,
            registry=registry,
            client=client,
        )

    assert reconnected.binding.binding_id != first.binding.binding_id
    assert reconnected.binding.active is True


@pytest.mark.asyncio
async def test_facebook_connect_requires_all_review_scopes_without_replacing_active(
    registry: MetaAppRegistry,
) -> None:
    first_state = _start_state(registry)
    async with httpx.AsyncClient(
        base_url="https://graph.facebook.com/v24.0/",
        transport=_transport(),
    ) as client:
        first = await complete_meta_business_login(
            code="first-authorization-code",
            state=first_state,
            registry=registry,
            client=client,
        )

    missing_scope_state = _start_state(registry)
    without_comments = tuple(
        scope for scope in PAGE_SCOPES if scope not in {"pages_read_user_content", "pages_manage_engagement"}
    )
    async with httpx.AsyncClient(
        base_url="https://graph.facebook.com/v24.0/",
        transport=_transport(page_scopes=without_comments),
    ) as client:
        with pytest.raises(MetaOAuthError, match="required review permissions"):
            await complete_meta_business_login(
                code="missing-comments-code",
                state=missing_scope_state,
                registry=registry,
                client=client,
            )

    active = registry.find_bindings_for_asset_key(
        tenant_id="tenant-a",
        app_key=APP_A_KEY,
        channel="facebook",
        asset_id="445566778899",
    )
    assert [binding.binding_id for binding in active if binding.active] == [first.binding.binding_id]


@pytest.mark.asyncio
async def test_facebook_reconnect_preserves_active_binding_when_subscription_verify_fails(
    registry: MetaAppRegistry,
) -> None:
    first_state = _start_state(registry)
    async with httpx.AsyncClient(
        base_url="https://graph.facebook.com/v24.0/",
        transport=_transport(),
    ) as client:
        first = await complete_meta_business_login(
            code="first-authorization-code",
            state=first_state,
            registry=registry,
            client=client,
        )

    reconnect_state = _start_state(registry)
    async with httpx.AsyncClient(
        base_url="https://graph.facebook.com/v24.0/",
        transport=_transport(verified_subscription_fields=("messages", "messaging_postbacks")),
    ) as client:
        with pytest.raises(MetaOAuthError, match="approved state"):
            await complete_meta_business_login(
                code="unverified-subscription-code",
                state=reconnect_state,
                registry=registry,
                client=client,
            )

    active = registry.find_bindings_for_asset_key(
        tenant_id="tenant-a",
        app_key=APP_A_KEY,
        channel="facebook",
        asset_id="445566778899",
    )
    assert [binding.binding_id for binding in active if binding.active] == [first.binding.binding_id]


@pytest.mark.asyncio
@pytest.mark.parametrize("failure_mode", ["validation", "subscription"])
async def test_multi_page_oauth_failure_never_partially_cuts_over_first_page(
    registry: MetaAppRegistry,
    failure_mode: str,
) -> None:
    initial_state = _start_state(registry)
    async with httpx.AsyncClient(
        base_url="https://graph.facebook.com/v24.0/",
        transport=_transport(),
    ) as client:
        original = await complete_meta_business_login(
            code="initial-page-code",
            state=initial_state,
            registry=registry,
            client=client,
        )

    prior_fields = ("feed", "mention", "messages", "messaging_postbacks")
    external_subscriptions = {"445566778899": prior_fields}
    observed_requests: list[httpx.Request] = []
    failure_transport = _transport(
        second_page_id="556677889900",
        second_page_scopes=(
            tuple(scope for scope in PAGE_SCOPES if scope != "pages_manage_engagement")
            if failure_mode == "validation"
            else None
        ),
        subscription_fail_page_id="556677889900" if failure_mode == "subscription" else "",
        subscription_state=external_subscriptions,
        observed_requests=observed_requests,
    )
    message = "Page token.*pages_manage_engagement" if failure_mode == "validation" else "did not confirm"
    reconnect_state = _start_state(registry)
    async with httpx.AsyncClient(
        base_url="https://graph.facebook.com/v24.0/",
        transport=failure_transport,
    ) as client:
        with pytest.raises(MetaOAuthError, match=message):
            await complete_meta_business_login(
                code="multi-page-failure-code",
                state=reconnect_state,
                registry=registry,
                client=client,
            )

    active = registry.list_bindings(include_inactive=False)
    assert [binding.binding_id for binding in active] == [original.binding.binding_id]
    assert active[0].asset_id == "445566778899"
    assert all(binding.asset_id != "556677889900" for binding in active)
    assert external_subscriptions == {"445566778899": prior_fields}
    if failure_mode == "subscription":
        assert any(
            request.method == "DELETE" and "556677889900/subscribed_apps" in request.url.path
            for request in observed_requests
        )


@pytest.mark.asyncio
async def test_concurrent_failing_callback_cannot_undo_successful_page_subscription(
    registry: MetaAppRegistry,
) -> None:
    """The whole provider transaction is serialized, including compensation."""

    page_id = "445566778899"
    second_page_id = "556677889900"
    prior_fields = ("mention", "messages", "messaging_postbacks")
    desired_fields = ("feed", "messages", "messaging_postbacks", "standby")
    external_subscriptions = {page_id: prior_fields}
    first_reached_failure = asyncio.Event()
    allow_first_to_fail = asyncio.Event()
    operations: list[tuple[str, str, str]] = []
    paused = False

    async def first_hook(request: httpx.Request, request_page_id: str) -> None:
        nonlocal paused
        operations.append(("first", request.method, request_page_id))
        if request.method == "POST" and request_page_id == second_page_id and not paused:
            paused = True
            first_reached_failure.set()
            await allow_first_to_fail.wait()

    async def second_hook(request: httpx.Request, request_page_id: str) -> None:
        operations.append(("second", request.method, request_page_id))

    first_state = _start_state(registry)
    second_state = _start_state(registry)
    async with (
        httpx.AsyncClient(
            base_url="https://graph.facebook.com/v24.0/",
            transport=_transport(
                second_page_id=second_page_id,
                subscription_fail_page_id=second_page_id,
                subscription_state=external_subscriptions,
                subscription_hook=first_hook,
            ),
        ) as first_client,
        httpx.AsyncClient(
            base_url="https://graph.facebook.com/v24.0/",
            transport=_transport(
                subscription_state=external_subscriptions,
                subscription_hook=second_hook,
            ),
        ) as second_client,
    ):
        first_task = asyncio.create_task(
            complete_meta_business_login(
                code="concurrent-failing-code",
                state=first_state,
                registry=registry,
                client=first_client,
            )
        )
        await asyncio.wait_for(first_reached_failure.wait(), timeout=2.0)

        second_task = asyncio.create_task(
            complete_meta_business_login(
                code="concurrent-success-code",
                state=second_state,
                registry=registry,
                client=second_client,
            )
        )
        await asyncio.sleep(0.05)
        assert not any(owner == "second" for owner, _method, _page in operations)

        allow_first_to_fail.set()
        with pytest.raises(MetaOAuthError, match="did not confirm"):
            await asyncio.wait_for(first_task, timeout=2.0)
        successful = await asyncio.wait_for(second_task, timeout=2.0)

    assert successful.binding.active
    assert external_subscriptions == {page_id: desired_fields}
    first_second_operation = next(index for index, item in enumerate(operations) if item[0] == "second")
    assert all(owner == "first" for owner, _method, _page in operations[:first_second_operation])
    assert all(owner == "second" for owner, _method, _page in operations[first_second_operation:])
