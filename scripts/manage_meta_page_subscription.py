#!/usr/bin/env python3
"""Manage the one allowlisted Meta Page subscription without exposing credentials."""

from __future__ import annotations

import argparse
import importlib
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from contextlib import AbstractContextManager
from dataclasses import dataclass
from pathlib import Path
from typing import cast

_webhook_contract = importlib.import_module("scripts.meta_webhook_contract" if __package__ else "meta_webhook_contract")

ALLOWED_PAGE_SUBSCRIPTION_FIELDS = _webhook_contract.ALLOWED_PAGE_SUBSCRIPTION_FIELDS
merge_subscription_fields = _webhook_contract.merge_subscription_fields

EXPECTED_PAGE_ID = "378696005334409"
EXPECTED_INSTAGRAM_ID = "17841413184256533"
EXPECTED_APP_ID = "2963733803971681"
RETIRED_APP_ID = "1784792718776344"
RETIRED_APP_CONFIRMATION = "CONFIRM_RETIRED_META_APP_SUBSCRIPTION"
ALLOWED_APP_IDS = frozenset({EXPECTED_APP_ID, RETIRED_APP_ID})
EXPECTED_GRAPH_VERSION = "v24.0"
DEFAULT_ENV_PATH = Path("/opt/linasbot/.env")


class MetaSubscriptionError(RuntimeError):
    """Raised when subscription state is outside the approved boundary."""


def _subscription_writer_lock(config: MetaConfig) -> AbstractContextManager[None]:
    """Load the shared runtime lock lazily so direct script execution is safe."""

    repo_dir = str(Path(__file__).resolve().parents[1])
    if repo_dir not in sys.path:
        sys.path.insert(0, repo_dir)
    from services.meta_oauth_page_lock import (
        lock_facebook_page_subscription_operation_sync,
        page_lock_target_from_env_file,
    )

    return lock_facebook_page_subscription_operation_sync(
        app_key="app_a" if config.app_id == EXPECTED_APP_ID else "retired_app",
        page_ids=(config.page_id,),
        target=page_lock_target_from_env_file(Path(os.environ.get("META_ENV_PATH", str(DEFAULT_ENV_PATH)))),
    )


def _ensure_canonical_python() -> None:
    """Re-exec legacy shell callers through the deployed dependency runtime."""

    script_path = Path(__file__).resolve()
    canonical_python = script_path.parents[1] / "venv" / "bin" / "python"
    if not canonical_python.is_file():
        return
    if Path(sys.executable).resolve() == canonical_python.resolve():
        return
    os.execv(
        str(canonical_python),
        [str(canonical_python), str(script_path), *sys.argv[1:]],
    )
    raise AssertionError("unreachable")


@dataclass(frozen=True)
class MetaConfig:
    app_id: str
    page_id: str
    instagram_id: str
    graph_version: str
    page_token: str


def load_config(path: Path, *, expected_app_id: str = EXPECTED_APP_ID) -> MetaConfig:
    """Read only the required values from the root-owned production env file."""

    if expected_app_id not in ALLOWED_APP_IDS:
        raise MetaSubscriptionError("Refusing an app outside the exact cutover allowlist")
    if (
        expected_app_id == RETIRED_APP_ID
        and (os.getenv("META_RETIRED_APP_SUBSCRIPTION_CONFIRM") or "").strip() != RETIRED_APP_CONFIRMATION
    ):
        raise MetaSubscriptionError("Retired-app subscription mode requires explicit confirmation")

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
    if values["META_APP_ID"] != expected_app_id:
        raise MetaSubscriptionError("Refusing an unexpected Meta App ID")

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
    """Enforce an empty or one-app-only state with the full social field set."""

    app_ids, fields = validate_subscription_payload(payload, current_app_id=current_app_id)
    if expectation == "empty":
        if app_ids:
            raise MetaSubscriptionError("Expected no Page subscriptions")
    elif expectation == "current-only":
        if app_ids != {current_app_id}:
            raise MetaSubscriptionError("Expected the configured app to be the only Page subscription")
        if set(fields) != ALLOWED_PAGE_SUBSCRIPTION_FIELDS:
            raise MetaSubscriptionError("Configured app is missing the required DM/comment webhook fields")
    else:
        raise MetaSubscriptionError("Unknown subscription-state expectation")
    return app_ids, fields


def plan_subscription_reconcile(current_fields: tuple[str, ...] | set[str]) -> tuple[str, ...]:
    """Converge the Page subscription to the approved DM-and-comments fields."""

    current = set(current_fields)
    if not current.issubset(ALLOWED_PAGE_SUBSCRIPTION_FIELDS):
        raise MetaSubscriptionError("Configured app has unexpected webhook fields")
    return tuple(sorted(merge_subscription_fields(current, ALLOWED_PAGE_SUBSCRIPTION_FIELDS)))


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
    with _subscription_writer_lock(config):
        before = _status(config)
        app_ids, fields = validate_subscription_payload(before, current_app_id=config.app_id)
        if not app_ids:
            target_fields = plan_subscription_reconcile(set())
        elif app_ids == {config.app_id}:
            target_fields = plan_subscription_reconcile(fields)
            if fields == target_fields:
                if not allow_present:
                    raise MetaSubscriptionError("Configured app is already subscribed")
                _print_state(app_ids, fields, config)
                print("[meta-subscription] subscribe_noop=true")
                return
        else:
            raise MetaSubscriptionError("Expected no other Page subscriptions")

        result = _request_json(
            config,
            method="POST",
            form={"subscribed_fields": ",".join(target_fields)},
        )
        if result.get("success") is not True:
            raise MetaSubscriptionError("Meta did not confirm the Page subscription")
        app_ids, fields = validate_state(_status(config), current_app_id=config.app_id, expectation="current-only")
        if fields != target_fields:
            raise MetaSubscriptionError("Meta returned unexpected fields after Page subscription reconcile")
        _print_state(app_ids, fields, config)
        print("[meta-subscription] subscribed=true")


def unsubscribe(config: MetaConfig, *, allow_absent: bool) -> None:
    with _subscription_writer_lock(config):
        before = _status(config)
        app_ids, fields = validate_subscription_payload(before, current_app_id=config.app_id)
        if not app_ids:
            if not allow_absent:
                raise MetaSubscriptionError("Configured app is not subscribed")
            print("[meta-subscription] unsubscribe_noop=true")
            return
        if app_ids != {config.app_id}:
            raise MetaSubscriptionError("Expected the configured app to be the only Page subscription")
        if not set(fields).issubset(ALLOWED_PAGE_SUBSCRIPTION_FIELDS):
            raise MetaSubscriptionError("Configured app has unexpected webhook fields")
        _print_state(app_ids, fields, config)

        result = _request_json(config, method="DELETE")
        if result.get("success") is not True:
            raise MetaSubscriptionError("Meta did not confirm subscription removal")
        validate_state(_status(config), current_app_id=config.app_id, expectation="empty")
        print("[meta-subscription] unsubscribed=true")


def main() -> None:
    _ensure_canonical_python()
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
        "--expected-app-id",
        choices=tuple(sorted(ALLOWED_APP_IDS)),
        default=EXPECTED_APP_ID,
    )
    parser.add_argument(
        "--env-file",
        type=Path,
        default=Path(os.environ.get("META_ENV_PATH", str(DEFAULT_ENV_PATH))),
    )
    args = parser.parse_args()
    config = load_config(args.env_file, expected_app_id=args.expected_app_id)
    if args.command == "status":
        status(config, args.expect)
    elif args.command == "subscribe":
        subscribe(config, allow_present=args.allow_present)
    else:
        unsubscribe(config, allow_absent=args.allow_absent)


if __name__ == "__main__":
    main()
