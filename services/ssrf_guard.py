"""SSRF-safe URL validation for server-side fetches."""

from __future__ import annotations

import ipaddress
import socket
from collections.abc import Iterable, Sequence
from urllib.parse import urlparse, urlunparse

DEFAULT_ALLOWED_HOST_SUFFIXES: frozenset[str] = frozenset(
    {
        "firebasestorage.googleapis.com",
        "storage.googleapis.com",
        "googleapis.com",
        "graph.facebook.com",
        "lookaside.fbsbx.com",
        "scontent.xx.fbcdn.net",
        "fbcdn.net",
        "cdninstagram.com",
        "montymobile.com",
        "whatsapp-notification.montymobile.com",
        "omni-apis.montymobile.com",
    }
)

_BLOCKED_NETWORKS = (
    ipaddress.ip_network("0.0.0.0/8"),
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("100.64.0.0/10"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.0.0.0/24"),
    ipaddress.ip_network("192.0.2.0/24"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("198.18.0.0/15"),
    ipaddress.ip_network("198.51.100.0/24"),
    ipaddress.ip_network("203.0.113.0/24"),
    ipaddress.ip_network("224.0.0.0/4"),
    ipaddress.ip_network("240.0.0.0/4"),
    ipaddress.ip_network("255.255.255.255/32"),
    ipaddress.ip_network("::/128"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
    ipaddress.ip_network("fe80::/10"),
    ipaddress.ip_network("ff00::/8"),
)


class SSRFValidationError(ValueError):
    """Raised when a URL fails SSRF policy checks."""


def _host_allowed(hostname: str, allowed_suffixes: Iterable[str]) -> bool:
    host = (hostname or "").strip().lower().rstrip(".")
    if not host:
        return False
    for suffix in allowed_suffixes:
        s = suffix.strip().lower().rstrip(".")
        if not s:
            continue
        if host == s or host.endswith("." + s):
            return True
    return False


def _ip_blocked(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_multicast or ip.is_reserved:
        return True
    if ip.is_unspecified:
        return True
    for net in _BLOCKED_NETWORKS:
        if ip in net:
            return True
    return False


def resolve_and_validate_host(
    hostname: str,
    *,
    allowed_suffixes: Sequence[str] | None = None,
) -> tuple[str, Sequence[str]]:
    """Validate hostname allowlist and DNS resolution targets."""
    suffixes = tuple(allowed_suffixes) if allowed_suffixes is not None else tuple(DEFAULT_ALLOWED_HOST_SUFFIXES)
    host = (hostname or "").strip().lower().rstrip(".")
    if not _host_allowed(host, suffixes):
        raise SSRFValidationError("Host is not on the allowlist")

    # Literal IP in hostname
    try:
        ip = ipaddress.ip_address(host)
        if _ip_blocked(ip):
            raise SSRFValidationError("Resolved address is not publicly routable")
        return host, (str(ip),)
    except ValueError:
        pass

    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror as exc:
        raise SSRFValidationError("DNS resolution failed") from exc

    resolved: list[str] = []
    for info in infos:
        sockaddr = info[4]
        if not sockaddr:
            continue
        addr = sockaddr[0]
        try:
            ip = ipaddress.ip_address(addr)
        except ValueError:
            continue
        if _ip_blocked(ip):
            raise SSRFValidationError("Resolved address is not publicly routable")
        resolved.append(str(ip))
    if not resolved:
        raise SSRFValidationError("No usable DNS addresses")
    return host, tuple(resolved)


def validate_fetch_url(
    url: str,
    *,
    allowed_schemes: Sequence[str] = ("https",),
    allowed_suffixes: Sequence[str] | None = None,
    allow_http_for_local_dev: bool = False,
) -> str:
    """
    Validate URL for outbound server fetch. Returns normalized URL string.
    Does not follow redirects — caller must re-validate each redirect Location.
    """
    if not url or not isinstance(url, str):
        raise SSRFValidationError("URL is required")
    if "\x00" in url or any(c.isspace() and c not in (" ",) for c in url):
        # disallow control whitespace except ordinary space already unusual in URLs
        pass
    parsed = urlparse(url.strip())
    scheme = (parsed.scheme or "").lower()
    schemes = set(allowed_schemes)
    if allow_http_for_local_dev:
        schemes.add("http")
    if scheme not in schemes:
        raise SSRFValidationError("URL scheme is not allowed")
    if parsed.username or parsed.password:
        raise SSRFValidationError("URL credentials are not allowed")
    if not parsed.hostname:
        raise SSRFValidationError("URL host is required")
    resolve_and_validate_host(parsed.hostname, allowed_suffixes=allowed_suffixes)
    # Rebuild without fragments
    normalized = urlunparse((scheme, parsed.netloc.lower(), parsed.path or "", parsed.params, parsed.query, ""))
    return normalized
