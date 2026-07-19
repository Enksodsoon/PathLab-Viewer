import base64
import hmac
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import Barrier, Event

import pytest
from sqlalchemy import event, select
from wsi_viewer.auth import (
    CredentialConflict,
    InvalidCurrentPassword,
    InvalidRecoveryCode,
    PasswordReuse,
    RecoveryThrottled,
    authenticate_and_create_session,
    change_password,
    issue_recovery_code,
    recover_password,
    reset_password_by_cli,
)
from wsi_viewer.config import Settings
from wsi_viewer.database import create_schema, session_factory
from wsi_viewer.models import (
    AuditEvent,
    PasswordRecoveryAttempt,
    PasswordRecoveryCode,
    Session,
    User,
)
from wsi_viewer.security import hash_password, recovery_code_hash, verify_password


def _settings(tmp_path: Path, name: str = "auth.sqlite3") -> Settings:
    return Settings(database_url=f"sqlite:///{tmp_path / name}", data_root=tmp_path)


def _create_user(database, username: str = "admin") -> User:
    user = User(username=username, password_hash=hash_password("correct horse battery"))
    database.add(user)
    database.flush()
    return user


def test_recovery_code_is_hashed_single_use_and_revokes_sessions(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    create_schema(settings)
    now = datetime(2026, 7, 19, 8, 0, tzinfo=UTC)
    with session_factory(settings)() as database:
        user = _create_user(database)
        database.add(
            Session(
                id="s" * 64,
                user_id=user.id,
                csrf_token="csrf",
                expires_at=now + timedelta(hours=1),
            )
        )
        code = issue_recovery_code(database, user, now)
        database.commit()
        stored = database.scalar(select(PasswordRecoveryCode))
        assert stored is not None
        if not hmac.compare_digest(stored.code_hash, recovery_code_hash(code)):
            pytest.fail("Stored recovery-code digest did not match")
        if hmac.compare_digest(code, stored.code_hash):
            pytest.fail("Recovery code was stored in plaintext")

        recover_password(
            database,
            "admin",
            code,
            "new correct horse battery",
            "127.0.0.1",
            now,
        )
        if not verify_password(user.password_hash, "new correct horse battery"):
            pytest.fail("Recovered password did not verify")
        assert database.get(Session, "s" * 64) is None
        with pytest.raises(InvalidRecoveryCode):
            recover_password(
                database,
                "admin",
                code,
                "another correct password",
                "127.0.0.1",
                now,
            )


def test_recovery_code_has_256_bits_and_expires_after_15_minutes(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    create_schema(settings)
    now = datetime(2026, 7, 19, 8, 0, tzinfo=UTC)
    with session_factory(settings)() as database:
        user = _create_user(database)
        code = issue_recovery_code(database, user, now)
        database.commit()

        decoded = base64.urlsafe_b64decode(code + "=" * (-len(code) % 4))
        if len(decoded) < 32:
            pytest.fail("Recovery code contained less than 256 bits")
        stored = database.scalar(select(PasswordRecoveryCode))
        assert stored is not None
        assert stored.expires_at == now.replace(tzinfo=None) + timedelta(minutes=15)
        with pytest.raises(InvalidRecoveryCode):
            recover_password(
                database,
                "admin",
                code,
                "valid replacement password",
                "10.0.0.1",
                now + timedelta(minutes=16),
            )


def test_new_recovery_code_supersedes_previous_code(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    create_schema(settings)
    now = datetime(2026, 7, 19, 8, 0, tzinfo=UTC)
    with session_factory(settings)() as database:
        user = _create_user(database)
        old_code = issue_recovery_code(database, user, now)
        database.commit()
        new_code = issue_recovery_code(database, user, now + timedelta(minutes=1))
        database.commit()

        with pytest.raises(InvalidRecoveryCode):
            recover_password(
                database,
                "admin",
                old_code,
                "valid replacement password",
                "10.0.0.1",
                now + timedelta(minutes=2),
            )
        recover_password(
            database,
            "admin",
            new_code,
            "valid replacement password",
            "10.0.0.1",
            now + timedelta(minutes=2),
        )


def test_invalid_new_password_does_not_consume_recovery_code(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    create_schema(settings)
    now = datetime(2026, 7, 19, 8, 0, tzinfo=UTC)
    with session_factory(settings)() as database:
        user = _create_user(database)
        code = issue_recovery_code(database, user, now)
        database.commit()

        with pytest.raises(ValueError, match="at least 12"):
            recover_password(database, "admin", code, "short", "10.0.0.1", now)
        recover_password(
            database,
            "admin",
            code,
            "valid replacement password",
            "10.0.0.1",
            now,
        )


def test_invalid_code_is_counted_even_when_new_password_is_invalid(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    create_schema(settings)
    now = datetime(2026, 7, 19, 8, 0, tzinfo=UTC)
    with session_factory(settings)() as database:
        _create_user(database)
        database.commit()

        with pytest.raises(InvalidRecoveryCode):
            recover_password(database, "admin", "wrong", "short", "10.0.0.1", now)
        attempts = list(database.scalars(select(PasswordRecoveryAttempt)))
        assert len(attempts) == 1


def test_fifth_failure_starts_full_five_minute_block(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    create_schema(settings)
    now = datetime(2026, 7, 19, 8, 0, tzinfo=UTC)
    with session_factory(settings)() as database:
        user = _create_user(database)
        valid_code = issue_recovery_code(database, user, now)
        database.commit()

        for minute in range(5):
            with pytest.raises(InvalidRecoveryCode):
                recover_password(
                    database,
                    "admin",
                    "wrong",
                    "valid replacement password",
                    "10.0.0.2",
                    now + timedelta(minutes=minute),
                )
        with pytest.raises(RecoveryThrottled):
            recover_password(
                database,
                "admin",
                valid_code,
                "valid replacement password",
                "10.0.0.2",
                now + timedelta(minutes=8, seconds=59),
            )
        recover_password(
            database,
            "admin",
            valid_code,
            "valid replacement password",
            "10.0.0.2",
            now + timedelta(minutes=9),
        )


def test_recovery_audit_never_contains_code_or_password(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    create_schema(settings)
    now = datetime(2026, 7, 19, 8, 0, tzinfo=UTC)
    with session_factory(settings)() as database:
        user = _create_user(database)
        valid_code = issue_recovery_code(database, user, now)
        database.commit()
        with pytest.raises(InvalidRecoveryCode):
            recover_password(
                database,
                "admin",
                "wrong",
                "valid replacement password",
                "10.0.0.3",
                now,
            )
        recover_password(
            database,
            "admin",
            valid_code,
            "valid replacement password",
            "10.0.0.4",
            now,
        )

        serialized_audit = " ".join(
            f"{event.action} {event.target_id} {event.detail}"
            for event in database.scalars(select(AuditEvent))
        )
        if valid_code in serialized_audit:
            pytest.fail("Audit data contained a recovery code")
        if "wrong" in serialized_audit:
            pytest.fail("Audit data contained a submitted code")
        if "valid replacement password" in serialized_audit:
            pytest.fail("Audit data contained a submitted password")


def test_password_changes_validate_current_password_and_revoke_access(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    create_schema(settings)
    now = datetime(2026, 7, 19, 8, 0, tzinfo=UTC)
    with session_factory(settings)() as database:
        user = _create_user(database)
        database.add(
            Session(
                id="s" * 64,
                user_id=user.id,
                csrf_token="csrf",
                expires_at=now + timedelta(hours=1),
            )
        )
        issue_recovery_code(database, user, now)
        database.commit()

        with pytest.raises(InvalidCurrentPassword):
            change_password(database, user, "incorrect password", "new secure password", now)
        with pytest.raises(PasswordReuse):
            change_password(database, user, "correct horse battery", "correct horse battery", now)
        change_password(database, user, "correct horse battery", "new secure password", now)

        if not verify_password(user.password_hash, "new secure password"):
            pytest.fail("Changed password did not verify")
        assert database.get(Session, "s" * 64) is None
        codes = list(database.scalars(select(PasswordRecoveryCode)))
        assert all(item.invalidated_at == now.replace(tzinfo=None) for item in codes)


def test_cli_password_reset_revokes_sessions_and_codes(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    create_schema(settings)
    now = datetime(2026, 7, 19, 8, 0, tzinfo=UTC)
    with session_factory(settings)() as database:
        user = _create_user(database)
        database.add(
            Session(
                id="s" * 64,
                user_id=user.id,
                csrf_token="csrf",
                expires_at=now + timedelta(hours=1),
            )
        )
        issue_recovery_code(database, user, now)
        database.commit()
        reset_password_by_cli(database, user, "replacement password", now)

        if not verify_password(user.password_hash, "replacement password"):
            pytest.fail("CLI-reset password did not verify")
        assert database.get(Session, "s" * 64) is None
        codes = list(database.scalars(select(PasswordRecoveryCode)))
        assert all(item.invalidated_at == now.replace(tzinfo=None) for item in codes)


def test_recovery_code_is_consumed_by_only_one_concurrent_session(tmp_path: Path) -> None:
    settings = _settings(tmp_path, "concurrent.sqlite3")
    create_schema(settings)
    now = datetime(2026, 7, 19, 8, 0, tzinfo=UTC)
    with session_factory(settings)() as database:
        user = _create_user(database)
        code = issue_recovery_code(database, user, now)
        database.commit()

    barrier = Barrier(2)

    def recover(client_address: str) -> type[Exception] | None:
        with session_factory(settings)() as database:
            barrier.wait()
            try:
                recover_password(
                    database,
                    "admin",
                    code,
                    "valid replacement password",
                    client_address,
                    now,
                )
            except InvalidRecoveryCode:
                return InvalidRecoveryCode
        return None

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(recover, ["10.0.0.4", "10.0.0.5"]))

    assert sorted(result is None for result in results) == [False, True]


def test_concurrent_failures_are_all_counted_before_throttling(tmp_path: Path) -> None:
    settings = _settings(tmp_path, "concurrent-failures.sqlite3")
    create_schema(settings)
    now = datetime(2026, 7, 19, 8, 0, tzinfo=UTC)
    with session_factory(settings)() as database:
        user = _create_user(database)
        valid_code = issue_recovery_code(database, user, now)
        database.commit()

    barrier = Barrier(5)

    def fail_recovery(_: int) -> type[Exception]:
        with session_factory(settings)() as database:
            barrier.wait()
            with pytest.raises(InvalidRecoveryCode) as raised:
                recover_password(
                    database,
                    "admin",
                    "wrong",
                    "valid replacement password",
                    "10.0.0.9",
                    now,
                )
        return raised.type

    with ThreadPoolExecutor(max_workers=5) as pool:
        results = list(pool.map(fail_recovery, range(5)))

    assert results == [InvalidRecoveryCode] * 5
    with session_factory(settings)() as database:
        attempts = list(database.scalars(select(PasswordRecoveryAttempt)))
        assert len(attempts) == 5
        with pytest.raises(RecoveryThrottled):
            recover_password(
                database,
                "admin",
                valid_code,
                "valid replacement password",
                "10.0.0.9",
                now,
            )


def test_login_cannot_create_session_after_concurrent_recovery(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = _settings(tmp_path, "login-recovery.sqlite3")
    create_schema(settings)
    now = datetime(2026, 7, 19, 8, 0, tzinfo=UTC)
    with session_factory(settings)() as database:
        user = _create_user(database)
        code = issue_recovery_code(database, user, now)
        database.commit()

    verified = Barrier(2)
    release = Event()
    original_verify = verify_password

    def paused_verify(encoded: str, password: str) -> bool:
        result = original_verify(encoded, password)
        verified.wait()
        release.wait(timeout=5)
        return result

    monkeypatch.setattr("wsi_viewer.auth.verify_password", paused_verify)

    def login() -> bool:
        with session_factory(settings)() as database:
            return authenticate_and_create_session(
                database,
                "admin",
                "correct horse battery",
                "l" * 64,
                "csrf",
                now + timedelta(hours=1),
                now,
            )

    with ThreadPoolExecutor(max_workers=1) as pool:
        pending = pool.submit(login)
        verified.wait()
        with session_factory(settings)() as database:
            recover_password(
                database,
                "admin",
                code,
                "recovered secure password",
                "10.0.0.1",
                now,
            )
        release.set()
        assert pending.result(timeout=5) is False

    with session_factory(settings)() as database:
        assert database.get(Session, "l" * 64) is None


def test_login_cannot_create_session_after_concurrent_cli_reset(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = _settings(tmp_path, "login-cli.sqlite3")
    create_schema(settings)
    now = datetime(2026, 7, 19, 8, 0, tzinfo=UTC)
    with session_factory(settings)() as database:
        _create_user(database)
        database.commit()

    verified = Barrier(2)
    release = Event()
    original_verify = verify_password

    def paused_verify(encoded: str, password: str) -> bool:
        result = original_verify(encoded, password)
        verified.wait()
        release.wait(timeout=5)
        return result

    monkeypatch.setattr("wsi_viewer.auth.verify_password", paused_verify)

    def login() -> bool:
        with session_factory(settings)() as database:
            return authenticate_and_create_session(
                database,
                "admin",
                "correct horse battery",
                "c" * 64,
                "csrf",
                now + timedelta(hours=1),
                now,
            )

    with ThreadPoolExecutor(max_workers=1) as pool:
        pending = pool.submit(login)
        verified.wait()
        with session_factory(settings)() as database:
            user = database.scalar(select(User).where(User.username == "admin"))
            assert user is not None
            reset_password_by_cli(database, user, "CLI replacement password", now)
        release.set()
        assert pending.result(timeout=5) is False

    with session_factory(settings)() as database:
        assert database.get(Session, "c" * 64) is None


def test_authenticated_change_cannot_overwrite_concurrent_cli_reset(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = _settings(tmp_path, "change-cli.sqlite3")
    create_schema(settings)
    now = datetime(2026, 7, 19, 8, 0, tzinfo=UTC)
    with session_factory(settings)() as database:
        _create_user(database)
        database.commit()

    verified = Barrier(2)
    release = Event()
    original_verify = verify_password
    first_call = True

    def paused_verify(encoded: str, password: str) -> bool:
        nonlocal first_call
        result = original_verify(encoded, password)
        if first_call:
            first_call = False
            verified.wait()
            release.wait(timeout=5)
        return result

    monkeypatch.setattr("wsi_viewer.auth.verify_password", paused_verify)

    def change() -> type[Exception] | None:
        with session_factory(settings)() as database:
            user = database.scalar(select(User).where(User.username == "admin"))
            assert user is not None
            try:
                change_password(
                    database,
                    user,
                    "correct horse battery",
                    "authenticated replacement password",
                    now,
                )
            except CredentialConflict:
                return CredentialConflict
        return None

    with ThreadPoolExecutor(max_workers=1) as pool:
        pending = pool.submit(change)
        verified.wait()
        with session_factory(settings)() as database:
            user = database.scalar(select(User).where(User.username == "admin"))
            assert user is not None
            reset_password_by_cli(database, user, "CLI replacement password", now)
        release.set()
        assert pending.result(timeout=5) is CredentialConflict

    with session_factory(settings)() as database:
        user = database.scalar(select(User).where(User.username == "admin"))
        assert user is not None
        assert verify_password(user.password_hash, "CLI replacement password")


def test_varied_usernames_share_a_persistent_ip_abuse_ceiling(tmp_path: Path) -> None:
    settings = _settings(tmp_path, "ip-abuse.sqlite3")
    create_schema(settings)
    now = datetime(2026, 7, 19, 8, 0, tzinfo=UTC)
    with session_factory(settings)() as database:
        _create_user(database)
        database.commit()
        for index in range(20):
            with pytest.raises(InvalidRecoveryCode):
                recover_password(
                    database,
                    f"unknown-{index}",
                    "wrong",
                    "valid replacement password",
                    "10.0.0.99",
                    now,
                )
        with pytest.raises(RecoveryThrottled):
            recover_password(
                database,
                "another-name",
                "wrong",
                "valid replacement password",
                "10.0.0.99",
                now,
            )


def test_old_recovery_failure_audits_are_pruned_opportunistically(tmp_path: Path) -> None:
    settings = _settings(tmp_path, "audit-retention.sqlite3")
    create_schema(settings)
    now = datetime(2026, 7, 19, 8, 0, tzinfo=UTC)
    with session_factory(settings)() as database:
        _create_user(database)
        database.add(
            AuditEvent(
                action="auth.password_recovery_failed",
                detail={"reason": "invalid_or_expired"},
                created_at=now.replace(tzinfo=None) - timedelta(days=2),
            )
        )
        database.commit()
        with pytest.raises(InvalidRecoveryCode):
            recover_password(
                database,
                "admin",
                "wrong",
                "valid replacement password",
                "10.0.0.1",
                now,
            )
        failures = list(
            database.scalars(
                select(AuditEvent).where(
                    AuditEvent.action == "auth.password_recovery_failed"
                )
            )
        )
        assert len(failures) == 1
        assert failures[0].created_at == now.replace(tzinfo=None)


def test_permanently_throttled_recovery_fast_path_does_not_attempt_a_write(
    tmp_path: Path,
) -> None:
    settings = _settings(tmp_path, "read-only-throttle.sqlite3")
    create_schema(settings)
    now = datetime(2026, 7, 19, 8, 0, tzinfo=UTC)
    with session_factory(settings)() as database:
        _create_user(database)
        for _ in range(5):
            with pytest.raises(InvalidRecoveryCode):
                recover_password(
                    database,
                    "admin",
                    "wrong",
                    "valid replacement password",
                    "10.0.0.1",
                    now,
                )

    statements: list[str] = []

    def capture_statement(
        _connection: object,
        _cursor: object,
        statement: str,
        _parameters: object,
        _context: object,
        _executemany: bool,
    ) -> None:
        statements.append(statement.strip().upper())

    factory = session_factory(settings)
    assert factory.kw["bind"] is not None
    event.listen(factory.kw["bind"], "before_cursor_execute", capture_statement)
    try:
        with factory() as database, pytest.raises(RecoveryThrottled):
            recover_password(
                database,
                "admin",
                "wrong",
                "valid replacement password",
                "10.0.0.1",
                now,
            )
    finally:
        event.remove(factory.kw["bind"], "before_cursor_execute", capture_statement)

    assert statements
    assert all(statement.startswith("SELECT") for statement in statements)
