"""Apple JWS certificate notBefore/notAfter validity checks."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID

from services.apple_jws import (
    AppleJwsError,
    _assert_cert_validity,
    _load_apple_root,
    _verify_chain,
)


def _forge_leaf(*, not_before: datetime, not_after: datetime) -> x509.Certificate:
    key = ec.generate_private_key(ec.SECP256R1())
    subject = issuer = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "linas-test-leaf")])
    return (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(not_before)
        .not_valid_after(not_after)
        .sign(key, hashes.SHA256())
    )


def test_assert_cert_validity_accepts_current_window() -> None:
    now = datetime(2020, 6, 1, tzinfo=timezone.utc)
    cert = _forge_leaf(
        not_before=now - timedelta(days=1),
        not_after=now + timedelta(days=1),
    )
    _assert_cert_validity(cert, now)


def test_assert_cert_validity_rejects_not_yet_valid() -> None:
    now = datetime(2020, 6, 1, tzinfo=timezone.utc)
    cert = _forge_leaf(
        not_before=now + timedelta(days=1),
        not_after=now + timedelta(days=30),
    )
    with pytest.raises(AppleJwsError, match="certificate not yet valid"):
        _assert_cert_validity(cert, now)


def test_assert_cert_validity_rejects_expired() -> None:
    now = datetime(2020, 6, 1, tzinfo=timezone.utc)
    cert = _forge_leaf(
        not_before=now - timedelta(days=30),
        not_after=now - timedelta(days=1),
    )
    with pytest.raises(AppleJwsError, match="certificate expired"):
        _assert_cert_validity(cert, now)


def test_verify_chain_rejects_expired_leaf() -> None:
    now = datetime(2020, 6, 1, tzinfo=timezone.utc)
    expired = _forge_leaf(
        not_before=now - timedelta(days=30),
        not_after=now - timedelta(days=1),
    )
    with pytest.raises(AppleJwsError, match="certificate expired"):
        _verify_chain([expired], skip_root_anchor=True, now=now)


def test_verify_chain_rejects_not_yet_valid_leaf() -> None:
    now = datetime(2020, 6, 1, tzinfo=timezone.utc)
    future = _forge_leaf(
        not_before=now + timedelta(days=1),
        not_after=now + timedelta(days=30),
    )
    with pytest.raises(AppleJwsError, match="certificate not yet valid"):
        _verify_chain([future], skip_root_anchor=True, now=now)


def test_apple_root_validity_window_checked() -> None:
    root = _load_apple_root()
    before = root.not_valid_before_utc - timedelta(days=1)
    after = root.not_valid_after_utc + timedelta(days=1)
    with pytest.raises(AppleJwsError, match="certificate not yet valid"):
        _assert_cert_validity(root, before)
    with pytest.raises(AppleJwsError, match="certificate expired"):
        _assert_cert_validity(root, after)
    _assert_cert_validity(root, datetime(2020, 1, 1, tzinfo=timezone.utc))
