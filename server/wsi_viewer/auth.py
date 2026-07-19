import hashlib
import hmac
from datetime import UTC, datetime, timedelta
from typing import Any, cast

from sqlalchemy import delete, select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.orm import Session as OrmSession

from .models import AuditEvent, PasswordRecoveryAttempt, PasswordRecoveryCode, Session, User
from .security import (
    hash_password,
    normalize_username,
    random_token,
    recovery_code_hash,
    validate_password,
    verify_password,
)

RECOVERY_TTL = timedelta(minutes=15)
ATTEMPT_WINDOW = timedelta(minutes=5)
ATTEMPT_RETENTION = timedelta(hours=24)
MAX_RECOVERY_FAILURES = 5


class InvalidCurrentPassword(ValueError):
    pass


class PasswordReuse(ValueError):
    pass


class InvalidRecoveryCode(ValueError):
    pass


class RecoveryThrottled(ValueError):
    pass


def _now(value: datetime | None) -> datetime:
    current = value or datetime.now(UTC)
    return current.replace(tzinfo=None)


def _client_key(username: str, client_address: str) -> str:
    material = f"{normalize_username(username)}\0{client_address}".encode()
    return hashlib.sha256(material).hexdigest()


def invalidate_recovery_codes(database: OrmSession, user_id: str, now: datetime) -> None:
    database.execute(
        update(PasswordRecoveryCode)
        .where(
            PasswordRecoveryCode.user_id == user_id,
            PasswordRecoveryCode.consumed_at.is_(None),
            PasswordRecoveryCode.invalidated_at.is_(None),
        )
        .values(invalidated_at=now)
    )


def revoke_sessions(database: OrmSession, user_id: str) -> None:
    database.execute(delete(Session).where(Session.user_id == user_id))


def issue_recovery_code(
    database: OrmSession, user: User, now: datetime | None = None
) -> str:
    issued_at = _now(now)
    database.execute(
        delete(PasswordRecoveryAttempt).where(
            PasswordRecoveryAttempt.attempted_at < issued_at - ATTEMPT_RETENTION
        )
    )
    invalidate_recovery_codes(database, user.id, issued_at)
    code = random_token(32)
    database.add(
        PasswordRecoveryCode(
            user_id=user.id,
            code_hash=recovery_code_hash(code),
            expires_at=issued_at + RECOVERY_TTL,
            created_at=issued_at,
        )
    )
    database.add(AuditEvent(action="auth.recovery_code_issued", target_id=user.id))
    return code


def change_password(
    database: OrmSession,
    user: User,
    current_password: str,
    new_password: str,
    now: datetime | None = None,
) -> None:
    changed_at = _now(now)
    if not verify_password(user.password_hash, current_password):
        raise InvalidCurrentPassword
    if verify_password(user.password_hash, new_password):
        raise PasswordReuse
    user.password_hash = hash_password(new_password)
    revoke_sessions(database, user.id)
    invalidate_recovery_codes(database, user.id, changed_at)
    database.add(
        AuditEvent(
            actor_user_id=user.id,
            action="auth.password_changed",
            target_id=user.id,
        )
    )
    database.commit()


def reset_password_by_cli(
    database: OrmSession,
    user: User,
    password: str,
    now: datetime | None = None,
) -> None:
    reset_at = _now(now)
    user.password_hash = hash_password(password)
    revoke_sessions(database, user.id)
    invalidate_recovery_codes(database, user.id, reset_at)
    database.add(AuditEvent(action="auth.password_reset_by_cli", target_id=user.id))
    database.commit()


def recover_password(
    database: OrmSession,
    username: str,
    code: str,
    new_password: str,
    client_address: str,
    now: datetime | None = None,
) -> None:
    attempted_at = _now(now)
    key = _client_key(username, client_address)
    database.execute(
        delete(PasswordRecoveryAttempt).where(
            PasswordRecoveryAttempt.attempted_at < attempted_at - ATTEMPT_RETENTION
        )
    )
    recent = list(
        database.scalars(
            select(PasswordRecoveryAttempt.attempted_at)
            .where(PasswordRecoveryAttempt.client_key_hash == key)
            .order_by(PasswordRecoveryAttempt.attempted_at.desc())
            .limit(MAX_RECOVERY_FAILURES)
        )
    )
    if len(recent) == MAX_RECOVERY_FAILURES and recent[0] - recent[-1] <= ATTEMPT_WINDOW:
        if attempted_at < recent[0] + ATTEMPT_WINDOW:
            database.commit()
            raise RecoveryThrottled
        database.execute(
            delete(PasswordRecoveryAttempt).where(
                PasswordRecoveryAttempt.client_key_hash == key
            )
        )
    normalized_username = normalize_username(username)
    user = next(
        (
            item
            for item in database.scalars(select(User))
            if normalize_username(item.username) == normalized_username
        ),
        None,
    )
    submitted_hash = recovery_code_hash(code)
    stored = (
        None
        if user is None
        else database.scalar(
            select(PasswordRecoveryCode)
            .where(
                PasswordRecoveryCode.user_id == user.id,
                PasswordRecoveryCode.consumed_at.is_(None),
                PasswordRecoveryCode.invalidated_at.is_(None),
            )
            .order_by(PasswordRecoveryCode.created_at.desc())
        )
    )
    valid = (
        stored is not None
        and stored.expires_at >= attempted_at
        and hmac.compare_digest(stored.code_hash, submitted_hash)
    )
    if not valid or user is None or stored is None:
        database.add(PasswordRecoveryAttempt(client_key_hash=key, attempted_at=attempted_at))
        database.add(
            AuditEvent(
                action="auth.password_recovery_failed",
                detail={"reason": "invalid_or_expired"},
            )
        )
        database.commit()
        raise InvalidRecoveryCode
    try:
        validate_password(new_password)
    except ValueError:
        database.rollback()
        raise
    result = cast(
        CursorResult[Any],
        database.execute(
            update(PasswordRecoveryCode)
            .where(
                PasswordRecoveryCode.id == stored.id,
                PasswordRecoveryCode.consumed_at.is_(None),
                PasswordRecoveryCode.invalidated_at.is_(None),
                PasswordRecoveryCode.expires_at >= attempted_at,
            )
            .values(consumed_at=attempted_at)
        ),
    )
    if result.rowcount != 1:
        database.rollback()
        raise InvalidRecoveryCode
    user.password_hash = hash_password(new_password)
    invalidate_recovery_codes(database, user.id, attempted_at)
    revoke_sessions(database, user.id)
    database.execute(
        delete(PasswordRecoveryAttempt).where(PasswordRecoveryAttempt.client_key_hash == key)
    )
    database.add(AuditEvent(action="auth.password_recovered", target_id=user.id))
    database.commit()
