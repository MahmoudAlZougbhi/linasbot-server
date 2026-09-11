"""Tests for optional Meta public comment AI replies (App A only)."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from services.meta_app_registry import (
    APP_A_KEY,
    MetaAssetBinding,
)
from services.meta_comment_events import (
    count_raw_comment_changes,
    parse_meta_comment_events,
)
from services.meta_comment_replies import (
    _is_self_comment,
)
from services.meta_comment_reply_settings import (
    get_comment_reply_setting,
    set_comment_reply_setting,
)
from services.meta_messaging import MetaMessagingSettings, parse_meta_messaging_events


def _facebook_comment_payload(*, page_id: str = "111", comment_id: str = "c1", author_id: str = "user-9") -> dict:
    return {
        "object": "page",
        "entry": [
            {
                "id": page_id,
                "time": 1700000000,
                "changes": [
                    {
                        "field": "feed",
                        "value": {
                            "item": "comment",
                            "verb": "add",
                            "comment_id": comment_id,
                            "post_id": "post-1",
                            "from": {"id": author_id, "name": "Customer"},
                            "message": "How much is laser?",
                        },
                    }
                ],
            }
        ],
    }


def _instagram_comment_payload(
    *,
    ig_id: str = "222",
    comment_id: str = "igc1",
    author_id: str = "user-8",
) -> dict:
    return {
        "object": "instagram",
        "entry": [
            {
                "id": ig_id,
                "time": 1700000000,
                "changes": [
                    {
                        "field": "comments",
                        "value": {
                            "id": comment_id,
                            "text": "What are your hours?",
                            "from": {"id": author_id, "username": "customer"},
                            "media": {"id": "media-1"},
                        },
                    }
                ],
            }
        ],
    }


def _official_instagram_login_comment_payload(*, username: str = "commenter") -> dict:
    return {
        "object": "instagram",
        "entry": [
            {
                "time": 1741982997,
                "id": "222",
                "field": "comments",
                "value": {
                    "from": {"username": username},
                    "media": {
                        "id": "media-official-1",
                        "media_product_type": "FEED",
                    },
                    "id": "comment-official-1",
                    "text": "This is an official-shape comment",
                },
            }
        ],
    }


def _binding(
    *,
    tenant_id: str = "linas",
    channel: str = "facebook",
    asset_id: str = "111",
    page_id: str = "111",
    instagram_id: str = "222",
    instagram_username: str = "",
    status: str = "active",
    app_key: str = APP_A_KEY,
) -> MetaAssetBinding:
    return MetaAssetBinding(
        binding_id="bind-1",
        tenant_id=tenant_id,
        channel=channel,  # type: ignore[arg-type]
        asset_id=asset_id,
        page_id=page_id,
        instagram_account_id=instagram_id,
        instagram_username=instagram_username,
        app_key=app_key,
        credential_id="cred-1",
        status=status,  # type: ignore[arg-type]
        generation=1,
        created_at=1.0,
        updated_at=1.0,
    )


def _settings(binding: MetaAssetBinding) -> MetaMessagingSettings:
    return MetaMessagingSettings(
        enabled=True,
        app_secret="secret",
        page_id=binding.page_id,
        page_access_token="page-token",
        instagram_account_id=binding.instagram_account_id,
        verify_token="verify",
        graph_api_version="v24.0",
        app_id="2963733803971681",
        app_key=binding.app_key,
        tenant_id=binding.tenant_id,
        binding_id=binding.binding_id,
    )


class MetaCommentEventParserTests(unittest.TestCase):
    def test_facebook_comment_parsed(self):
        events = parse_meta_comment_events(_facebook_comment_payload(), channel="facebook", page_id="111")
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["comment_id"], "c1")
        self.assertEqual(events[0]["channel"], "facebook")

    def test_instagram_comment_parsed(self):
        events = parse_meta_comment_events(
            _instagram_comment_payload(), channel="instagram", instagram_account_id="222"
        )
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["comment_id"], "igc1")

    def test_official_instagram_login_comment_shape_parsed_without_from_id(self):
        payload = _official_instagram_login_comment_payload()

        first = parse_meta_comment_events(payload, channel="instagram", instagram_account_id="222")
        second = parse_meta_comment_events(payload, channel="instagram", instagram_account_id="222")

        self.assertEqual(len(first), 1)
        self.assertEqual(first[0]["comment_id"], "comment-official-1")
        self.assertEqual(first[0]["media_id"], "media-official-1")
        self.assertEqual(first[0]["author_username"], "commenter")
        self.assertTrue(first[0]["author_id"])
        self.assertEqual(first[0]["author_id"], second[0]["author_id"])

    def test_count_raw_comment_changes(self):
        self.assertEqual(count_raw_comment_changes(_facebook_comment_payload()), 1)
        self.assertEqual(count_raw_comment_changes(_instagram_comment_payload()), 1)
        self.assertEqual(count_raw_comment_changes(_official_instagram_login_comment_payload()), 1)
        self.assertEqual(
            count_raw_comment_changes({"object": "instagram", "entry": [{"id": "222", "messaging": []}]}),
            0,
        )

    def test_self_page_comment_ignored_in_processor(self):
        binding = _binding(channel="facebook", asset_id="111", page_id="111")
        self.assertTrue(_is_self_comment({"author_id": "111"}, binding))

    def test_official_instagram_shape_self_comment_ignored_by_username(self):
        binding = _binding(
            channel="instagram",
            asset_id="222",
            instagram_id="222",
            instagram_username="LinasAI",
        )
        events = parse_meta_comment_events(
            _official_instagram_login_comment_payload(username="linasai"),
            channel="instagram",
            instagram_account_id="222",
        )

        self.assertEqual(len(events), 1)
        self.assertTrue(_is_self_comment(events[0], binding))

    def test_dm_parser_unchanged_without_changes(self):
        dm_payload = {
            "object": "page",
            "entry": [
                {
                    "id": "111",
                    "messaging": [
                        {
                            "sender": {"id": "user-1"},
                            "recipient": {"id": "111"},
                            "message": {"mid": "m1", "text": "hello"},
                        }
                    ],
                }
            ],
        }
        events = parse_meta_messaging_events(dm_payload, page_id="111", instagram_account_id="222")
        self.assertEqual(len(events), 1)
        comment_events = parse_meta_comment_events(dm_payload, channel="facebook", page_id="111")
        self.assertEqual(comment_events, [])


class MetaCommentSettingsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.settings_root = Path(self.tmp.name)
        self._settings_patch = mock.patch(
            "services.meta_comment_reply_settings._SETTINGS_ROOT",
            self.settings_root,
        )
        self._settings_patch.start()

    def tearDown(self):
        self._settings_patch.stop()
        self.tmp.cleanup()

    def test_defaults_off_per_asset(self):
        first = get_comment_reply_setting(
            tenant_id="tenant-a",
            app_key=APP_A_KEY,
            channel="facebook",
            asset_id="111",
        )
        second = get_comment_reply_setting(
            tenant_id="tenant-a",
            app_key=APP_A_KEY,
            channel="facebook",
            asset_id="999",
        )
        self.assertFalse(first.enabled)
        self.assertFalse(second.enabled)
        set_comment_reply_setting(
            tenant_id="tenant-a",
            app_key=APP_A_KEY,
            channel="facebook",
            asset_id="111",
            enabled=True,
            instructions="Be brief",
        )
        updated_first = get_comment_reply_setting(
            tenant_id="tenant-a",
            app_key=APP_A_KEY,
            channel="facebook",
            asset_id="111",
        )
        unchanged_second = get_comment_reply_setting(
            tenant_id="tenant-a",
            app_key=APP_A_KEY,
            channel="facebook",
            asset_id="999",
        )
        self.assertTrue(updated_first.enabled)
        self.assertEqual(updated_first.instructions, "Be brief")
        self.assertFalse(unchanged_second.enabled)
