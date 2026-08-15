"""Safety contracts for the dedicated Meta app webhook reconciler."""

import io
import urllib.error
from unittest.mock import patch

import pytest

from scripts.reconcile_meta_app_webhooks import (
    MetaWebhookReconcileError,
    _classify_error_message,
    _request_json,
    inspect_repairable_webhook_state,
    main,
    plan_webhook_reconcile,
    validate_webhook_state,
)


def _payload(
    *,
    page_fields: list[str] | None = None,
    instagram_fields: list[str] | None = None,
) -> dict[str, object]:
    return {
        "data": [
            {
                "object": "page",
                "callback_url": "https://www.linasaibot.com/webhook/meta-messaging",
                "active": True,
                "fields": page_fields or [],
            },
            {
                "object": "instagram",
                "callback_url": "https://www.linasaibot.com/webhook/instagram-login",
                "active": True,
                "fields": (
                    instagram_fields
                    if instagram_fields is not None
                    else ["comments", "messages", "messaging_postbacks"]
                ),
            },
        ]
    }


def test_social_reconcile_preserves_whatsapp_business_subscription() -> None:
    payload = _payload(
        page_fields=["feed", "messages", "messaging_postbacks"],
        instagram_fields=["comments", "messages", "messaging_postbacks"],
    )
    data = payload["data"]
    assert isinstance(data, list)
    data.append(
        {
            "object": "whatsapp_business_account",
            "callback_url": "https://www.linasaibot.com/webhook/whatsapp-cloud",
            "active": True,
            "fields": [{"name": "messages"}],
        }
    )

    fields = validate_webhook_state(payload, require_expected_fields=True)

    assert fields["page"] == {"feed", "messages", "messaging_postbacks"}
    assert fields["instagram"] == {"comments", "messages", "messaging_postbacks"}


def test_empty_page_fields_are_valid_only_as_reconcile_precondition() -> None:
    payload = _payload(instagram_fields=["comments", "messages", "messaging_postbacks"])
    fields = inspect_repairable_webhook_state(payload)
    assert fields == {
        "instagram": {"comments", "messages", "messaging_postbacks"},
        "page": set(),
    }

    with pytest.raises(MetaWebhookReconcileError):
        validate_webhook_state(payload, require_expected_fields=True)


def test_reconcile_precondition_allows_missing_inactive_or_wrong_callback() -> None:
    payload = {
        "data": [
            {
                "object": "page",
                "callback_url": "https://wrong.example/webhook",
                "active": False,
                "fields": ["messages"],
            },
            {
                "object": "instagram",
                "callback_url": "https://www.linasaibot.com/webhook/instagram-login",
                "active": True,
                "fields": ["comments", "messages", "messaging_postbacks"],
            },
        ]
    }

    assert inspect_repairable_webhook_state(payload) == {
        "page": {"messages"},
        "instagram": {"comments", "messages", "messaging_postbacks"},
    }


@pytest.mark.parametrize("failure", ["duplicate", "unknown_object", "unknown_field"])
def test_reconcile_precondition_rejects_unsafe_state(failure: str) -> None:
    payload = _payload()
    data = payload["data"]
    assert isinstance(data, list)
    if failure == "duplicate":
        data.append(dict(data[0]))
    elif failure == "unknown_object":
        data.append({"object": "user", "fields": []})
    else:
        page = data[0]
        assert isinstance(page, dict)
        page["fields"] = ["mentions"]

    with pytest.raises(MetaWebhookReconcileError):
        inspect_repairable_webhook_state(payload)


def test_dm_only_fields_are_not_a_valid_final_social_state() -> None:
    expected = ["messages", "messaging_postbacks"]
    with pytest.raises(MetaWebhookReconcileError):
        validate_webhook_state(
            _payload(page_fields=expected, instagram_fields=list(reversed(expected))),
            require_expected_fields=True,
        )


def test_dm_reconcile_preserves_page_feed_and_instagram_comments() -> None:
    before = inspect_repairable_webhook_state(
        _payload(
            page_fields=["feed"],
            instagram_fields=["comments", "messages", "messaging_postbacks"],
        )
    )

    targets = plan_webhook_reconcile(before)

    assert targets == {
        "page": {"feed", "messages", "messaging_postbacks"},
        "instagram": {"comments", "messages", "messaging_postbacks"},
    }
    assert (
        validate_webhook_state(
            _payload(
                page_fields=sorted(targets["page"]),
                instagram_fields=sorted(targets["instagram"]),
            ),
            require_expected_fields=True,
        )
        == targets
    )


def test_main_posts_merged_fields_without_removing_comments(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("META_APP_ID", "2963733803971681")
    monkeypatch.setenv("META_APP_SECRET", "app-secret")
    monkeypatch.setenv("META_WEBHOOK_VERIFY_TOKEN", "v" * 32)
    monkeypatch.setenv("META_GRAPH_API_VERSION", "v24.0")
    responses = iter(
        [
            _payload(
                page_fields=["feed"],
                instagram_fields=["comments", "messages", "messaging_postbacks"],
            ),
            {"success": True},
            _payload(
                page_fields=["feed", "messages", "messaging_postbacks"],
                instagram_fields=["comments", "messages", "messaging_postbacks"],
            ),
        ]
    )
    posted_forms: dict[str, dict[str, str]] = {}

    def fake_request(
        url: str,
        *,
        bearer: str,
        method: str = "GET",
        form: dict[str, str] | None = None,
        stage: str,
    ) -> dict[str, object]:
        del url, bearer, method, stage
        if form is not None:
            posted_forms[form["object"]] = dict(form)
        return next(responses)

    with patch("scripts.reconcile_meta_app_webhooks._request_json", side_effect=fake_request):
        main()

    assert posted_forms["page"]["fields"] == "feed,messages,messaging_postbacks"
    assert posted_forms["page"]["callback_url"] == "https://www.linasaibot.com/webhook/meta-messaging"
    assert posted_forms["page"]["verify_token"] == "v" * 32
    assert "instagram" not in posted_forms


def test_main_rejects_main_instagram_callback_without_post(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("META_APP_ID", "2963733803971681")
    monkeypatch.setenv("META_APP_SECRET", "app-secret")
    monkeypatch.setenv("META_WEBHOOK_VERIFY_TOKEN", "v" * 32)
    monkeypatch.setenv("META_GRAPH_API_VERSION", "v24.0")
    payload = _payload(page_fields=["feed", "messages", "messaging_postbacks"])
    rows = payload["data"]
    assert isinstance(rows, list)
    instagram = rows[1]
    assert isinstance(instagram, dict)
    instagram["callback_url"] = "https://www.linasaibot.com/webhook/meta-messaging"
    calls: list[tuple[str, dict[str, str] | None]] = []

    def fake_request(
        _url: str,
        *,
        bearer: str,
        method: str = "GET",
        form: dict[str, str] | None = None,
        stage: str,
    ) -> dict[str, object]:
        del bearer, stage
        calls.append((method, form))
        return payload

    with patch("scripts.reconcile_meta_app_webhooks._request_json", side_effect=fake_request):
        with pytest.raises(MetaWebhookReconcileError, match="callback object=instagram"):
            main()

    assert calls == [("GET", None)]


@pytest.mark.parametrize(
    "failure",
    ["extra_object", "extra_field", "wrong_callback", "inactive", "missing_object"],
)
def test_unapproved_webhook_state_fails_closed(failure: str) -> None:
    payload = _payload()
    data = payload["data"]
    assert isinstance(data, list)
    page = data[0]
    assert isinstance(page, dict)
    if failure == "extra_object":
        data.append(
            {
                "object": "user",
                "callback_url": "https://www.linasaibot.com/webhook/meta-messaging",
                "active": True,
                "fields": [],
            }
        )
    elif failure == "extra_field":
        page["fields"] = ["messages", "mentions"]
    elif failure == "wrong_callback":
        page["callback_url"] = "https://example.invalid/webhook"
    elif failure == "inactive":
        page["active"] = False
    else:
        data.pop()

    with pytest.raises(MetaWebhookReconcileError):
        validate_webhook_state(payload, require_expected_fields=False)


def test_graph_failure_does_not_render_credentials() -> None:
    app_token = "test-app-id|test-app-secret"
    verify_token = "test-verify-token-that-must-stay-redacted"
    http_error = urllib.error.HTTPError(
        "https://graph.facebook.com/v24.0/test-app/subscriptions",
        400,
        "Bad Request",
        hdrs=None,
        fp=io.BytesIO(
            b'{"error":{"message":"Invalid parameter fields secret-containing text",'
            b'"type":"OAuthException","code":100,"error_subcode":33}}'
        ),
    )

    with patch("urllib.request.urlopen", side_effect=http_error):
        with pytest.raises(MetaWebhookReconcileError) as captured:
            _request_json(
                "https://graph.facebook.com/v24.0/test-app/subscriptions",
                bearer=app_token,
                method="POST",
                form={"verify_token": verify_token},
                stage="test_stage",
            )

    rendered = str(captured.value)
    assert rendered == (
        "Meta webhook request failed stage=test_stage http=400 "
        "type=OAuthException code=100 subcode=33 "
        "reason=invalid_parameter mentions=fields"
    )
    assert app_token not in rendered
    assert verify_token not in rendered
    assert "secret-containing text" not in rendered


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ("Unsupported post request for instagram object", ("unsupported_request", ("instagram", "object"))),
        ("messages is not a valid field", ("unsupported_field", ("messages",))),
        ("Could not validate callback_url", ("callback_verification", ("callback_url",))),
        ("verify_token has a maximum length", ("verify_token_format", ("verify_token",))),
        ("verify_token is invalid", ("verify_token_invalid", ("verify_token",))),
    ],
)
def test_error_classifier_returns_only_fixed_labels(
    message: str,
    expected: tuple[str, tuple[str, ...]],
) -> None:
    assert _classify_error_message(message) == expected
