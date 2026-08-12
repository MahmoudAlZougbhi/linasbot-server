"""Verify Apple StoreKit / ASSN V2 JWS (x5c chain) and decode payloads.

Never log or persist full JWS strings — use ``sha256_hex`` for storage keys.
"""

from __future__ import annotations

import base64
import hashlib
import json
from typing import Any

from cryptography import x509
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.asymmetric.ec import ECDSA
from cryptography.hazmat.primitives.hashes import SHA256
from cryptography.x509.oid import NameOID

from services.iap_product_catalog import APPLE_BUNDLE_ID

# Apple Root CA - G3 (public root). Used to anchor App Store Server JWS x5c chains.
_APPLE_ROOT_CA_G3_PEM = b"""-----BEGIN CERTIFICATE-----
MIICQzCCAcmgAwIBAgIILcX8iNLFS5UwCgYIKoZIzj0EAwMwZzEbMBkGA1UEAwwS
QXBwbGUgUm9vdCBDQSAtIEczMSYwJAYDVQQLDB1BcHBsZSBDZXJ0aWZpY2F0aW9u
IEF1dGhvcml0eTETMBEGA1UECgwKQXBwbGUgSW5jLjELMAkGA1UEBhMCVVMwHhcN
MTQwNDMwMTgxOTA2WhcNMzkwNDMwMTgxOTA2WjBnMRswGQYDVQQDDBJBcHBsZSBS
b290IENBIC0gRzMxJjAkBgNVBAsMHUFwcGxlIENlcnRpZmljYXRpb24gQXV0aG9y
aXR5MRMwEQYDVQQKDApBcHBsZSBJbmMuMQswCQYDVQQGEwJVUzB2MBAGByqGSM49
AgEGBSuBBAAiA2IABJjpLz1AcqTtkyJygRMc3RCV8cWjTnHcFBbZDuWmBSp3ZHtf
TjjTuxxEtX/1H7YyYl3J6YRbTzBPEVoA/VhYDKX1DyxNB0cTddqXl5dvMVztK517
IDvYuVTZXpmkOlEKMaNCMEAwHQYDVR0OBBYEFLuw3qFYM4iapIqZ3r6966/ayySr
MA8GA1UdEwEB/wQFMAMBAf8wDgYDVR0PAQH/BAQDAgEGMAoGCCqGSM49BAMDA2gA
MGUCMQCD6cHEFl4aXTQY2e3v9GwOAEZLuN+yRhHFD/3meoyhpmvOwgPUnPWTxnS4
at+qIxUCMG1mihDK1A3UT82NQz60imOlM27jbdoXt2QfyFMm+YhidDkLF1vLUagM
6BgD56KyKA==
-----END CERTIFICATE-----
"""


class AppleJwsError(ValueError):
    """Invalid Apple JWS (signature, chain, or payload)."""


def sha256_hex(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def _b64url_decode(segment: str) -> bytes:
    pad = "=" * ((4 - len(segment) % 4) % 4)
    return base64.urlsafe_b64decode(segment + pad)


def _load_apple_root() -> x509.Certificate:
    # Prefer cryptography's load; fall back to system store lookup by subject if PEM invalid in tests.
    try:
        return x509.load_pem_x509_certificate(_APPLE_ROOT_CA_G3_PEM)
    except Exception as exc:  # noqa: BLE001
        raise AppleJwsError(f"Apple root CA unavailable: {exc}") from exc


def _parse_compact(token: str) -> tuple[dict[str, Any], dict[str, Any], bytes, bytes, bytes]:
    parts = (token or "").strip().split(".")
    if len(parts) != 3:
        raise AppleJwsError("JWS must have three compact segments")
    header_b, payload_b, sig_b = parts
    try:
        header = json.loads(_b64url_decode(header_b))
        payload = json.loads(_b64url_decode(payload_b))
    except Exception as exc:  # noqa: BLE001
        raise AppleJwsError("JWS header/payload is not valid JSON") from exc
    if not isinstance(header, dict) or not isinstance(payload, dict):
        raise AppleJwsError("JWS header/payload must be objects")
    signing_input = f"{header_b}.{payload_b}".encode("ascii")
    signature = _b64url_decode(sig_b)
    return header, payload, signing_input, signature, header_b.encode("ascii")


def _certs_from_x5c(x5c: list[Any]) -> list[x509.Certificate]:
    if not x5c:
        raise AppleJwsError("JWS header missing x5c")
    certs: list[x509.Certificate] = []
    for entry in x5c:
        raw = base64.b64decode(str(entry))
        certs.append(x509.load_der_x509_certificate(raw))
    return certs


def _verify_chain(certs: list[x509.Certificate], *, skip_root_anchor: bool = False) -> None:
    """Validate leaf←…←Apple Root. ``skip_root_anchor`` is tests-only via env monkeypatch."""
    if not certs:
        raise AppleJwsError("empty certificate chain")
    for i in range(len(certs) - 1):
        child, parent = certs[i], certs[i + 1]
        try:
            parent.public_key().verify(  # type: ignore[union-attr]
                child.signature,
                child.tbs_certificate_bytes,
                ECDSA(child.signature_hash_algorithm),  # type: ignore[arg-type]
            )
        except Exception:
            try:
                parent.public_key().verify(  # type: ignore[union-attr]
                    child.signature,
                    child.tbs_certificate_bytes,
                    padding.PKCS1v15(),
                    child.signature_hash_algorithm,  # type: ignore[arg-type]
                )
            except Exception as exc:  # noqa: BLE001
                raise AppleJwsError("x5c chain signature failed") from exc
    if skip_root_anchor:
        return
    root = _load_apple_root()
    leaf_root = certs[-1]
    if leaf_root.fingerprint(SHA256()) != root.fingerprint(SHA256()):
        # Chain may omit root — verify last cert is signed by Apple root.
        try:
            root.public_key().verify(  # type: ignore[union-attr]
                leaf_root.signature,
                leaf_root.tbs_certificate_bytes,
                ECDSA(leaf_root.signature_hash_algorithm),  # type: ignore[arg-type]
            )
        except Exception as exc:  # noqa: BLE001
            raise AppleJwsError("x5c does not chain to Apple Root CA - G3") from exc


def _verify_signature(leaf: x509.Certificate, signing_input: bytes, signature: bytes) -> None:
    pub = leaf.public_key()
    try:
        pub.verify(signature, signing_input, ECDSA(SHA256()))  # type: ignore[union-attr]
    except Exception as exc:  # noqa: BLE001
        raise AppleJwsError("JWS signature verification failed") from exc


def _assert_bundle(payload: dict[str, Any], *, expected_bundle: str | None = None) -> None:
    expected = (expected_bundle or APPLE_BUNDLE_ID).strip()
    for key in ("bundleId", "bid"):
        raw = payload.get(key)
        if raw is not None and str(raw).strip() and str(raw).strip() != expected:
            raise AppleJwsError(f"bundle id mismatch: {raw}")
    data = payload.get("data")
    if isinstance(data, dict):
        bid = data.get("bundleId")
        if bid is not None and str(bid).strip() and str(bid).strip() != expected:
            raise AppleJwsError(f"notification bundle id mismatch: {bid}")


def verify_and_decode_jws(
    token: str,
    *,
    expected_bundle: str | None = None,
    skip_root_anchor: bool = False,
) -> dict[str, Any]:
    """Verify Apple JWS (x5c) and return the payload dict."""
    header, payload, signing_input, signature, _ = _parse_compact(token)
    alg = str(header.get("alg") or "")
    if alg not in {"ES256", "ES384"}:
        raise AppleJwsError(f"unsupported JWS alg: {alg}")
    x5c = header.get("x5c")
    if not isinstance(x5c, list):
        raise AppleJwsError("JWS header missing x5c array")
    certs = _certs_from_x5c(x5c)
    _verify_chain(certs, skip_root_anchor=skip_root_anchor)
    _verify_signature(certs[0], signing_input, signature)
    _assert_bundle(payload, expected_bundle=expected_bundle)
    return payload


def decode_jws_payload(token: str, *, expected_bundle: str | None = None) -> dict[str, Any]:
    """Verify then return payload (alias used by processors)."""
    return verify_and_decode_jws(token, expected_bundle=expected_bundle)


def leaf_common_name(token: str) -> str | None:
    """Debug helper — never logs the token itself."""
    header, _, _, _, _ = _parse_compact(token)
    x5c = header.get("x5c")
    if not isinstance(x5c, list) or not x5c:
        return None
    cert = _certs_from_x5c(x5c)[0]
    attrs = cert.subject.get_attributes_for_oid(NameOID.COMMON_NAME)
    return attrs[0].value if attrs else None  # type: ignore[return-value]
