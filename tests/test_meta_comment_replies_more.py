"""Continuation of Meta public comment reply tests."""

from __future__ import annotations

import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

import httpx

from services.meta_app_registry import (
    APP_A_KEY,
    APP_B_KEY,
    MetaAssetBinding,
    MetaBindingCredential,
)
from services.meta_comment_events import (
    ResolvedMetaCommentEvent,
    parse_meta_comment_events,
    resolve_registry_comment_events,
)
from services.meta_comment_replies import (
    CommentReplyResult,
    MetaCommentReplyInspectionError,
    _comment_has_page_reply,
    _graph_post_form,
    comment_reply_requires_retry,
    process_meta_comment_event,
)
from services.meta_comment_reply_settings import (
    set_comment_reply_setting,
)
from tests.test_meta_comment_replies import (
    _binding,
    _facebook_comment_payload,
    _instagram_comment_payload,
    _settings,
)


class MetaCommentProcessorTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.settings_root = Path(self.tmp.name)
        self._settings_patch = mock.patch(
            "services.meta_comment_reply_settings._SETTINGS_ROOT",
            self.settings_root,
        )
        self._settings_patch.start()
        import services.meta_comment_replies as replies_module

        replies_module._SENT_REPLY_IDS.clear()
        replies_module._RATE_BUCKETS.clear()
        self._registry_patch = mock.patch("services.meta_app_registry.get_meta_app_registry")
        self.mock_registry = self._registry_patch.start()
        registry = mock.MagicMock()
        registry.get_credential.return_value = MetaBindingCredential(
            access_token="page-token",
            token_app_id="2963733803971681",
            token_profile_id="111",
            scopes=(
                "pages_messaging",
                "pages_read_user_content",
                "pages_manage_engagement",
                "instagram_manage_comments",
            ),
            expires_at=int(time.time()) + 3600,
            authorized_meta_user_id="meta-user",
            auth_flow="facebook_login",
        )
        self.mock_registry.return_value = registry

        def _enforcement(**kwargs):
            if not kwargs.get("per_asset_enabled"):
                return {"allow": False, "reason": "feature_disabled", "readiness": {}}
            return {"allow": True, "reason": "", "readiness": {}}

        self._enforcement_patch = mock.patch(
            "services.cm.actions.comments_enforcement_decision",
            side_effect=_enforcement,
        )
        self._enforcement_patch.start()

    def tearDown(self):
        self._enforcement_patch.stop()
        self._registry_patch.stop()
        self._settings_patch.stop()
        self.tmp.cleanup()

    def _verified_binding(self, **kwargs: object) -> MetaAssetBinding:
        from services.meta_comment_permission_verification import comment_permission_token_fingerprint

        binding = _binding(**kwargs)
        token = "page-token"
        return MetaAssetBinding(
            **{
                **binding.__dict__,
                "comment_permission_status": "verified_granted",
                "comment_permission_verified_at": time.time(),
                "comment_permission_source": "oauth_stored_scopes",
                "comment_permission_credential_id": binding.credential_id,
                "comment_permission_token_fingerprint": comment_permission_token_fingerprint(token),
            }
        )

    async def test_toggle_off_skips_openai_and_reply(self):
        binding = _binding()
        event = parse_meta_comment_events(_facebook_comment_payload(), channel="facebook", page_id="111")[0]
        resolved = ResolvedMetaCommentEvent(event=event, settings=_settings(binding), binding=binding)
        result = await process_meta_comment_event(resolved, simulation=True)
        self.assertEqual(result.status, "ignored")
        self.assertEqual(result.reason, "feature_disabled")

    @mock.patch("services.meta_comment_replies._generate_comment_reply_text", new_callable=mock.AsyncMock)
    @mock.patch(
        "services.meta_comment_replies._comment_has_page_reply", new_callable=mock.AsyncMock, return_value=False
    )
    async def test_toggle_on_sends_one_public_reply(self, _manual_mock, generate_mock):
        generate_mock.return_value = "Thanks for your question."
        binding = self._verified_binding()
        set_comment_reply_setting(
            tenant_id=binding.tenant_id,
            app_key=binding.app_key,
            channel=binding.channel,
            asset_id=binding.asset_id,
            enabled=True,
        )
        event = parse_meta_comment_events(_facebook_comment_payload(), channel="facebook", page_id="111")[0]
        resolved = ResolvedMetaCommentEvent(event=event, settings=_settings(binding), binding=binding)
        sent: list[dict] = []
        result = await process_meta_comment_event(resolved, simulation=True, capture_send=sent)
        self.assertEqual(result.status, "simulated")
        self.assertEqual(len(sent), 1)
        self.assertEqual(sent[0]["message"], "Thanks for your question.")
        generate_mock.assert_awaited_once()

    @mock.patch("services.meta_comment_replies._generate_comment_reply_text", new_callable=mock.AsyncMock)
    async def test_toggle_off_does_not_call_openai(self, generate_mock):
        binding = _binding(channel="instagram", asset_id="222")
        event = parse_meta_comment_events(
            _instagram_comment_payload(),
            channel="instagram",
            instagram_account_id="222",
        )[0]
        resolved = ResolvedMetaCommentEvent(event=event, settings=_settings(binding), binding=binding)
        result = await process_meta_comment_event(resolved, simulation=True)
        self.assertEqual(result.reason, "feature_disabled")
        generate_mock.assert_not_called()

    async def test_app_b_binding_rejected(self):
        binding = _binding(app_key=APP_B_KEY)
        event = parse_meta_comment_events(_facebook_comment_payload(), channel="facebook", page_id="111")[0]
        resolved = ResolvedMetaCommentEvent(event=event, settings=_settings(binding), binding=binding)
        result = await process_meta_comment_event(resolved, simulation=True)
        self.assertEqual(result.reason, "app_b_not_supported")

    async def test_archived_binding_ignored(self):
        binding = _binding(status="disconnected")
        event = parse_meta_comment_events(_facebook_comment_payload(), channel="facebook", page_id="111")[0]
        resolved = ResolvedMetaCommentEvent(event=event, settings=_settings(binding), binding=binding)
        result = await process_meta_comment_event(resolved, simulation=True)
        self.assertEqual(result.reason, "binding_not_active")

    @mock.patch(
        "services.meta_comment_replies._generate_comment_reply_text", new_callable=mock.AsyncMock, return_value="Hi"
    )
    @mock.patch(
        "services.meta_comment_replies._comment_has_page_reply", new_callable=mock.AsyncMock, return_value=False
    )
    async def test_duplicate_comment_not_replied_twice(self, _manual_mock, _generate_mock):
        binding = self._verified_binding()
        set_comment_reply_setting(
            tenant_id=binding.tenant_id,
            app_key=binding.app_key,
            channel=binding.channel,
            asset_id=binding.asset_id,
            enabled=True,
        )
        event = parse_meta_comment_events(_facebook_comment_payload(), channel="facebook", page_id="111")[0]
        resolved = ResolvedMetaCommentEvent(event=event, settings=_settings(binding), binding=binding)
        first = await process_meta_comment_event(resolved, simulation=True)
        second = await process_meta_comment_event(resolved, simulation=True)
        self.assertEqual(first.status, "simulated")
        self.assertEqual(second.reason, "already_replied")

    async def test_transient_reply_list_failure_never_generates_or_posts_duplicate(self):
        binding = self._verified_binding()
        set_comment_reply_setting(
            tenant_id=binding.tenant_id,
            app_key=binding.app_key,
            channel=binding.channel,
            asset_id=binding.asset_id,
            enabled=True,
        )
        event = parse_meta_comment_events(_facebook_comment_payload(), channel="facebook", page_id="111")[0]
        resolved = ResolvedMetaCommentEvent(event=event, settings=_settings(binding), binding=binding)

        async def _no_graph(event, **_kwargs):
            return dict(event)

        with (
            mock.patch(
                "services.meta_comment_post_context.enrich_comment_event_post",
                new_callable=mock.AsyncMock,
                side_effect=_no_graph,
            ),
            mock.patch(
                "services.meta_comment_replies._comment_has_page_reply",
                new_callable=mock.AsyncMock,
                side_effect=MetaCommentReplyInspectionError("http_503"),
            ),
            mock.patch(
                "services.meta_comment_replies._generate_comment_reply_text",
                new_callable=mock.AsyncMock,
            ) as generate_mock,
        ):
            result = await process_meta_comment_event(resolved)

        self.assertEqual(result, CommentReplyResult(status="failed", reason="reply_dedupe_check_failed"))
        self.assertTrue(comment_reply_requires_retry(result))
        generate_mock.assert_not_awaited()


class MetaCommentRegistryRoutingTests(unittest.TestCase):
    def test_wrong_workspace_asset_not_resolved(self):
        payload = _facebook_comment_payload(page_id="111")
        binding = _binding(tenant_id="linas", asset_id="111", page_id="111")
        registry = mock.MagicMock()
        registry.get_active_bindings_for_app.return_value = [binding]
        registry.get_credential.return_value = MetaBindingCredential(
            access_token="token",
            token_app_id="2963733803971681",
            token_profile_id="111",
            scopes=("pages_messaging", "pages_read_user_content", "pages_manage_engagement"),
        )
        app_config = mock.MagicMock()
        app_config.key = APP_A_KEY
        app_config.app_id = "2963733803971681"
        app_config.app_secret = "secret"
        app_config.verify_token = "verify"
        app_config.graph_api_version = "v24.0"
        resolved = resolve_registry_comment_events(payload, app_config=app_config, registry=registry)
        self.assertEqual(len(resolved), 1)
        wrong_payload = _facebook_comment_payload(page_id="999")
        resolved_wrong = resolve_registry_comment_events(wrong_payload, app_config=app_config, registry=registry)
        self.assertEqual(resolved_wrong, [])


class MetaCommentResultPolicyTests(unittest.IsolatedAsyncioTestCase):
    def test_only_retryable_outcomes_remain_non_terminal(self):
        self.assertTrue(comment_reply_requires_retry(CommentReplyResult(status="failed", reason="http_500")))
        self.assertTrue(comment_reply_requires_retry(CommentReplyResult(status="ignored", reason="rate_limited")))
        self.assertFalse(comment_reply_requires_retry(CommentReplyResult(status="sent", reply_id="reply-1")))
        self.assertFalse(
            comment_reply_requires_retry(CommentReplyResult(status="skipped", reason="no_confident_reply"))
        )

    async def test_graph_2xx_without_reply_id_is_not_success(self):
        async def handler(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"success": True})

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            ok, reason, _payload = await _graph_post_form(
                client,
                "https://graph.facebook.com/v24.0/comment-1/comments",
                token="token",
                data={"message": "hello"},
            )

        self.assertFalse(ok)
        self.assertEqual(reason, "missing_reply_id")

    async def test_reply_dedupe_get_failure_is_fail_closed(self):
        async def handler(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(503, json={"error": {"message": "temporary"}})

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            with self.assertRaisesRegex(MetaCommentReplyInspectionError, "http_503"):
                await _comment_has_page_reply(
                    client,
                    comment_id="comment-1",
                    owner_id="page-1",
                    token="token",
                    graph_url="https://graph.facebook.com/v24.0/comment-1/comments",
                )

    async def test_reply_dedupe_traverses_pagination_before_retrying_send(self):
        requests: list[httpx.Request] = []

        async def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            if request.url.params.get("after") == "cursor-1":
                return httpx.Response(
                    200,
                    json={
                        "data": [{"id": "reply-11", "from": {"id": "page-1"}}],
                        "paging": {"cursors": {"after": "cursor-2"}},
                    },
                )
            return httpx.Response(
                200,
                json={
                    "data": [{"id": f"reply-{index}", "from": {"id": f"customer-{index}"}} for index in range(10)],
                    "paging": {
                        "cursors": {"after": "cursor-1"},
                        "next": "https://graph.facebook.com/v24.0/comment-1/comments?after=cursor-1",
                    },
                },
            )

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            found = await _comment_has_page_reply(
                client,
                comment_id="comment-1",
                owner_id="page-1",
                token="token",
                graph_url="https://graph.facebook.com/v24.0/comment-1/comments",
            )

        self.assertTrue(found)
        self.assertEqual(len(requests), 2)
        self.assertEqual(requests[0].url.params.get("fields"), "id,from")
        self.assertEqual(requests[1].url.params.get("after"), "cursor-1")
        self.assertEqual(requests[1].url.params.get("fields"), "id,from")

    async def test_reply_dedupe_graph_400_is_treated_as_unreplied(self):
        async def handler(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(400, json={"error": {"message": "unsupported get request"}})

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            found = await _comment_has_page_reply(
                client,
                comment_id="comment-1",
                owner_id="page-1",
                token="token",
                graph_url="https://graph.facebook.com/v24.0/comment-1/comments",
            )

        self.assertFalse(found)

    async def test_reply_dedupe_falls_back_when_from_field_is_rejected(self):
        fields: list[str] = []

        async def handler(request: httpx.Request) -> httpx.Response:
            fields.append(str(request.url.params.get("fields") or ""))
            if request.url.params.get("fields") == "id,from":
                return httpx.Response(400, json={"error": {"code": 100}})
            return httpx.Response(200, json={"data": [{"id": "reply-1"}]})

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            found = await _comment_has_page_reply(
                client,
                comment_id="comment-1",
                owner_id="page-1",
                token="token",
                graph_url="https://graph.facebook.com/v24.0/comment-1/comments",
            )

        self.assertFalse(found)
        self.assertEqual(fields, ["id,from", "id"])

    async def test_reply_dedupe_skips_rows_missing_from_instead_of_fail_closing(self):
        async def handler(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={
                    "data": [
                        {"id": "reply-hidden"},
                        {"id": "reply-page", "from": {"id": "page-1"}},
                    ]
                },
            )

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            found = await _comment_has_page_reply(
                client,
                comment_id="comment-1",
                owner_id="page-1",
                token="token",
                graph_url="https://graph.facebook.com/v24.0/comment-1/comments",
            )

        self.assertTrue(found)

    async def test_reply_dedupe_graph_403_is_treated_as_unreplied(self):
        async def handler(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(403, json={"error": {"message": "permission"}})

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            found = await _comment_has_page_reply(
                client,
                comment_id="comment-1",
                owner_id="page-1",
                token="token",
                graph_url="https://graph.facebook.com/v24.0/comment-1/comments",
            )

        self.assertFalse(found)


if __name__ == "__main__":
    unittest.main()
