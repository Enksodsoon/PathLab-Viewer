from datetime import UTC, datetime, timedelta

import pytest
from wsi_viewer.security import (
    InvalidToken,
    UploadGrant,
    hash_password,
    issue_upload_token,
    verify_password,
    verify_upload_token,
)


def test_passwords_are_argon2id_hashed() -> None:
    encoded = hash_password("a very long admin password")
    assert encoded.startswith("$argon2id$")
    assert verify_password(encoded, "a very long admin password")
    assert not verify_password(encoded, "wrong password")


def test_upload_token_is_scoped_and_expires() -> None:
    now = datetime(2026, 7, 19, tzinfo=UTC)
    grant = UploadGrant(slide_id="slide-1", length=4096)
    token = issue_upload_token(grant, "secret", now=now, ttl=timedelta(hours=1))
    assert verify_upload_token(token, "secret", now=now).slide_id == "slide-1"
    with pytest.raises(InvalidToken):
        verify_upload_token(token, "secret", now=now + timedelta(hours=2))
