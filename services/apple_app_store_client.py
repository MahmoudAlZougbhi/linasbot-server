"""App Store Server API credentials + short-lived ES256 JWT client.

LOCKED IAP identity (never print .p8 contents):
  Issuer / Key ID from env; private key path only.
  Env: APPLE_IAP_ISSUER_ID, APPLE_IAP_KEY_ID, APPLE_IAP_PRIVATE_KEY_PATH
  Aliases: APPLE_APP_STORE_ISSUER_ID, APPLE_APP_STORE_KEY_ID,
           APPLE_APP_STORE_PRIVATE_KEY_PATH

Dual-environment lookup: production 404/401 on transaction fetch retries
sandbox. This is Apple's documented migration lookup — not a billing
fallback that invents entitlements.
"""

from __future__ import annotations

import os
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import httpx
import jwt

from services.iap_product_catalog import APPLE_BUNDLE_ID

PROD_BASE = "https://api.storekit.itunes.apple.com"
SANDBOX_BASE = "https://api.storekit-sandbox.itunes.apple.com"

_DEFAULT_ISSUER_ID = "a3b052c7-c0ed-4935-8e2e-4b57946e1f6b"
_DEFAULT_KEY_ID = "8H9SZG552B"
_DEFAULT_KEY_PATH = "~/.linasai-secrets/apple/SubscriptionKey_8H9SZG552B.p8"
_JWT_TTL_SECONDS = 1200  # 20 minutes (Apple max 60)


class AppleIapConfigError(RuntimeError):
    """Missing or unreadable App Store Server API credentials."""


def _env(*names: str, default: str = "") -> str:
    for name in names:
        raw = (os.getenv(name) or "").strip()
        if raw:
            return raw
    return default


def iap_issuer_id() -> str:
    return _env("APPLE_IAP_ISSUER_ID", "APPLE_APP_STORE_ISSUER_ID", default=_DEFAULT_ISSUER_ID)


def iap_key_id() -> str:
    return _env("APPLE_IAP_KEY_ID", "APPLE_APP_STORE_KEY_ID", default=_DEFAULT_KEY_ID)


def iap_private_key_path() -> Path:
    raw = _env(
        "APPLE_IAP_PRIVATE_KEY_PATH",
        "APPLE_APP_STORE_PRIVATE_KEY_PATH",
        default=_DEFAULT_KEY_PATH,
    )
    return Path(raw).expanduser()


def iap_bundle_id() -> str:
    return _env("APPLE_BUNDLE_ID", default=APPLE_BUNDLE_ID) or APPLE_BUNDLE_ID


def iap_credentials_configured() -> bool:
    try:
        path = iap_private_key_path()
        return bool(iap_issuer_id() and iap_key_id() and path.is_file())
    except Exception:
        return False


def _load_private_key_pem() -> str:
    """Read .p8 PEM from disk. Never log the contents."""
    # Prefer shared apple_secrets helper when Sign-In agent lands it.
    try:
        from services import apple_secrets as _as  # type: ignore

        loader = getattr(_as, "load_iap_private_key_pem", None) or getattr(
            _as, "load_subscription_private_key_pem", None
        )
        if callable(loader):
            pem = loader()
            if isinstance(pem, str) and pem.strip():
                return pem
    except Exception:
        pass
    path = iap_private_key_path()
    if not path.is_file():
        raise AppleIapConfigError("Apple IAP private key not found at configured path")
    pem = path.read_text(encoding="utf-8")
    if "PRIVATE KEY" not in pem:
        raise AppleIapConfigError("Apple IAP private key file is not a PEM private key")
    return pem


def generate_app_store_jwt(*, ttl_seconds: int = _JWT_TTL_SECONDS) -> str:
    issuer = iap_issuer_id()
    key_id = iap_key_id()
    if not issuer or not key_id:
        raise AppleIapConfigError("APPLE_IAP_ISSUER_ID / APPLE_IAP_KEY_ID required")
    now = int(time.time())
    payload = {
        "iss": issuer,
        "iat": now,
        "exp": now + max(60, min(int(ttl_seconds), 3600)),
        "aud": "appstoreconnect-v1",
        "bid": iap_bundle_id(),
    }
    return jwt.encode(
        payload,
        _load_private_key_pem(),
        algorithm="ES256",
        headers={"alg": "ES256", "kid": key_id, "typ": "JWT"},
    )


class AppleAppStoreClient:
    """Thin httpx client for App Store Server API."""

    def __init__(self, *, timeout: float = 20.0) -> None:
        self._timeout = timeout

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {generate_app_store_jwt()}",
            "Content-Type": "application/json",
        }

    def _request(
        self,
        method: str,
        path: str,
        *,
        base: str,
        json_body: dict[str, Any] | None = None,
    ) -> httpx.Response:
        url = f"{base.rstrip('/')}{path}"
        with httpx.Client(timeout=self._timeout) as client:
            return client.request(method, url, headers=self._headers(), json=json_body)

    def _get_json(self, path: str, *, base: str) -> dict[str, Any]:
        resp = self._request("GET", path, base=base)
        if resp.status_code >= 400:
            raise httpx.HTTPStatusError(
                f"App Store API {resp.status_code} for {path}",
                request=resp.request,
                response=resp,
            )
        data = resp.json()
        if not isinstance(data, dict):
            raise ValueError("App Store API returned non-object JSON")
        return data

    def get_transaction_info(self, transaction_id: str) -> dict[str, Any]:
        """Fetch transaction info; retry sandbox on production 404/401.

        Apple documents dual-environment lookup during Sandbox→Production
        migration. We never synthesize entitlements from a failed lookup.
        """
        tid = str(transaction_id or "").strip()
        if not tid:
            raise ValueError("transaction_id required")
        path = f"/inApps/v1/transactions/{tid}"
        resp = self._request("GET", path, base=PROD_BASE)
        if resp.status_code in {401, 404}:
            # Documented: production miss may be a sandbox purchase.
            resp = self._request("GET", path, base=SANDBOX_BASE)
            if resp.status_code >= 400:
                raise httpx.HTTPStatusError(
                    f"App Store API {resp.status_code} (sandbox retry) for {path}",
                    request=resp.request,
                    response=resp,
                )
            data = resp.json()
            if isinstance(data, dict):
                data = {**data, "_linas_environment_resolved": "Sandbox"}
            return data if isinstance(data, dict) else {"signedTransactionInfo": data}
        if resp.status_code >= 400:
            raise httpx.HTTPStatusError(
                f"App Store API {resp.status_code} for {path}",
                request=resp.request,
                response=resp,
            )
        data = resp.json()
        if not isinstance(data, dict):
            raise ValueError("App Store API returned non-object JSON")
        return {**data, "_linas_environment_resolved": "Production"}

    def get_all_subscription_statuses(self, original_transaction_id: str) -> dict[str, Any]:
        oid = str(original_transaction_id or "").strip()
        if not oid:
            raise ValueError("original_transaction_id required")
        path = f"/inApps/v1/subscriptions/{oid}"
        try:
            return self._get_json(path, base=PROD_BASE)
        except httpx.HTTPStatusError as exc:
            code = exc.response.status_code if exc.response is not None else 0
            if code not in {401, 404}:
                raise
            return self._get_json(path, base=SANDBOX_BASE)

    def get_notification_history(
        self,
        start_ms: int,
        end_ms: int,
        *,
        notification_type: str | None = None,
        pagination_token: str | None = None,
        only_failures: bool = False,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {
            "startDate": int(start_ms),
            "endDate": int(end_ms),
            "onlyFailures": bool(only_failures),
        }
        if notification_type:
            body["notificationType"] = notification_type
        if pagination_token:
            body["paginationToken"] = pagination_token
        resp = self._request("POST", "/inApps/v1/notifications/history", base=PROD_BASE, json_body=body)
        if resp.status_code in {401, 404}:
            resp = self._request("POST", "/inApps/v1/notifications/history", base=SANDBOX_BASE, json_body=body)
        if resp.status_code >= 400:
            raise httpx.HTTPStatusError(
                f"App Store API {resp.status_code} for notification history",
                request=resp.request,
                response=resp,
            )
        data = resp.json()
        if not isinstance(data, dict):
            raise ValueError("notification history returned non-object JSON")
        return data

    def iter_notification_history(
        self,
        start_ms: int,
        end_ms: int,
        *,
        notification_type: str | None = None,
        only_failures: bool = False,
        max_pages: int = 100,
    ) -> Iterator[dict[str, Any]]:
        """Yield notification-history pages until exhausted or ``max_pages``."""
        token: str | None = None
        limit = max(1, int(max_pages))
        for _ in range(limit):
            page = self.get_notification_history(
                start_ms,
                end_ms,
                notification_type=notification_type,
                pagination_token=token,
                only_failures=only_failures,
            )
            yield page
            if not page.get("hasMore"):
                return
            next_token = page.get("paginationToken")
            if not isinstance(next_token, str) or not next_token.strip():
                return
            token = next_token

    def send_consumption_info(self, transaction_id: str, body: dict[str, Any]) -> dict[str, Any]:
        """Respond to CONSUMPTION_REQUEST when refund consumption data is permitted."""
        tid = str(transaction_id or "").strip()
        if not tid:
            raise ValueError("transaction_id required")
        if not isinstance(body, dict) or not body:
            raise ValueError("consumption body required")
        path = f"/inApps/v1/transactions/consumption/{tid}"
        resp = self._request("PUT", path, base=PROD_BASE, json_body=body)
        if resp.status_code in {401, 404}:
            resp = self._request("PUT", path, base=SANDBOX_BASE, json_body=body)
        if resp.status_code >= 400:
            raise httpx.HTTPStatusError(
                f"App Store API {resp.status_code} for consumption info",
                request=resp.request,
                response=resp,
            )
        if not resp.content:
            return {"ok": True, "status_code": resp.status_code}
        data = resp.json()
        return data if isinstance(data, dict) else {"ok": True, "raw": data}


apple_app_store_client = AppleAppStoreClient()
