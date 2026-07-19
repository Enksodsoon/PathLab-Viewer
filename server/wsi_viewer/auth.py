import hashlib
import hmac
from datetime import UTC, datetime, timedelta
from typing import Any, cast

from sqlalchemy import delete, func, select, update
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
MAX_IP_RECOVERY_FAILURES = 20
MAX_GLOBAL_RECOVERY_FAILURES = 100
FAILED_AUDIT_RETENTION = timedelta(hours=24)


class InvalidCurrentPassword(ValueError):
    pass


class PasswordReuse(ValueError):
    pass


class InvalidRecoveryCode(ValueError):
    pass


class RecoveryThrottled(ValueError):
    pass


class CredentialConflict(ValueError):
    pass


def _now(value: datetime | None) -> datetime:
    current = value or datetime.now(UTC)
    return current.replace(tzinfo=None)


def _client_key(username: str, client_address: str) -> str:
    material = f"{normalize_username(username)}\0{client_address}".encode()
    return hashlib.sha256(material).hexdigest()


def _scope_key(scope: str, value: str = "") -> str:
    return hashlib.sha256(f"{scope}\0{value}".encode()).hexdigest()


def _replace_credential(
    database: OrmSession,
    user: User,
    new_password_hash: str,
) -> None:
    expected_generation = user.credential_generation
    expected_hash = user.password_hash
    result = cast(
        CursorResult[Any],
        database.execute(
            update(User)
            .where(
                User.id == user.id,
                User.credential_generation == expected_generation,
                User.password_hash == expected_hash,
            )
            .values(
                password_hash=new_password_hash,
                credential_generation=expected_generation + 1,
            )
            .execution_options(synchronize_session=False)
        ),
    )
    if result.rowcount != 1:
        database.rollback()
        raise CredentialConflict
    user.password_hash = new_password_hash
    user.credential_generation = expected_generation + 1


def authenticate_and_create_session(
    database: OrmSession,
    username: str,
    password: str,
    session_id: str,
    csrf_token: str,
    expires_at: datetime,
    now: datetime | None = None,
) -> bool:
    authenticated_at = _now(now)
    user = database.scalar(select(User).where(User.username == username))
    if user is None or not verify_password(user.password_hash, password):
        database.rollback()
        return False
    generation = user.credential_generation
    password_hash = user.password_hash
    result = cast(
        CursorResult[Any],
        database.execute(
            update(User)
            .where(
                User.id == user.id,
                User.credential_generation == generation,
                User.password_hash == password_hash,
            )
            .values(credential_generation=generation)
            .execution_options(synchronize_session=False)
        ),
    )
    if result.rowcount != 1:
        database.rollback()
        return False
    database.add(
        Session(
            id=session_id,
            user_id=user.id,
            csrf_token=csrf_token,
            credential_generation=generation,
            expires_at=expires_at,
        )
    )
    database.add(
        AuditEvent(
            actor_user_id=user.id,
            action="auth.login",
            created_at=authenticated_at,
        )
    )
    database.commit()
    return True


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
    _replace_credential(database, user, hash_password(new_password))
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
    _replace_credential(database, user, hash_password(password))
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
    ip_key = _scope_key("ip", client_address)
    database.execute(
        delete(PasswordRecoveryAttempt).where(
            PasswordRecoveryAttempt.attempted_at < attempted_at - ATTEMPT_RETENTION
        )
    )
    database.execute(
        delete(AuditEvent).where(
            AuditEvent.action == "auth.password_recovery_failed",
            AuditEvent.created_at < attempted_at - FAILED_AUDIT_RETENTION,
        )
    )

    def failure_count(*conditions: Any) -> int:
        statement = select(func.count()).select_from(PasswordRecoveryAttempt).where(
            PasswordRecoveryAttempt.attempted_at >= attempted_at - ATTEMPT_WINDOW,
            *conditions,
        )
        return int(database.scalar(statement) or 0)

    if (
        failure_count(PasswordRecoveryAttempt.ip_key_hash == ip_key)
        >= MAX_IP_RECOVERY_FAILURES
        or failure_count() >= MAX_GLOBAL_RECOVERY_FAILURES
    ):
        database.commit()
        raise RecoveryThrottled
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
        database.add(
            PasswordRecoveryAttempt(
                client_key_hash=key,
                ip_key_hash=ip_key,
                attempted_at=attempted_at,
            )
        )
        database.add(
            AuditEvent(
                action="auth.password_recovery_failed",
                detail={"reason": "invalid_or_expired"},
                created_at=attempted_at,
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
    _replace_credential(database, user, hash_password(new_password))
    invalidate_recovery_codes(database, user.id, attempted_at)
    revoke_sessions(database, user.id)
    database.execute(
        delete(PasswordRecoveryAttempt).where(PasswordRecoveryAttempt.client_key_hash == key)
    )
    database.add(AuditEvent(action="auth.password_recovered", target_id=user.id))
    database.commit()
