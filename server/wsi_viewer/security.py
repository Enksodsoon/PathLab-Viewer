import secrets
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from argon2.low_level import Type
from itsdangerous import BadSignature, URLSafeSerializer

_PASSWORD_HASHER = PasswordHasher(type=Type.ID)


class InvalidToken(ValueError):
    pass


@dataclass(frozen=True)
class UploadGrant:
    slide_id: str
    length: int


def hash_password(password: str) -> str:
    if len(password) < 12:
        raise ValueError("Admin password must contain at least 12 characters")
    return _PASSWORD_HASHER.hash(password)


def verify_password(encoded: str, password: str) -> bool:
    try:
        return _PASSWORD_HASHER.verify(encoded, password)
    except VerifyMismatchError:
        return False


def random_token(bytes_count: int = 32) -> str:
    return secrets.token_urlsafe(bytes_count)


def issue_upload_token(
    grant: UploadGrant,
    secret: str,
    *,
    now: datetime | None = None,
    ttl: timedelta = timedelta(hours=1),
) -> str:
    issued_at = now or datetime.now(UTC)
    payload = asdict(grant) | {"expires_at": int((issued_at + ttl).timestamp())}
    return URLSafeSerializer(secret, salt="pathlab-upload-v1").dumps(payload)


def verify_upload_token(
    token: str,
    secret: str,
    *,
    now: datetime | None = None,
    allow_expired: bool = False,
) -> UploadGrant:
    try:
        payload = URLSafeSerializer(secret, salt="pathlab-upload-v1").loads(token)
        if not isinstance(payload, dict):
            raise InvalidToken("Malformed upload token")
        current = now or datetime.now(UTC)
        if not allow_expired and int(payload["expires_at"]) < int(current.timestamp()):
            raise InvalidToken("Upload token expired")
        return UploadGrant(slide_id=str(payload["slide_id"]), length=int(payload["length"]))
    except (BadSignature, KeyError, TypeError, ValueError) as error:
        if isinstance(error, InvalidToken):
            raise
        raise InvalidToken("Invalid upload token") from error
