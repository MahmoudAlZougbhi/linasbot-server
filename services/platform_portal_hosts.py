"""Canonical hosts for the platform-owner control portal.

Marketing stays on linasaibot.com. Owner control is portal.linasaibot.com
(and www.portal.linasaibot.com). Workspace admins must not get a session there.
"""

from __future__ import annotations

from typing import Iterable

MARKETING_HOSTS: frozenset[str] = frozenset({"linasaibot.com", "www.linasaibot.com"})
PLATFORM_PORTAL_HOSTS: frozenset[str] = frozenset(
    {"portal.linasaibot.com", "www.portal.linasaibot.com"}
)
EMAIL_LINK_HOSTS: frozenset[str] = MARKETING_HOSTS | PLATFORM_PORTAL_HOSTS
PLATFORM_OWNER_TENANT_ID = "platform"
PORTAL_LOGIN_FORBIDDEN = "This portal is for the platform owner only."


def hostname_from_header(host_header: str | None) -> str:
    raw = (host_header or "").split(",")[0].strip().lower()
    if raw.startswith("[") and "]" in raw:
        return raw[1 : raw.index("]")]
    if ":" in raw:
        return raw.rsplit(":", 1)[0]
    return raw


def is_platform_portal_host(host_header: str | None) -> bool:
    return hostname_from_header(host_header) in PLATFORM_PORTAL_HOSTS


def portal_login_error(host_header: str | None, role: str | None) -> str | None:
    if not is_platform_portal_host(host_header):
        return None
    if (role or "").strip().lower() == "platform_owner":
        return None
    return PORTAL_LOGIN_FORBIDDEN


def https_origins(hosts: Iterable[str]) -> list[str]:
    return [f"https://{host}" for host in hosts]


def cors_public_origins(*, production: bool) -> list[str]:
    origins = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:8003",
        "http://127.0.0.1:8003",
        *https_origins(MARKETING_HOSTS),
        *https_origins(PLATFORM_PORTAL_HOSTS),
    ]
    if not production:
        origins.extend(f"http://{host}" for host in MARKETING_HOSTS)
        origins.extend(f"http://{host}" for host in PLATFORM_PORTAL_HOSTS)
    return origins
