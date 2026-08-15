"""Website domain normalization and origin matching."""

from __future__ import annotations

from urllib.parse import urlparse


def normalize_site_url(raw: str) -> str:
    text = (raw or "").strip()
    if not text:
        return ""
    if "://" not in text:
        text = f"https://{text}"
    parsed = urlparse(text)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("invalid_site_url")
    return f"{parsed.scheme}://{parsed.netloc}".rstrip("/")


def _host_variants(netloc: str) -> set[str]:
    host = (netloc or "").strip().lower()
    if not host:
        return set()
    variants = {host}
    if host.startswith("www."):
        variants.add(host[4:])
    else:
        variants.add(f"www.{host}")
    return variants


def origin_allowed_for_site(site_url: str, origin: str | None) -> bool:
    if not site_url or not origin:
        return False
    try:
        allowed = urlparse(site_url.strip())
        parsed = urlparse(origin.strip())
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            return False
        if allowed.scheme not in {"http", "https"} or not allowed.netloc:
            return False
        allowed_hosts = _host_variants(allowed.netloc)
        origin_hosts = _host_variants(parsed.netloc)
        return bool(allowed_hosts & origin_hosts)
    except Exception:
        return False
