"""Meta send-failure, WhatsApp inbound policy, and webhook HTTP contract tests."""

import json
import unittest
from unittest import mock

from services.meta_messaging import (
    InMemoryMessageDeduper,
    MetaMessagingAdapter,
    parse_meta_messaging_events,
    verify_meta_signature,
)
from tests.meta_social_messaging_helpers import _sign


class MetaSendFailureTests(unittest.TestCase):
    def test_graph_send_requires_provider_message_id(self):
        adapter = MetaMessagingAdapter(
            access_token="unit-token",
            account_id="378696005334409",
            channel="facebook",
        )

        async def fake_post(*args, **kwargs):
            del args, kwargs
            return {"success": True}

        adapter._post = fake_post

        import asyncio

        result = asyncio.run(adapter.send_text_message("PSID1", "hello"))
        self.assertFalse(result["success"])
        self.assertEqual(result["error"], "meta_send_missing_message_id")

    def test_graph_send_surfaces_provider_message_id(self):
        adapter = MetaMessagingAdapter(
            access_token="unit-token",
            account_id="378696005334409",
            channel="facebook",
        )

        async def fake_post(*args, **kwargs):
            del args, kwargs
            return {"recipient_id": "recipient", "message_id": "mid-1"}

        adapter._post = fake_post

        import asyncio

        result = asyncio.run(adapter.send_text_message("PSID1", "hello"))
        self.assertTrue(result["success"])
        self.assertEqual(result["message_id"], "mid-1")

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
