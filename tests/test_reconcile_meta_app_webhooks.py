"""Safety contracts for the dedicated Meta app webhook reconciler."""

import io
import urllib.error
from unittest.mock import patch

import pytest

from scripts.reconcile_meta_app_webhooks import (
    MetaWebhookReconcileError,
    _classify_error_message,
    _request_json,
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
                "callback_url": "https://www.linasaibot.com/webhook/meta-messaging",
                "active": True,
                "fields": instagram_fields or [],
            },
        ]
    }


def test_empty_approved_fields_are_valid_only_as_reconcile_precondition() -> None:
    fields = validate_webhook_state(_payload(), require_exact_fields=False)
    assert fields == {"instagram": set(), "page": set()}

    with pytest.raises(MetaWebhookReconcileError):
        validate_webhook_state(_payload(), require_exact_fields=True)


def test_exact_dm_only_fields_are_valid_final_state() -> None:
    expected = ["messages", "messaging_postbacks"]
    fields = validate_webhook_state(
        _payload(page_fields=expected, instagram_fields=list(reversed(expected))),
        require_exact_fields=True,
    )
    assert fields == {"instagram": set(expected), "page": set(expected)}


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
        page["fields"] = ["messages", "feed"]
    elif failure == "wrong_callback":
        page["callback_url"] = "https://example.invalid/webhook"
    elif failure == "inactive":
        page["active"] = False
    else:
        data.pop()

    with pytest.raises(MetaWebhookReconcileError):
        validate_webhook_state(payload, require_exact_fields=False)


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
