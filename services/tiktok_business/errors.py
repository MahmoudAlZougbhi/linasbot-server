"""TikTok Business errors — fail closed, never hide bugs behind fallbacks."""

from __future__ import annotations


class TikTokBusinessError(Exception):
    code = "TIKTOK_ERROR"
    http_status = 400

    def __init__(self, message: str, *, code: str | None = None, http_status: int | None = None) -> None:
        super().__init__(message)
        self.message = message
        if code:
            self.code = code
        if http_status is not None:
            self.http_status = http_status


class TikTokNotConfiguredError(TikTokBusinessError):
    code = "TIKTOK_NOT_CONFIGURED"
    http_status = 503


class TikTokPlanDeniedError(TikTokBusinessError):
    code = "TIKTOK_PLAN_DENIED"
    http_status = 403


class TikTokOAuthStateError(TikTokBusinessError):
    code = "TIKTOK_OAUTH_STATE_INVALID"
    http_status = 400


class TikTokApiError(TikTokBusinessError):
    code = "TIKTOK_API_ERROR"
    http_status = 502

    def __init__(
        self,
        message: str,
        *,
        tiktok_code: int | None = None,
        request_id: str = "",
        retryable: bool = False,
        http_status: int = 502,
    ) -> None:
        super().__init__(message, http_status=http_status)
        self.tiktok_code = tiktok_code
        self.request_id = request_id
        self.retryable = retryable


class TikTokPermissionPendingError(TikTokBusinessError):
    code = "TIKTOK_PERMISSION_PENDING"
    http_status = 409


class TikTokCapabilityGatedError(TikTokBusinessError):
    code = "TIKTOK_CAPABILITY_GATED"
    http_status = 409
