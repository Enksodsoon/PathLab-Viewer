import logging
from datetime import UTC, datetime, timedelta

import pytest
from wsi_viewer.security import (
    InvalidToken,
    UploadGrant,
    hash_password,
    issue_upload_token,
    normalize_username,
    recovery_code_hash,
    verify_password,
    verify_upload_token,
)


def test_passwords_are_argon2id_hashed() -> None:
    encoded = hash_password("a very long admin password")
    assert encoded.startswith("$argon2id$")
    assert verify_password(encoded, "a very long admin password")
    assert not verify_password(encoded, "wrong password")


@pytest.mark.parametrize(
    ("malformed_hash", "error_name"),
    [
        ("not-an-argon2-hash", "InvalidHashError"),
        ("$argon2id$malformed-private-hash", "VerificationError"),
    ],
)
def test_malformed_argon2_hash_is_a_logged_authentication_failure(
    caplog: pytest.LogCaptureFixture,
    malformed_hash: str,
    error_name: str,
) -> None:
    submitted_password = "private submitted password"

    with caplog.at_level(logging.WARNING, logger="wsi_viewer.security"):
        assert not verify_password(malformed_hash, submitted_password)

    assert error_name in caplog.text
    assert malformed_hash not in caplog.text
    assert submitted_password not in caplog.text


def test_upload_token_is_scoped_and_expires() -> None:
    now = datetime(2026, 7, 19, tzinfo=UTC)
    grant = UploadGrant(slide_id="slide-1", length=4096)
    token = issue_upload_token(grant, "secret", now=now, ttl=timedelta(hours=1))
    assert verify_upload_token(token, "secret", now=now).slide_id == "slide-1"
    with pytest.raises(InvalidToken):
        verify_upload_token(token, "secret", now=now + timedelta(hours=2))


def test_password_policy_has_minimum_and_maximum() -> None:
    with pytest.raises(ValueError, match="at least 12"):
        hash_password("short")
    with pytest.raises(ValueError, match="at most 128"):
        hash_password("x" * 129)


def test_recovery_hash_and_username_normalization_are_deterministic() -> None:
    assert recovery_code_hash("one-time-code") == recovery_code_hash("one-time-code")
    assert recovery_code_hash("one-time-code") != "one-time-code"
    assert len(recovery_code_hash("one-time-code")) == 64
    assert normalize_username("  AdMiN  ") == "admin"
