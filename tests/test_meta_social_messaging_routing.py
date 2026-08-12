"""Social contact routing and handoff state-machine regressions."""

import unittest

from services.social_contact_routing import (
    DEFAULT_SOCIAL_WHATSAPP_CONTACTS,
    SOCIAL_BOOKING_PREFERENCES_FIELD,
    SocialContactScopeError,
    get_social_booking_preference,
    restore_social_booking_preference,
    route_social_contact_request,
    social_booking_preference_key,
    wa_me_url,
)
from tests.meta_social_messaging_helpers import _social_user_data


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

    def test_completed_male_flow_is_reused_only_as_scoped_durable_preference(self):
        ud = self._fb()
        first = route_social_contact_request("Book a Beirut appointment for men", ud, "en")
        self.assertIn("https://wa.me/96171534928", first.reply)
        self.assertEqual(first.preference_to_persist, "male")
        self.assertFalse(self._flow_keys(ud))

        started = route_social_contact_request("I want to book an appointment with a human", ud, "en")
        self.assertIn(self.BRANCH_EN, started.reply)
        after_branch = route_social_contact_request("Beirut", ud, "en")
        self.assertIn("https://wa.me/96171534928", after_branch.reply)
        self.assertNotIn("men or women", after_branch.reply.lower())

    @staticmethod
    def _persisted_preference(user_data, preference):
        return {SOCIAL_BOOKING_PREFERENCES_FIELD: {social_booking_preference_key(user_data): {"value": preference}}}

    def test_new_facebook_customer_saves_explicit_preference_and_returns_women_beirut_once(self):
        ud = self._fb(sender="new-facebook-customer")
        self.assertIn(self.BRANCH_EN, route_social_contact_request("book appointment", ud, "en").reply)
        self.assertIn("men or women", route_social_contact_request("Beirut", ud, "en").reply.lower())

        completed = route_social_contact_request("Women", ud, "en")
        self.assertIn("https://wa.me/96178847527", completed.reply)
        self.assertEqual(completed.preference_to_persist, "female")
        self.assertEqual(get_social_booking_preference(ud), "female")
        self.assertFalse(self._flow_keys(ud))
        self.assertIsNone(route_social_contact_request("Women", ud, "en"))

    def test_returning_facebook_customer_reuses_durable_preference_but_starts_fresh_flow(self):
        original = self._fb(sender="returning-facebook-customer")
        persisted = self._persisted_preference(original, "female")
        returning = self._fb(sender="returning-facebook-customer")
        self.assertEqual(restore_social_booking_preference(returning, persisted), "female")

        started = route_social_contact_request("I want to book an appointment", returning, "en")
        self.assertIn(self.BRANCH_EN, started.reply)
        completed = route_social_contact_request("Beirut", returning, "en")
        self.assertIn("https://wa.me/96178847527", completed.reply)
        self.assertNotIn("men or women", completed.reply.lower())
        self.assertFalse(self._flow_keys(returning))

    def test_durable_preference_isolated_by_sender_workspace_channel_and_asset(self):
        source = self._fb(sender="isolated-customer")
        persisted = self._persisted_preference(source, "female")
        variants = (
            self._fb(sender="different-customer"),
            _social_user_data("facebook", sender="isolated-customer", tenant="other-workspace"),
            self._ig(sender="isolated-customer"),
            _social_user_data("facebook", sender="isolated-customer", account="other-page"),
        )
        for variant in variants:
            self.assertIsNone(restore_social_booking_preference(variant, persisted))
            waiting_for_gender = route_social_contact_request("Book in Beirut", variant, "en")
            self.assertIn("men or women", waiting_for_gender.reply.lower())

    def test_cancellation_and_ttl_clear_flow_but_keep_durable_preference(self):
        ud = self._fb(sender="flow-cleanup-customer")
        restore_social_booking_preference(ud, self._persisted_preference(ud, "female"))
        route_social_contact_request("Book appointment", ud, "en")
        self.assertIsNone(route_social_contact_request("cancel", ud, "en"))
        self.assertEqual(get_social_booking_preference(ud), "female")

        route_social_contact_request("Book appointment", ud, "en")
        key = self._flow_keys(ud)[0]
        ud[key]["updated_at"] = 0
        self.assertIsNone(route_social_contact_request("Beirut", ud, "en"))
        self.assertEqual(get_social_booking_preference(ud), "female")

    def test_explicit_preference_change_updates_future_booking(self):
        initial = self._fb(sender="change-preference-customer")
        restore_social_booking_preference(initial, self._persisted_preference(initial, "male"))
        changed = route_social_contact_request("Change my preference to Women.", initial, "en")
        self.assertIsNotNone(changed)
        self.assertEqual(changed.intent, "preference")
        self.assertEqual(changed.preference_to_persist, "female")

        returning = self._fb(sender="change-preference-customer")
        persisted = self._persisted_preference(returning, "female")
        restore_social_booking_preference(returning, persisted)
        self.assertIn(
            "https://wa.me/96178847527",
            route_social_contact_request("Book in Beirut", returning, "en").reply,
        )

    def test_natural_preference_change_phrases_normalize_to_canonical_values(self):
        men = self._fb(sender="phrase-men")
        men_change = route_social_contact_request("I am Men.", men, "en")
        self.assertEqual(men_change.preference_to_persist, "male")
        self.assertEqual(get_social_booking_preference(men), "male")

        women = self._fb(sender="phrase-women")
        women_change = route_social_contact_request("Use Women from now on.", women, "en")
        self.assertEqual(women_change.preference_to_persist, "female")
        self.assertEqual(get_social_booking_preference(women), "female")

    def test_booking_for_another_person_overrides_current_flow_without_replacing_default(self):
        ud = self._fb(sender="other-person-customer")
        restore_social_booking_preference(ud, self._persisted_preference(ud, "male"))
        self.assertIn(self.BRANCH_EN, route_social_contact_request("Book an appointment", ud, "en").reply)
        self.assertIn(self.BRANCH_EN, route_social_contact_request("for my wife", ud, "en").reply)
        override = route_social_contact_request("Beirut", ud, "en")
        self.assertIn("https://wa.me/96178847527", override.reply)
        self.assertIsNone(override.preference_to_persist)
        self.assertEqual(get_social_booking_preference(ud), "male")

        later = route_social_contact_request("Book in Beirut", ud, "en")
        self.assertIn("https://wa.me/96171534928", later.reply)

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

        source = Path("services/chat_response_runtime_gpt.py").read_text(encoding="utf-8")
        prompt = Path("services/chat_response_runtime_prompt.py").read_text(encoding="utf-8")
        features = Path("services/product_features.py").read_text(encoding="utf-8")
        for blocked_tool in (
            "submit_booking_intent",
            "create_appointment",
            "update_appointment_date",
            "check_next_appointment",
            "get_customer_by_phone",
        ):
            self.assertIn(blocked_tool, features)
        self.assertIn("LEGACY_BOOKING_TOOL_NAMES", source)
        self.assertIn("Never create, change, cancel, confirm, list, or check an appointment", prompt)


if __name__ == "__main__":
    unittest.main()
