"""6-digit OTP is stored alongside the existing email-link token (same endpoints)."""

from __future__ import annotations

from pathlib import Path

from services.auth_email_tokens import AuthEmailTokenService, otp_secret


def test_email_verify_otp_roundtrip(tmp_path: Path) -> None:
    svc = AuthEmailTokenService(store_dir=tmp_path / "tokens")
    issued = svc.issue(
        purpose="email_verify",
        user_id="u2",
        email="b@example.com",
        tenant_id="acme",
    )
    assert issued.otp.isdigit()
    assert len(issued.otp) == 6
    assert svc.peek(issued, "email_verify") is not None
    assert svc.consume_link_or_otp(issued.otp, "email_verify", email="b@example.com") is not None
    assert svc.consume(issued, "email_verify") is None
    assert svc.consume(otp_secret("email_verify", "b@example.com", issued.otp), "email_verify") is None


def test_password_reset_otp_does_not_cross_accounts(tmp_path: Path) -> None:
    svc = AuthEmailTokenService(store_dir=tmp_path / "tokens")
    issued = svc.issue(
        purpose="password_reset",
        user_id="u1",
        email="a@example.com",
        tenant_id="acme",
        ttl_seconds=600,
    )
    assert svc.consume_link_or_otp(issued.otp, "password_reset", email="other@example.com") is None
    record = svc.consume_link_or_otp(issued.otp, "password_reset", email="a@example.com")
    assert record is not None
    assert record.user_id == "u1"
    assert svc.consume(issued, "password_reset") is None


def test_email_change_has_no_otp(tmp_path: Path) -> None:
    svc = AuthEmailTokenService(store_dir=tmp_path / "tokens")
    issued = svc.issue(
        purpose="email_change",
        user_id="u9",
        email="new@example.com",
        tenant_id="acme",
        meta={"previous_email": "old@example.com"},
    )
    assert issued.otp == ""
    assert svc.consume(issued, "email_change") is not None
