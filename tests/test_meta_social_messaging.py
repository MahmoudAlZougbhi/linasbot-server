"""Regression tests for Meta Instagram/Facebook social messaging webhooks."""

import unittest
from unittest import mock

from services.meta_messaging import (
    InMemoryMessageDeduper,
    MetaMessagingSettings,
    get_meta_messaging_readiness,
    parse_meta_messaging_events,
    verify_meta_signature,
)
from tests.meta_social_messaging_helpers import _sign


class MetaSignatureTests(unittest.TestCase):
    def test_valid_signature_accepted(self):
        body = b'{"object":"page","entry":[]}'
        secret = "test_app_secret"
        self.assertTrue(verify_meta_signature(body, _sign(secret, body), secret))

    def test_invalid_signature_rejected(self):
        body = b'{"object":"page","entry":[]}'
        self.assertFalse(verify_meta_signature(body, "sha256=deadbeef", "test_app_secret"))

    def test_missing_signature_rejected(self):
        self.assertFalse(verify_meta_signature(b"{}", None, "secret"))

    def test_missing_secret_rejected(self):
        body = b"{}"
        self.assertFalse(verify_meta_signature(body, _sign("secret", body), ""))


class MetaReadinessTests(unittest.TestCase):
    def test_enabled_readiness_requires_new_app_and_exact_allowlist(self):
        settings = MetaMessagingSettings(
            enabled=True,
            app_secret="secret",
            page_id="378696005334409",
            page_access_token="page-token",
            instagram_account_id="17841413184256533",
            verify_token="verify-token",
            graph_api_version="v24.0",
        )
        with mock.patch.dict(
            "os.environ",
            {
                "META_APP_ID": "999000111",
                "META_SOCIAL_ROLLBACK_ACTIVE": "false",
                "META_SOCIAL_NEW_APP_REQUIRED": "true",
            },
            clear=False,
        ):
            ready, checks = get_meta_messaging_readiness(settings)
        self.assertTrue(ready)
        self.assertTrue(all(checks.values()))

    def test_retired_app_or_wrong_identity_is_not_ready(self):
        settings = MetaMessagingSettings(
            enabled=True,
            app_secret="secret",
            page_id="WRONG",
            page_access_token="page-token",
            instagram_account_id="17841413184256533",
            verify_token="verify-token",
            graph_api_version="v24.0",
        )
        with mock.patch.dict(
            "os.environ",
            {
                "META_APP_ID": "1784792718776344",
                "META_SOCIAL_ROLLBACK_ACTIVE": "false",
                "META_SOCIAL_NEW_APP_REQUIRED": "true",
            },
            clear=False,
        ):
            ready, checks = get_meta_messaging_readiness(settings)
        self.assertFalse(ready)
        self.assertFalse(checks["app_id_allowed_for_mode"])
        self.assertFalse(checks["page_id_allowlisted"])

    def test_wrong_identity_does_not_fail_platform_readiness(self):
        settings = MetaMessagingSettings(
            enabled=True,
            app_secret="secret",
            page_id="WRONG",
            page_access_token="page-token",
            instagram_account_id="",
            verify_token="verify-token",
            graph_api_version="v24.0",
        )
        with mock.patch.dict(
            "os.environ",
            {
                "META_APP_ID": "999000111",
                "META_SOCIAL_ROLLBACK_ACTIVE": "false",
                "META_SOCIAL_NEW_APP_REQUIRED": "true",
            },
            clear=False,
        ):
            ready, checks = get_meta_messaging_readiness(settings)
        self.assertTrue(ready)
        self.assertFalse(checks["page_id_allowlisted"])
        self.assertFalse(checks["instagram_id_allowlisted"])

    def test_retired_app_after_cutover_is_ready_only_in_explicit_single_secret_rollback_mode(self):
        settings = MetaMessagingSettings(
            enabled=True,
            app_secret="old-secret",
            page_id="378696005334409",
            page_access_token="old-page-token",
            instagram_account_id="17841413184256533",
            verify_token="rotated-verify-token",
            graph_api_version="v24.0",
        )
        with mock.patch.dict(
            "os.environ",
            {
                "META_APP_ID": "1784792718776344",
                "META_SOCIAL_ROLLBACK_ACTIVE": "true",
                "META_SOCIAL_NEW_APP_REQUIRED": "true",
            },
            clear=False,
        ):
            ready, checks = get_meta_messaging_readiness(settings)
        self.assertTrue(ready)
        self.assertTrue(checks["app_id_allowed_for_mode"])

    def test_retired_app_remains_ready_before_new_app_cutover(self):
        settings = MetaMessagingSettings(
            enabled=True,
            app_secret="old-secret",
            page_id="378696005334409",
            page_access_token="old-page-token",
            instagram_account_id="17841413184256533",
            verify_token="verify-token",
            graph_api_version="v24.0",
        )
        with mock.patch.dict(
            "os.environ",
            {
                "META_APP_ID": "1784792718776344",
                "META_SOCIAL_NEW_APP_REQUIRED": "false",
                "META_SOCIAL_ROLLBACK_ACTIVE": "false",
            },
            clear=False,
        ):
            ready, checks = get_meta_messaging_readiness(settings)
        self.assertTrue(ready)
        self.assertTrue(checks["app_id_allowed_for_mode"])


class MetaParseTests(unittest.TestCase):
    def test_facebook_text_event(self):
        payload = {
            "object": "page",
            "entry": [
                {
                    "id": "378696005334409",
                    "messaging": [
                        {
                            "sender": {"id": "PSID1"},
                            "recipient": {"id": "378696005334409"},
                            "timestamp": 1,
                            "message": {"mid": "m1", "text": "Hello"},
                        }
                    ],
                }
            ],
        }
        events = parse_meta_messaging_events(payload)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["channel"], "facebook")
        self.assertEqual(events[0]["sender_id"], "PSID1")
        self.assertEqual(events[0]["text"], "Hello")

    def test_page_standby_text_event(self):
        payload = {
            "object": "page",
            "entry": [
                {
                    "id": "378696005334409",
                    "standby": [
                        {
                            "sender": {"id": "PSID1"},
                            "recipient": {"id": "378696005334409"},
                            "timestamp": 1,
                            "message": {"mid": "m-standby", "text": "from page inbox"},
                        }
                    ],
                }
            ],
        }
        events = parse_meta_messaging_events(
            payload,
            page_id="378696005334409",
            instagram_account_id="17841413184256533",
        )
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["channel"], "facebook")
        self.assertEqual(events[0]["sender_id"], "PSID1")
        self.assertEqual(events[0]["text"], "from page inbox")
        self.assertEqual(events[0]["message_id"], "m-standby")

    def test_instagram_text_event(self):
        payload = {
            "object": "instagram",
            "entry": [
                {
                    "id": "IG_ACCOUNT",
                    "messaging": [
                        {
                            "sender": {"id": "IGSID1"},
                            "recipient": {"id": "IG_ACCOUNT"},
                            "timestamp": 1,
                            "message": {"mid": "m2", "text": "مرحبا"},
                        }
                    ],
                }
            ],
        }
        events = parse_meta_messaging_events(payload, instagram_account_id="IG_ACCOUNT")
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["channel"], "instagram")
        self.assertEqual(events[0]["sender_id"], "IGSID1")

    def test_echo_messages_ignored(self):
        payload = {
            "object": "page",
            "entry": [
                {
                    "id": "378696005334409",
                    "messaging": [
                        {
                            "sender": {"id": "378696005334409"},
                            "recipient": {"id": "PSID1"},
                            "timestamp": 1,
                            "message": {
                                "mid": "echo1",
                                "text": "bot reply",
                                "is_echo": True,
                            },
                        }
                    ],
                }
            ],
        }
        self.assertEqual(parse_meta_messaging_events(payload), [])

    def test_self_message_without_echo_flag_is_ignored(self):
        payload = {
            "object": "page",
            "entry": [
                {
                    "id": "378696005334409",
                    "messaging": [
                        {
                            "sender": {"id": "378696005334409"},
                            "recipient": {"id": "PSID1"},
                            "message": {"mid": "m-self", "text": "outbound"},
                        }
                    ],
                }
            ],
        }
        self.assertEqual(
            parse_meta_messaging_events(
                payload,
                page_id="378696005334409",
                instagram_account_id="17841413184256533",
            ),
            [],
        )

    def test_whatsapp_object_yields_no_events(self):
        payload = {
            "object": "whatsapp_business_account",
            "entry": [
                {
                    "id": "WABA",
                    "changes": [{"value": {"messages": [{"id": "w1", "text": {"body": "hi"}}]}}],
                }
            ],
        }
        self.assertEqual(parse_meta_messaging_events(payload), [])

    def test_page_payload_with_instagram_recipient_detected(self):
        payload = {
            "object": "page",
            "entry": [
                {
                    "id": "378696005334409",
                    "messaging": [
                        {
                            "sender": {"id": "IGSID9"},
                            "recipient": {"id": "IG_ACCOUNT"},
                            "timestamp": 1,
                            "message": {"mid": "m3", "text": "hi"},
                        }
                    ],
                }
            ],
        }
        events = parse_meta_messaging_events(
            payload,
            instagram_account_id="IG_ACCOUNT",
            page_id="378696005334409",
        )
        self.assertEqual(events[0]["channel"], "instagram")

    def test_postback_event_parsed(self):
        payload = {
            "object": "page",
            "entry": [
                {
                    "id": "378696005334409",
                    "messaging": [
                        {
                            "sender": {"id": "PSID1"},
                            "recipient": {"id": "378696005334409"},
                            "timestamp": 1,
                            "postback": {
                                "mid": "pb1",
                                "title": "Book",
                                "payload": "BOOK_NOW",
                            },
                        }
                    ],
                }
            ],
        }
        events = parse_meta_messaging_events(payload, page_id="378696005334409", instagram_account_id="IG_ACCOUNT")
        self.assertEqual(len(events), 1)
        self.assertTrue(events[0]["is_postback"])
        self.assertEqual(events[0]["text"], "Book")

    def test_wrong_page_id_rejected(self):
        payload = {
            "object": "page",
            "entry": [
                {
                    "id": "999999999999999",
                    "messaging": [
                        {
                            "sender": {"id": "PSID1"},
                            "recipient": {"id": "999999999999999"},
                            "timestamp": 1,
                            "message": {"mid": "m-wrong", "text": "Hi"},
                        }
                    ],
                }
            ],
        }
        events = parse_meta_messaging_events(payload, page_id="378696005334409", instagram_account_id="IG_ACCOUNT")
        self.assertEqual(events, [])

    def test_wrong_instagram_id_rejected(self):
        payload = {
            "object": "instagram",
            "entry": [
                {
                    "id": "WRONG_IG",
                    "messaging": [
                        {
                            "sender": {"id": "IGSID1"},
                            "recipient": {"id": "WRONG_IG"},
                            "timestamp": 1,
                            "message": {"mid": "m-wrong-ig", "text": "Hi"},
                        }
                    ],
                }
            ],
        }
        events = parse_meta_messaging_events(payload, page_id="378696005334409", instagram_account_id="IG_ACCOUNT")
        self.assertEqual(events, [])

    def test_comment_change_payload_is_not_processed(self):
        payload = {
            "object": "page",
            "entry": [
                {
                    "id": "378696005334409",
                    "changes": [
                        {
                            "field": "feed",
                            "value": {"item": "comment", "comment_id": "comment-1", "message": "hello"},
                        }
                    ],
                }
            ],
        }
        self.assertEqual(
            parse_meta_messaging_events(
                payload,
                page_id="378696005334409",
                instagram_account_id="IG_ACCOUNT",
            ),
            [],
        )

    def test_attachment_without_text_is_normalized_for_safe_handling(self):
        payload = {
            "object": "page",
            "entry": [
                {
                    "id": "378696005334409",
                    "messaging": [
                        {
                            "sender": {"id": "PSID-ATTACHMENT"},
                            "recipient": {"id": "378696005334409"},
                            "message": {
                                "mid": "attachment-1",
                                "attachments": [{"type": "image", "payload": {"url": "https://example.test/a"}}],
                            },
                        }
                    ],
                }
            ],
        }
        events = parse_meta_messaging_events(
            payload,
            page_id="378696005334409",
            instagram_account_id="IG_ACCOUNT",
        )
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["text"], "")
        self.assertEqual(events[0]["attachments"][0]["type"], "image")


class MetaDedupeTests(unittest.TestCase):
    def test_duplicate_message_ids_rejected(self):
        deduper = InMemoryMessageDeduper(ttl_seconds=60)
        self.assertTrue(deduper.claim("mid-1"))
        self.assertFalse(deduper.claim("mid-1"))
        self.assertTrue(deduper.claim("mid-2"))


if __name__ == "__main__":
    unittest.main()
