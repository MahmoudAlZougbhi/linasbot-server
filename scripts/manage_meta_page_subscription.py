#!/usr/bin/env python3
"""Manage the one allowlisted Meta Page subscription without exposing credentials."""

from __future__ import annotations

import argparse
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import cast

EXPECTED_PAGE_ID = "378696005334409"
EXPECTED_INSTAGRAM_ID = "17841413184256533"
EXPECTED_GRAPH_VERSION = "v24.0"
REQUIRED_FIELDS = ("messages", "messaging_postbacks")
DEFAULT_ENV_PATH = Path("/opt/linasbot/.env")


class MetaSubscriptionError(RuntimeError):
    """Raised when subscription state is outside the approved boundary."""


@dataclass(frozen=True)
class MetaConfig:
    app_id: str
    page_id: str
    instagram_id: str
    graph_version: str
    page_token: str


def load_config(path: Path) -> MetaConfig:
    """Read only the required values from the root-owned production env file."""

    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        if key in {
            "META_APP_ID",
            "META_PAGE_ID",
            "META_INSTAGRAM_ACCOUNT_ID",
            "META_GRAPH_API_VERSION",
            "META_PAGE_ACCESS_TOKEN",
        }:
            values[key] = value.strip()

    required = {
        "META_APP_ID",
        "META_PAGE_ID",
        "META_INSTAGRAM_ACCOUNT_ID",
        "META_GRAPH_API_VERSION",
        "META_PAGE_ACCESS_TOKEN",
    }
    missing = sorted(key for key in required if not values.get(key))
    if missing:
        raise MetaSubscriptionError(f"Production Meta configuration is incomplete keys={missing}")
    if values["META_PAGE_ID"] != EXPECTED_PAGE_ID:
        raise MetaSubscriptionError("Refusing an unexpected Facebook Page")
    if values["META_INSTAGRAM_ACCOUNT_ID"] != EXPECTED_INSTAGRAM_ID:
        raise MetaSubscriptionError("Refusing an unexpected Instagram account")
    if values["META_GRAPH_API_VERSION"] != EXPECTED_GRAPH_VERSION:
        raise MetaSubscriptionError("Refusing an unexpected Graph API version")
    if not values["META_APP_ID"].isdigit():
        raise MetaSubscriptionError("Refusing a malformed Meta App ID")

    return MetaConfig(
        app_id=values["META_APP_ID"],
        page_id=values["META_PAGE_ID"],
        instagram_id=values["META_INSTAGRAM_ACCOUNT_ID"],
        graph_version=values["META_GRAPH_API_VERSION"],
        page_token=values["META_PAGE_ACCESS_TOKEN"],
    )


def validate_subscription_payload(
    payload: dict[str, object],
    *,
    current_app_id: str,
) -> tuple[set[str], tuple[str, ...]]:
    """Return app IDs and current-app fields after strict response validation."""

    raw_data = payload.get("data")
    if not isinstance(raw_data, list):
        raise MetaSubscriptionError("Meta subscription response did not contain a data list")

    app_ids: set[str] = set()
    current_fields: tuple[str, ...] = ()
    for raw_item in raw_data:
        if not isinstance(raw_item, dict):
            raise MetaSubscriptionError("Meta subscription response contained an invalid item")
        item = cast(dict[str, object], raw_item)
        app_id = str(item.get("id") or "")
        if not app_id.isdigit():
            raise MetaSubscriptionError("Meta subscription response contained an invalid App ID")
        app_ids.add(app_id)
        if app_id == current_app_id:
            raw_fields = item.get("subscribed_fields")
            if not isinstance(raw_fields, list):
                raise MetaSubscriptionError("Current app subscription fields were not returned")
            current_fields = tuple(sorted(str(field) for field in raw_fields))

    return app_ids, current_fields


def validate_state(
    payload: dict[str, object],
    *,
    current_app_id: str,
    expectation: str,
) -> tuple[set[str], tuple[str, ...]]:
    """Enforce an empty or one-app-only state and the exact messaging fields."""

    app_ids, fields = validate_subscription_payload(payload, current_app_id=current_app_id)
    required_fields = tuple(sorted(REQUIRED_FIELDS))
    if expectation == "empty":
        if app_ids:
            raise MetaSubscriptionError("Expected no Page subscriptions")
    elif expectation == "current-only":
        if app_ids != {current_app_id}:
            raise MetaSubscriptionError("Expected the configured app to be the only Page subscription")
        if fields != required_fields:
            raise MetaSubscriptionError("Configured app has unexpected webhook fields")
    else:
        raise MetaSubscriptionError("Unknown subscription-state expectation")
    return app_ids, fields


def _request_json(
    config: MetaConfig,
    *,
    method: str,
    form: dict[str, str] | None = None,
) -> dict[str, object]:
    query = urllib.parse.urlencode({"fields": "id,subscribed_fields"}) if method == "GET" else ""
    suffix = f"?{query}" if query else ""
    url = f"https://graph.facebook.com/{config.graph_version}/{config.page_id}/subscribed_apps{suffix}"
    data = urllib.parse.urlencode(form).encode("utf-8") if form else None
    headers = {
        "Accept": "application/json",
        "Authorization": f"Bearer {config.page_token}",
    }
    if data is not None:
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            decoded: object = json.loads(response.read(1_000_000))
    except urllib.error.HTTPError as exc:
        raise MetaSubscriptionError(f"Meta subscription request returned HTTP {exc.code}") from None
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
        raise MetaSubscriptionError("Meta subscription request failed") from None
    if not isinstance(decoded, dict):
        raise MetaSubscriptionError("Meta subscription response was not an object")
    return cast(dict[str, object], decoded)


def _status(config: MetaConfig) -> dict[str, object]:
    return _request_json(config, method="GET")


def _print_state(app_ids: set[str], fields: tuple[str, ...], config: MetaConfig) -> None:
    print(f"[meta-subscription] app_count={len(app_ids)}")
    print(f"[meta-subscription] configured_app_present={config.app_id in app_ids}")
    print(f"[meta-subscription] fields={','.join(fields) if fields else 'none'}")


def status(config: MetaConfig, expectation: str) -> None:
    app_ids, fields = validate_state(_status(config), current_app_id=config.app_id, expectation=expectation)
    _print_state(app_ids, fields, config)
    print("[meta-subscription] status_ok=true")


def subscribe(config: MetaConfig, *, allow_present: bool) -> None:
    before = _status(config)
    try:
        app_ids, fields = validate_state(before, current_app_id=config.app_id, expectation="current-only")
    except MetaSubscriptionError:
        validate_state(before, current_app_id=config.app_id, expectation="empty")
    else:
        if not allow_present:
            raise MetaSubscriptionError("Configured app is already subscribed")
        _print_state(app_ids, fields, config)
        print("[meta-subscription] subscribe_noop=true")
        return

    result = _request_json(
        config,
        method="POST",
        form={"subscribed_fields": ",".join(REQUIRED_FIELDS)},
    )
    if result.get("success") is not True:
        raise MetaSubscriptionError("Meta did not confirm the Page subscription")
    app_ids, fields = validate_state(_status(config), current_app_id=config.app_id, expectation="current-only")
    _print_state(app_ids, fields, config)
    print("[meta-subscription] subscribed=true")


def unsubscribe(config: MetaConfig, *, allow_absent: bool) -> None:
    before = _status(config)
    try:
        app_ids, fields = validate_state(before, current_app_id=config.app_id, expectation="current-only")
    except MetaSubscriptionError:
        validate_state(before, current_app_id=config.app_id, expectation="empty")
        if not allow_absent:
            raise MetaSubscriptionError("Configured app is not subscribed") from None
        print("[meta-subscription] unsubscribe_noop=true")
        return
    _print_state(app_ids, fields, config)

    result = _request_json(config, method="DELETE")
    if result.get("success") is not True:
        raise MetaSubscriptionError("Meta did not confirm subscription removal")
    validate_state(_status(config), current_app_id=config.app_id, expectation="empty")
    print("[meta-subscription] unsubscribed=true")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "command",
        choices=("status", "subscribe", "unsubscribe"),
    )
    parser.add_argument(
        "--expect",
        choices=("empty", "current-only"),
        default="current-only",
    )
    parser.add_argument("--allow-present", action="store_true")
    parser.add_argument("--allow-absent", action="store_true")
    parser.add_argument(
        "--env-file",
        type=Path,
        default=Path(os.environ.get("META_ENV_PATH", str(DEFAULT_ENV_PATH))),
    )
    args = parser.parse_args()
    config = load_config(args.env_file)
    if args.command == "status":
        status(config, args.expect)
    elif args.command == "subscribe":
        subscribe(config, allow_present=args.allow_present)
    else:
        unsubscribe(config, allow_absent=args.allow_absent)


if __name__ == "__main__":
    main()
