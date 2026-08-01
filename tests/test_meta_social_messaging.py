"""Regression tests for Meta Instagram/Facebook social messaging webhooks."""

import hashlib
import hmac
import json
import unittest

from services.meta_messaging import (
    InMemoryMessageDeduper,
    parse_meta_messaging_events,
    verify_meta_signature,
)
from services.social_contact_routing import (
    DEFAULT_SOCIAL_WHATSAPP_CONTACTS,
    route_social_contact_request,
    wa_me_url,
)


def _sign(secret: str, body: bytes) -> str:
    digest = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


class MetaSignatureTests(unittest.TestCase):
    def test_valid_signature_accepted(self):
        body = b'{"object":"page","entry":[]}'
        secret = "test_app_secret"
        self.assertTrue(verify_meta_signature(body, _sign(secret, body), secret))

    def test_invalid_signature_rejected(self):
        body = b'{"object":"page","entry":[]}'
        self.assertFalse(
            verify_meta_signature(body, "sha256=deadbeef", "test_app_secret")
        )

    def test_missing_signature_rejected(self):
        self.assertFalse(verify_meta_signature(b"{}", None, "secret"))

    def test_missing_secret_rejected(self):
        body = b"{}"
        self.assertFalse(verify_meta_signature(body, _sign("secret", body), ""))


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
        events = parse_meta_messaging_events(payload, instagram_account_id="IG_ACCOUNT")
        self.assertEqual(events[0]["channel"], "instagram")


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

    def test_tattoo_routing_beirut_only(self):
        user_data = {}
        result = route_social_contact_request(
            "bade 7jez tattoo removal",
            user_data,
            known_gender=None,
            language="en",
        )
        self.assertIsNotNone(result)
        self.assertTrue(result.tattoo_removal)
        self.assertIn("71534928", result.reply)
        self.assertIn("https://wa.me/", result.reply)


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
            if not verify_meta_signature(
                raw_body, request.headers.get("X-Hub-Signature-256"), app_secret
            ):
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
            events = parse_meta_messaging_events(payload)
            accepted = 0
            duplicates = 0
            for event in events:
                if not state["deduper"].claim(event["message_id"]):
                    duplicates += 1
                    continue
                accepted += 1
            return JSONResponse(
                {"status": "received", "accepted": accepted, "duplicates": duplicates}
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


if __name__ == "__main__":
    unittest.main()
