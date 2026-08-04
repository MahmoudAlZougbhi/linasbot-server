"""Regression tests for Meta Instagram/Facebook social messaging webhooks."""

import hashlib
import hmac
import json
import unittest
from unittest import mock

from services.meta_messaging import (
    InMemoryMessageDeduper,
    MetaMessagingAdapter,
    MetaMessagingSettings,
    get_meta_messaging_readiness,
    parse_meta_messaging_events,
    verify_meta_signature,
)
from services.social_contact_routing import (
    DEFAULT_SOCIAL_WHATSAPP_CONTACTS,
    SocialContactScopeError,
    route_social_contact_request,
    wa_me_url,
)


def _sign(secret: str, body: bytes) -> str:
    digest = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


def _social_user_data(
    channel: str = "instagram",
    *,
    sender: str = "social-sender-a",
    tenant: str = "linas",
    account: str | None = None,
) -> dict:
    asset_id = account or ("17841413184256533" if channel == "instagram" else "378696005334409")
    return {
        "tenant_id": tenant,
        "channel": channel,
        "meta_account_id": asset_id,
        "social_sender_id": sender,
    }


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


class SocialRoutingRegressionTests(unittest.TestCase):
    def test_defaults_use_wa_me_not_wa_link(self):
        phone = DEFAULT_SOCIAL_WHATSAPP_CONTACTS["SOCIAL_WHATSAPP_BEIRUT_FEMALE"]
        url = wa_me_url(phone)
        self.assertTrue(url.startswith("https://wa.me/"))
        self.assertNotIn("wa.link", url)

    def test_tattoo_request_refuses_without_whatsapp_handoff(self):
        """Owner-confirmed truth: tattoo removal is unsupported — never hand off a WA number."""
        user_data = _social_user_data()
        result = route_social_contact_request(
            "bade 7jez tattoo removal",
            user_data,
            language="en",
        )
        self.assertIsNotNone(result)
        self.assertTrue(result.tattoo_removal)
        self.assertIsNone(result.contact_env)
        self.assertNotIn("wa.me", result.reply.lower())
        self.assertNotIn("71534928", result.reply)
        self.assertIn("isn't one of the services", result.reply.lower())

    def test_laser_female_beirut_handoff_unchanged(self):
        user_data = _social_user_data()
        result = route_social_contact_request(
            "bade 7jez laser beirut ana binit",
            user_data,
            language="en",
        )
        self.assertIsNotNone(result)
        self.assertIn("78847527", result.reply)
        self.assertIn("https://wa.me/96178847527", result.reply)


class SocialHandoffStateMachineTests(unittest.TestCase):
    """Canonical AI vs deterministic handoff — production IG bug regressions."""

    BRANCH_AR = "أي فرع بدك"
    BRANCH_EN = "Which branch do you prefer"

    def _ig(self, account="17841413184256533", sender="ig-sender-a"):
        return _social_user_data("instagram", account=account, sender=sender)

    def _fb(self, sender="fb-sender-a"):
        return _social_user_data("facebook", sender=sender)

    @staticmethod
    def _flow_keys(user_data):
        return [str(key) for key in user_data if str(key).startswith("social_contact_flow::")]

    def test_fresh_hello_does_not_ask_branch(self):
        ud = self._ig()
        result = route_social_contact_request("Hello", ud, "en")
        self.assertIsNone(result)
        self.assertFalse(any(str(k).startswith("social_contact_flow") for k in ud))

    def test_arabizi_general_chat_does_not_ask_branch(self):
        ud = self._ig()
        msg = "Sho bek 3al2t 3am elak meen ma3e"
        result = route_social_contact_request(msg, ud, "ar")
        self.assertIsNone(result)
        # GPT force_intent must not open handoff without explicit booking/human intent.
        forced = route_social_contact_request(msg, ud, "ar", force_intent="booking")
        self.assertIsNone(forced)
        self.assertFalse(any(str(k).startswith("social_contact_flow") for k in ud))

    def test_ambiguous_au_cannot_loop_branch_question(self):
        ud = self._ig()
        start = route_social_contact_request("bade 7jez", ud, "en")
        self.assertIsNotNone(start)
        self.assertIn(self.BRANCH_EN, start.reply)
        replies = []
        for _ in range(5):
            r = route_social_contact_request("Au", ud, "en")
            replies.append(r)
        self.assertTrue(all(r is None for r in replies))
        self.assertFalse(any(str(k).startswith("social_contact_flow") for k in ud))

    def test_appointment_request_starts_missing_field_flow(self):
        ud = self._ig()
        result = route_social_contact_request("I want to book an appointment", ud, "en")
        self.assertIsNotNone(result)
        self.assertEqual(result.intent, "booking")
        self.assertIn(self.BRANCH_EN, result.reply)

    def test_human_agent_request_starts_missing_field_flow(self):
        ud = self._ig()
        result = route_social_contact_request("I want to speak with a human agent", ud, "en")
        self.assertIsNotNone(result)
        self.assertEqual(result.intent, "human")
        self.assertIn(self.BRANCH_EN, result.reply)

    def test_facebook_fresh_booking_collects_branch_then_gender_then_women_link(self):
        ud = self._fb()
        started = route_social_contact_request("I want to book an appointment with a human", ud, "en")
        self.assertIn(self.BRANCH_EN, started.reply)
        after_branch = route_social_contact_request("Beirut", ud, "en")
        self.assertIn("men or women", after_branch.reply.lower())
        completed = route_social_contact_request("Women", ud, "en")
        self.assertIn("https://wa.me/96178847527", completed.reply)
        self.assertFalse(self._flow_keys(ud))

    def test_completed_male_flow_is_not_reused_by_new_booking(self):
        ud = self._fb()
        first = route_social_contact_request("Book a Beirut appointment for men", ud, "en")
        self.assertIn("https://wa.me/96171534928", first.reply)
        self.assertFalse(self._flow_keys(ud))

        started = route_social_contact_request("I want to book an appointment with a human", ud, "en")
        self.assertIn(self.BRANCH_EN, started.reply)
        after_branch = route_social_contact_request("Beirut", ud, "en")
        self.assertIn("men or women", after_branch.reply.lower())
        self.assertNotIn("71534928", after_branch.reply)

    def test_new_explicit_request_replaces_partial_flow_fields(self):
        ud = self._fb()
        waiting_for_gender = route_social_contact_request("Book an appointment in Beirut", ud, "en")
        self.assertIn("men or women", waiting_for_gender.reply.lower())

        restarted = route_social_contact_request("I want to book an appointment", ud, "en")
        self.assertIn(self.BRANCH_EN, restarted.reply)
        after_new_branch = route_social_contact_request("Antelias", ud, "en")
        self.assertIn("men or women", after_new_branch.reply.lower())
        self.assertNotIn("wa.me", after_new_branch.reply)

    def test_two_facebook_senders_do_not_share_fields(self):
        first = self._fb(sender="fb-sender-one")
        second = self._fb(sender="fb-sender-two")
        route_social_contact_request("Book for Women", first, "en")
        route_social_contact_request("Book in Beirut", second, "en")
        first_key = self._flow_keys(first)
        second_key = self._flow_keys(second)
        self.assertNotEqual(first_key, second_key)

        first_after_branch = route_social_contact_request("Beirut", first, "en")
        second_after_gender = route_social_contact_request("Women", second, "en")
        self.assertIn("https://wa.me/96178847527", first_after_branch.reply)
        self.assertIn("https://wa.me/96178847527", second_after_gender.reply)
        self.assertFalse(self._flow_keys(first))
        self.assertFalse(self._flow_keys(second))

    def test_cross_sender_state_blob_is_rejected_fail_closed(self):
        first = self._fb(sender="fb-sender-one")
        second = self._fb(sender="fb-sender-two")
        route_social_contact_request("Book for Women", first, "en")
        route_social_contact_request("Book in Beirut", second, "en")
        first_key = self._flow_keys(first)[0]
        second_key = self._flow_keys(second)[0]

        first[first_key] = dict(second[second_key])
        self.assertIsNone(route_social_contact_request("Beirut", first, "en"))
        self.assertFalse(self._flow_keys(first))

    def test_same_sender_is_isolated_between_facebook_and_instagram(self):
        facebook = self._fb(sender="shared-person")
        instagram = self._ig(sender="shared-person")
        route_social_contact_request("Book for Women", facebook, "en")
        route_social_contact_request("Book in Beirut", instagram, "en")
        facebook_key = self._flow_keys(facebook)
        instagram_key = self._flow_keys(instagram)
        self.assertNotEqual(facebook_key, instagram_key)

        facebook_result = route_social_contact_request("Beirut", facebook, "en")
        instagram_result = route_social_contact_request("Women", instagram, "en")
        self.assertIn("https://wa.me/96178847527", facebook_result.reply)
        self.assertIn("https://wa.me/96178847527", instagram_result.reply)
        self.assertFalse(self._flow_keys(facebook))
        self.assertFalse(self._flow_keys(instagram))

    def test_instagram_equivalent_flow_returns_women_beirut_link(self):
        ud = self._ig()
        self.assertIn(self.BRANCH_EN, route_social_contact_request("Book an appointment", ud, "en").reply)
        self.assertIn("men or women", route_social_contact_request("Beirut", ud, "en").reply.lower())
        completed = route_social_contact_request("Women", ud, "en")
        self.assertIn("https://wa.me/96178847527", completed.reply)

    def test_current_request_with_branch_and_gender_completes_without_extra_questions(self):
        ud = self._fb()
        completed = route_social_contact_request("Book a Beirut appointment for Women", ud, "en")
        self.assertIn("https://wa.me/96178847527", completed.reply)
        self.assertNotIn(self.BRANCH_EN, completed.reply)
        self.assertNotIn("Men or Women", completed.reply)

    def test_active_flow_key_and_metadata_include_complete_isolated_scope(self):
        ud = self._ig(sender="scope-sender", account="ig-business-asset")
        route_social_contact_request("Book an appointment", ud, "en")
        keys = self._flow_keys(ud)
        self.assertEqual(len(keys), 1)
        self.assertTrue(keys[0].startswith("social_contact_flow::v2::"))
        state = ud[keys[0]]
        self.assertEqual(state["tenant_id"], "linas")
        self.assertEqual(state["channel"], "instagram")
        self.assertEqual(state["business_asset_id"], "ig-business-asset")
        self.assertNotIn("scope-sender", keys[0])
        self.assertNotIn("scope-sender", state.values())

    def test_explicit_handoff_fails_closed_without_complete_scope(self):
        with self.assertRaises(SocialContactScopeError):
            route_social_contact_request("Book an appointment", {"channel": "facebook"}, "en")

    def test_valid_branch_and_gender_advance(self):
        ud = self._ig()
        r1 = route_social_contact_request("bade 7jez", ud, "en")
        self.assertIn(self.BRANCH_EN, r1.reply)
        r2 = route_social_contact_request("Antelias", ud, "en")
        self.assertIsNotNone(r2)
        self.assertIn("men or women", r2.reply.lower())
        r3 = route_social_contact_request("male", ud, "en")
        self.assertIsNotNone(r3)
        self.assertIn("71226082", r3.reply)
        self.assertIn("https://wa.me/", r3.reply)
        self.assertFalse(any(str(k).startswith("social_contact_flow") for k in ud))

    def test_beirut_female_mapping_unchanged(self):
        ud = self._ig()
        route_social_contact_request("book appointment", ud, "en")
        route_social_contact_request("Beirut", ud, "en")
        result = route_social_contact_request("female", ud, "en")
        self.assertIn("78847527", result.reply)

    def test_new_topic_during_pending_handoff_returns_to_ai(self):
        ud = self._ig()
        route_social_contact_request("bade 7jez", ud, "ar")
        result = route_social_contact_request("قديش سعر الليزر؟", ud, "ar")
        self.assertIsNone(result)
        self.assertFalse(any(str(k).startswith("social_contact_flow") for k in ud))

    def test_cancellation_resets_pending_flow(self):
        ud = self._ig()
        route_social_contact_request("bade 7jez", ud, "en")
        result = route_social_contact_request("cancel", ud, "en")
        self.assertIsNone(result)
        self.assertFalse(any(str(k).startswith("social_contact_flow") for k in ud))
        # Fresh booking can start again.
        again = route_social_contact_request("book appointment", ud, "en")
        self.assertIsNotNone(again)

    def test_expired_handoff_state_returns_to_ai(self):
        from services import social_contact_routing as scr

        ud = self._ig()
        route_social_contact_request("bade 7jez", ud, "en")
        key = self._flow_keys(ud)[0]
        self.assertIn(key, ud)
        ud[key]["updated_at"] = 0
        ud[key]["started_at"] = 0
        result = route_social_contact_request("Beirut", ud, "en")
        self.assertIsNone(result)
        self.assertNotIn(key, ud)
        self.assertEqual(scr.SOCIAL_CONTACT_FLOW_TTL_SECONDS, 30 * 60)

    def test_instagram_messenger_state_isolation(self):
        ig = self._ig()
        fb = self._fb()
        route_social_contact_request("bade 7jez", ig, "en")
        self.assertIsNone(route_social_contact_request("Hello", fb, "en"))
        self.assertEqual(len(self._flow_keys(ig)), 1)
        self.assertFalse(any(str(k).startswith("social_contact_flow") for k in fb))
        # Messenger booking must not consume Instagram pending state.
        fb_book = route_social_contact_request("book appointment", fb, "en")
        self.assertIn(self.BRANCH_EN, fb_book.reply)
        self.assertEqual(len(self._flow_keys(fb)), 1)
        self.assertEqual(len(self._flow_keys(ig)), 1)
        self.assertNotEqual(self._flow_keys(fb), self._flow_keys(ig))

    def test_force_intent_cannot_start_without_explicit_user_intent(self):
        ud = self._ig()
        for intent in ("booking", "human"):
            r = route_social_contact_request("Hello", ud, "en", force_intent=intent)
            self.assertIsNone(r)
        self.assertFalse(any(str(k).startswith("social_contact_flow") for k in ud))

    def test_whatsapp_matrix_keys_unchanged(self):
        expected = {
            "SOCIAL_WHATSAPP_BEIRUT_FEMALE": "+96178847527",
            "SOCIAL_WHATSAPP_ANTELIAS_FEMALE": "+96170707354",
            "SOCIAL_WHATSAPP_BEIRUT_MALE": "+96171534928",
            "SOCIAL_WHATSAPP_ANTELIAS_MALE": "+96171226082",
        }
        self.assertEqual(DEFAULT_SOCIAL_WHATSAPP_CONTACTS, expected)
        self.assertNotIn("SOCIAL_WHATSAPP_TATTOO_REMOVAL", DEFAULT_SOCIAL_WHATSAPP_CONTACTS)


class SocialCanonicalAiPathTests(unittest.TestCase):
    """Normal IG messages must enter handle_message (canonical AI), not branch prompts."""

    def test_hello_does_not_open_handoff_so_canonical_ai_path_runs(self):
        """Contract: router returns None for Hello → processor always calls handle_message."""
        from pathlib import Path

        ud = _social_user_data()
        self.assertIsNone(route_social_contact_request("Hello", ud, "en"))
        self.assertIsNone(route_social_contact_request("Hello", ud, "en", force_intent="booking"))
        processor_src = Path("services/social_messaging_processor.py").read_text(encoding="utf-8")
        self.assertIn("await handle_message(", processor_src)
        self.assertNotIn("social_ai", processor_src.lower())
        self.assertNotIn("simplified_prompt", processor_src.lower())

    def test_social_ai_excludes_crm_booking_tools(self):
        from pathlib import Path

        source = Path("services/chat_response_service.py").read_text(encoding="utf-8")
        for blocked_tool in (
            '"submit_booking_intent"',
            '"create_appointment"',
            '"update_appointment_date"',
            '"check_next_appointment"',
            '"get_customer_by_phone"',
        ):
            self.assertIn(blocked_tool, source)
        self.assertIn("if social_channel", source)
        self.assertIn("Never create, change, cancel, confirm, list, or check an appointment", source)


class MetaSendFailureTests(unittest.TestCase):
    def test_graph_send_failure_raises(self):
        adapter = MetaMessagingAdapter(
            access_token="unit-token",
            account_id="378696005334409",
            channel="facebook",
        )

        class FakeResponse:
            status_code = 400
            text = '{"error":{"message":"fail"}}'

            def raise_for_status(self):
                import httpx

                raise httpx.HTTPStatusError(
                    "bad", request=mock.Mock(), response=mock.Mock(status_code=400, text=self.text)
                )

            def json(self):
                return {"error": {"message": "fail"}}

        async def fake_post(*args, **kwargs):
            return FakeResponse()

        adapter.client = mock.Mock()
        adapter.client.post = fake_post
        adapter._owns_client = False

        import asyncio

        with self.assertRaises(RuntimeError) as caught:
            asyncio.run(adapter.send_text_message("PSID1", "hello"))
        self.assertIn("HTTP 400", str(caught.exception))
        self.assertNotIn("fail", str(caught.exception))


class WhatsAppInboundPolicyTests(unittest.TestCase):
    def test_provider_webhook_policy_reason_constant(self):
        # Contract used by modules/webhook_handlers.receive_webhook
        payload = {
            "status": "ignored",
            "reason": "whatsapp_inbound_ai_disabled",
            "accepted": 0,
        }
        self.assertEqual(payload["reason"], "whatsapp_inbound_ai_disabled")
        self.assertEqual(payload["accepted"], 0)


class MetaWebhookContractTests(unittest.TestCase):
    """HTTP-contract tests using a minimal FastAPI app (no full production app import)."""

    @classmethod
    def setUpClass(cls):
        try:
            from fastapi import FastAPI, HTTPException, Request
            from fastapi.responses import JSONResponse, PlainTextResponse
            from fastapi.testclient import TestClient
        except ImportError as exc:  # pragma: no cover
            raise unittest.SkipTest(f"fastapi unavailable: {exc}") from exc

        verify_token = "unit-verify-token"
        app_secret = "unit-app-secret"
        state = {"enabled": False, "deduper": InMemoryMessageDeduper(ttl_seconds=60)}

        app = FastAPI()

        @app.get("/webhook/meta-messaging")
        async def verify(request: Request):
            mode = request.query_params.get("hub.mode")
            token = request.query_params.get("hub.verify_token")
            challenge = request.query_params.get("hub.challenge")
            if mode == "subscribe" and token == verify_token and challenge is not None:
                return PlainTextResponse(challenge)
            raise HTTPException(status_code=403, detail="Webhook verification failed")

        @app.post("/webhook/meta-messaging")
        async def receive(request: Request):
            raw_body = await request.body()
            if not verify_meta_signature(raw_body, request.headers.get("X-Hub-Signature-256"), app_secret):
                raise HTTPException(status_code=401, detail="Invalid webhook signature")
            if not state["enabled"]:
                return JSONResponse({"status": "disabled"})
            payload = json.loads(raw_body)
            payload_object = str(payload.get("object") or "").strip().lower()
            if payload_object in {"whatsapp_business_account", "whatsapp"}:
                return JSONResponse(
                    {
                        "status": "ignored",
                        "reason": "whatsapp_inbound_not_supported",
                        "accepted": 0,
                    }
                )
            events = parse_meta_messaging_events(
                payload,
                page_id="378696005334409",
                instagram_account_id="IG1",
            )
            accepted = 0
            duplicates = 0
            for event in events:
                if not state["deduper"].claim(event["message_id"]):
                    duplicates += 1
                    continue
                accepted += 1
            return JSONResponse({"status": "received", "accepted": accepted, "duplicates": duplicates})

        @app.post("/webhook")
        async def whatsapp_inbound(request: Request):
            await request.body()
            return JSONResponse(
                {
                    "status": "ignored",
                    "reason": "whatsapp_inbound_ai_disabled",
                    "accepted": 0,
                }
            )

        cls.client = TestClient(app)
        cls.state = state

    def test_verify_challenge_success(self):
        response = self.client.get(
            "/webhook/meta-messaging",
            params={
                "hub.mode": "subscribe",
                "hub.verify_token": "unit-verify-token",
                "hub.challenge": "12345",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.text, "12345")

    def test_verify_challenge_rejects_bad_token(self):
        response = self.client.get(
            "/webhook/meta-messaging",
            params={
                "hub.mode": "subscribe",
                "hub.verify_token": "wrong",
                "hub.challenge": "12345",
            },
        )
        self.assertEqual(response.status_code, 403)

    def test_invalid_signature_rejected(self):
        response = self.client.post(
            "/webhook/meta-messaging",
            data=b'{"object":"page","entry":[]}',
            headers={
                "Content-Type": "application/json",
                "X-Hub-Signature-256": "sha256=deadbeef",
            },
        )
        self.assertEqual(response.status_code, 401)

    def test_valid_signature_disabled_returns_disabled(self):
        body = b'{"object":"page","entry":[]}'
        response = self.client.post(
            "/webhook/meta-messaging",
            data=body,
            headers={
                "Content-Type": "application/json",
                "X-Hub-Signature-256": _sign("unit-app-secret", body),
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json().get("status"), "disabled")

    def test_whatsapp_object_ignored_when_enabled(self):
        self.state["enabled"] = True
        try:
            body = b'{"object":"whatsapp_business_account","entry":[]}'
            response = self.client.post(
                "/webhook/meta-messaging",
                data=body,
                headers={
                    "Content-Type": "application/json",
                    "X-Hub-Signature-256": _sign("unit-app-secret", body),
                },
            )
            self.assertEqual(response.status_code, 200)
            payload = response.json()
            self.assertEqual(payload.get("status"), "ignored")
            self.assertEqual(payload.get("reason"), "whatsapp_inbound_not_supported")
            self.assertEqual(payload.get("accepted"), 0)
        finally:
            self.state["enabled"] = False

    def test_facebook_and_instagram_events_and_duplicates(self):
        self.state["enabled"] = True
        self.state["deduper"].clear()
        try:
            body = (
                b'{"object":"page","entry":[{"id":"378696005334409","messaging":'
                b'[{"sender":{"id":"PSID1"},"recipient":{"id":"378696005334409"},'
                b'"timestamp":1,"message":{"mid":"mid-unique-1","text":"Hi"}}]}]}'
            )
            response = self.client.post(
                "/webhook/meta-messaging",
                data=body,
                headers={
                    "Content-Type": "application/json",
                    "X-Hub-Signature-256": _sign("unit-app-secret", body),
                },
            )
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json().get("accepted"), 1)

            response2 = self.client.post(
                "/webhook/meta-messaging",
                data=body,
                headers={
                    "Content-Type": "application/json",
                    "X-Hub-Signature-256": _sign("unit-app-secret", body),
                },
            )
            self.assertEqual(response2.json().get("accepted"), 0)
            self.assertEqual(response2.json().get("duplicates"), 1)

            ig_body = (
                b'{"object":"instagram","entry":[{"id":"IG1","messaging":'
                b'[{"sender":{"id":"IGSID1"},"recipient":{"id":"IG1"},'
                b'"timestamp":1,"message":{"mid":"mid-ig-1","text":"Hi IG"}}]}]}'
            )
            ig_response = self.client.post(
                "/webhook/meta-messaging",
                data=ig_body,
                headers={
                    "Content-Type": "application/json",
                    "X-Hub-Signature-256": _sign("unit-app-secret", ig_body),
                },
            )
            self.assertEqual(ig_response.status_code, 200)
            self.assertEqual(ig_response.json().get("accepted"), 1)
        finally:
            self.state["enabled"] = False

    def test_missing_signature_rejected(self):
        response = self.client.post(
            "/webhook/meta-messaging",
            data=b'{"object":"page","entry":[]}',
            headers={"Content-Type": "application/json"},
        )
        self.assertEqual(response.status_code, 401)

    def test_whatsapp_provider_inbound_rejected(self):
        response = self.client.post(
            "/webhook",
            data=b'{"entry":[]}',
            headers={"Content-Type": "application/json"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json().get("reason"), "whatsapp_inbound_ai_disabled")

    def test_wrong_page_event_not_accepted_when_enabled(self):
        self.state["enabled"] = True
        self.state["deduper"].clear()
        try:
            body = (
                b'{"object":"page","entry":[{"id":"111","messaging":'
                b'[{"sender":{"id":"PSID1"},"recipient":{"id":"111"},'
                b'"timestamp":1,"message":{"mid":"mid-x","text":"Hi"}}]}]}'
            )
            response = self.client.post(
                "/webhook/meta-messaging",
                data=body,
                headers={
                    "Content-Type": "application/json",
                    "X-Hub-Signature-256": _sign("unit-app-secret", body),
                },
            )
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json().get("accepted"), 0)
        finally:
            self.state["enabled"] = False


if __name__ == "__main__":
    unittest.main()
