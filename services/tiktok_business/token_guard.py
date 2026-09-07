"""Refuse the wrong TikTok token type before any Marketing API HTTP call."""

from __future__ import annotations

from services.tiktok_business.capabilities import TOKEN_KIND_ADVERTISER, is_advertiser_only_path
from services.tiktok_business.errors import TikTokBusinessError


def assert_advertiser_token(*, path: str, token_kind: str) -> None:
    if not is_advertiser_only_path(path):
        return
    if str(token_kind or "").strip() != TOKEN_KIND_ADVERTISER:
        raise TikTokBusinessError(
            "Refusing to send an account-holder token to a Marketing API endpoint.",
            code="token_type_mismatch",
            http_status=400,
        )


def assert_not_account_token_for_enhanced(token_kind: str) -> None:
    assert_advertiser_token(path="/identity/get/", token_kind=token_kind)
