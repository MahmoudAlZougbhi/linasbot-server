"""Shared fixtures and helpers for Meta Business Login OAuth tests."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

import httpx
import pytest

from services.meta_app_registry import (
    MetaAppRegistry,
)
from services.meta_oauth import (
    begin_meta_business_login,
)
from tests.meta_compliance_helpers import _FakeFirestore

PAGE_SCOPES = [
    "pages_manage_engagement",
    "pages_show_list",
    "pages_manage_metadata",
    "pages_read_engagement",
    "pages_read_user_content",
    "pages_messaging",
]
INTEGRATION_SCOPES = ["business_management", *PAGE_SCOPES]
SCOPES = INTEGRATION_SCOPES


@pytest.fixture
def oauth_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("META_APP_A_ID", "2963733803971681")
    monkeypatch.setenv("META_APP_A_SECRET", "app-a-secret-tests")
    monkeypatch.setenv("META_APP_A_WEBHOOK_VERIFY_TOKEN", "verify-a-tests-thirty-two-characters-long")
    monkeypatch.setenv("META_WEBHOOK_VERIFY_TOKEN", "verify-a-tests-thirty-two-characters-long")
    monkeypatch.setenv("META_APP_B_ID", "998877665544")
    monkeypatch.setenv("META_APP_B_SECRET", "app-b-secret-tests")
    monkeypatch.setenv("META_APP_B_WEBHOOK_VERIFY_TOKEN", "verify-b-tests")
    monkeypatch.setenv("META_APP_A_FACEBOOK_LOGIN_CONFIG_ID", "facebook-only-config-tests")
    monkeypatch.setenv("META_GRAPH_API_VERSION", "v24.0")
    monkeypatch.setenv("META_OAUTH_REDIRECT_URI", "https://www.linasaibot.com/oauth/meta/callback")


@pytest.fixture
def registry(tmp_path: Path, oauth_env: None, monkeypatch: pytest.MonkeyPatch) -> MetaAppRegistry:
    import utils.utils

    db = _FakeFirestore()
    monkeypatch.setattr(utils.utils, "get_firestore_db", lambda: db)

    async def _enable_channel_defaults(**_kwargs: Any) -> None:
        return None

    monkeypatch.setattr(
        "services.channel_capability_toggles.enable_channel_defaults_after_connect",
        _enable_channel_defaults,
    )
    return MetaAppRegistry(
        store_path=tmp_path / "registry.json",
        audit_path=tmp_path / "audit.jsonl",
        master_secret="oauth-registry-master-secret-tests-1234567890",
    )


def _start_state(registry: MetaAppRegistry, *, channel: str = "facebook") -> str:
    url = begin_meta_business_login(
        tenant_id="tenant-a",
        channel=channel,  # type: ignore[arg-type]
        actor_id="owner-a",
        registry=registry,
    )
    query = parse_qs(urlparse(url).query)
    return query["state"][0]


def _transport(
    *,
    page_id: str = "445566778899",
    instagram_id: str = "17840000123456789",
    wrong_app: bool = False,
    extra_target: bool = False,
    page_type: str = "PAGE",
    page_extra_scopes: tuple[str, ...] = (),
    page_scopes: tuple[str, ...] | None = None,
    integration_scopes: tuple[str, ...] | None = None,
    page_tasks: tuple[str, ...] = ("MESSAGING", "MODERATE"),
    omit_granular_scopes: bool = False,
    granular_scope_targets: dict[str, tuple[str, ...]] | None = None,
    authorized_user_id: str = "112233445566",
    subscription_post_success: bool = True,
    subscription_fail_page_id: str = "",
    verified_subscription_fields: tuple[str, ...] | None = None,
    second_page_id: str = "",
    second_page_scopes: tuple[str, ...] | None = None,
    second_page_tasks: tuple[str, ...] | None = None,
    include_page: bool = True,
    page_access_token: str = "page-token-private",
    subscription_state: dict[str, tuple[str, ...]] | None = None,
    observed_requests: list[httpx.Request] | None = None,
    subscription_hook: Callable[[httpx.Request, str], Awaitable[None]] | None = None,
) -> httpx.MockTransport:
    subscribed_fields = subscription_state if subscription_state is not None else {}
    posted_pages: set[str] = set()
    verification_override_pending: set[str] = set()

    async def handler(request: httpx.Request) -> httpx.Response:
        if observed_requests is not None:
            observed_requests.append(request)
        path = request.url.path
        if path.endswith("/oauth/access_token"):
            return httpx.Response(200, json={"access_token": "integration-token-private"})
        if path.endswith("/debug_token"):
            inspected = request.url.params.get("input_token")
            data: dict[str, Any] = {
                "is_valid": True,
                "app_id": "000000000000" if wrong_app else "2963733803971681",
                "scopes": list(integration_scopes if integration_scopes is not None else INTEGRATION_SCOPES),
                "expires_at": 4102444800,
                "user_id": authorized_user_id,
            }
            inspected_page_id = ""
            inspected_scopes: list[str] = []
            if inspected == "page-token-private":
                inspected_page_id = page_id
                inspected_scopes = list(page_scopes if page_scopes is not None else PAGE_SCOPES)
            elif second_page_id and inspected == "page-token-private-2":
                inspected_page_id = second_page_id
                inspected_scopes = list(second_page_scopes if second_page_scopes is not None else PAGE_SCOPES)
            if inspected_page_id:
                inspected_scopes.extend(page_extra_scopes)
                data["scopes"] = inspected_scopes
                data["profile_id"] = inspected_page_id
                data["type"] = page_type
                if not omit_granular_scopes:
                    default_targets = [inspected_page_id, "000111222"] if extra_target else [inspected_page_id]
                    data["granular_scopes"] = [
                        {
                            "scope": scope,
                            "target_ids": list((granular_scope_targets or {}).get(scope, tuple(default_targets))),
                        }
                        for scope in PAGE_SCOPES
                    ]
            return httpx.Response(200, json={"data": data})
        if path.endswith("/me/accounts"):
            pages = []
            if include_page:
                pages.append(
                    {
                        "id": page_id,
                        "name": "Authorized Clinic",
                        "access_token": page_access_token,
                        "tasks": list(page_tasks),
                        "instagram_business_account": {
                            "id": instagram_id,
                            "username": "authorized_clinic",
                        },
                    }
                )
            if second_page_id:
                pages.append(
                    {
                        "id": second_page_id,
                        "name": "Second Authorized Clinic",
                        "access_token": "page-token-private-2",
                        "tasks": list(second_page_tasks if second_page_tasks is not None else page_tasks),
                        "instagram_business_account": {
                            "id": "17840000999999999",
                            "username": "second_authorized_clinic",
                        },
                    }
                )
            return httpx.Response(
                200,
                json={"data": pages},
            )
        if path.endswith("/subscribed_apps") and request.method == "POST":
            body = (await request.aread()).decode("utf-8")
            request_page_id = path.rstrip("/").split("/")[-2]
            subscribed_fields[request_page_id] = tuple(
                sorted((parse_qs(body).get("subscribed_fields") or [""])[0].split(","))
            )
            if verified_subscription_fields is not None and request_page_id not in posted_pages:
                verification_override_pending.add(request_page_id)
            posted_pages.add(request_page_id)
            success = subscription_post_success and request_page_id != subscription_fail_page_id
            if subscription_hook is not None:
                await subscription_hook(request, request_page_id)
            return httpx.Response(200, json={"success": success})
        if path.endswith("/subscribed_apps") and request.method == "GET":
            request_page_id = path.rstrip("/").split("/")[-2]
            fields = subscribed_fields.get(request_page_id)
            if verified_subscription_fields is not None and request_page_id in verification_override_pending:
                fields = verified_subscription_fields
                verification_override_pending.remove(request_page_id)
            rows = [{"id": "2963733803971681", "subscribed_fields": list(fields)}] if fields is not None else []
            if subscription_hook is not None:
                await subscription_hook(request, request_page_id)
            return httpx.Response(200, json={"data": rows})
        if path.endswith("/subscribed_apps") and request.method == "DELETE":
            request_page_id = path.rstrip("/").split("/")[-2]
            subscribed_fields.pop(request_page_id, None)
            if subscription_hook is not None:
                await subscription_hook(request, request_page_id)
            return httpx.Response(200, json={"success": True})
        if path.endswith("/subscriptions") and request.method == "POST":
            return httpx.Response(200, json={"success": True})
        return httpx.Response(404, json={"error": {"message": "not found"}})

    return httpx.MockTransport(handler)
