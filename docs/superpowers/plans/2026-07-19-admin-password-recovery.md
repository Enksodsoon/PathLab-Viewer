# Admin Password Recovery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add authenticated password changes and secure forgotten-password recovery using OCI-issued, 15-minute, one-time codes for the single PathLab Viewer administrator.

**Architecture:** Add recovery-code and recovery-attempt records to SQLite, and put credential lifecycle operations in a focused `auth.py` service used by both FastAPI and the admin CLI. FastAPI exposes one CSRF-protected change endpoint and one throttled public recovery endpoint; React presents sign-in, recovery, and account-security forms without persisting secrets.

**Tech Stack:** Python 3.12, FastAPI 0.139, SQLAlchemy 2, Alembic, SQLite WAL, Argon2id, React 19, TypeScript, Vitest, Testing Library, Docker Compose, OCI Always Free.

## Global Constraints

- Preserve the single-administrator model and anonymous published-slide viewing.
- Password length is 12 to 128 Unicode characters.
- Password hashes remain Argon2id.
- Recovery codes contain at least 256 bits of randomness, expire after 15 minutes, are displayed once, and are stored only as SHA-256 digests.
- Issuing a code is CLI-only; no HTTP endpoint may issue recovery codes.
- Password change and recovery revoke all sessions and active recovery codes.
- Recovery errors do not distinguish unknown, expired, consumed, superseded, or malformed credentials.
- Recovery throttling is enforced across two API workers using SQLite: five failed attempts in five minutes, followed by a five-minute block.
- Do not add email, SMS, Redis, identity providers, permanent recovery keys, or paid services.
- Do not rotate the production password without separate explicit owner approval.
- Recovery secrets must not enter logs, commits, browser storage, shell history, screenshots, or reports.

---

## File Structure

- Create `migrations/versions/20260719_0002_password_recovery.py`: production schema upgrade and downgrade.
- Create `server/wsi_viewer/auth.py`: recovery issuance, password change/reset, attempt throttling, session/code revocation, and audit operations.
- Modify `server/wsi_viewer/models.py`: map recovery codes and persistent recovery attempts.
- Modify `server/wsi_viewer/security.py`: centralize password validation and recovery-code digest helpers.
- Modify `server/wsi_viewer/cli.py`: add `issue-recovery-code` and harden `reset-password` revocation.
- Modify `server/wsi_viewer/main.py`: add request types and thin password change/recovery endpoints.
- Create `apps/web/src/components/AuthPanels.tsx`: sign-in, forgot-password, and authenticated account-security UI.
- Modify `apps/web/src/api.ts`: add password change/recovery calls and reliable auth-state clearing.
- Modify `apps/web/src/pages/AdminPage.tsx`: integrate the extracted auth panel and account-security dialog.
- Modify `apps/web/src/styles.css`: responsive password-management form and dialog styling.
- Modify `deploy/README.md`: document safe recovery-code issuance and emergency reset behavior.
- Modify backend and frontend tests listed in each task.

---

### Task 1: Recovery Persistence and Security Primitives

**Files:**
- Create: `migrations/versions/20260719_0002_password_recovery.py`
- Modify: `server/wsi_viewer/models.py`
- Modify: `server/wsi_viewer/security.py`
- Modify: `tests/backend/test_database.py`
- Modify: `tests/backend/test_security.py`

**Interfaces:**
- Produces: `PasswordRecoveryCode`, `PasswordRecoveryAttempt` SQLAlchemy models.
- Produces: `validate_password(password: str) -> None`.
- Produces: `recovery_code_hash(code: str) -> str`.
- Produces: `normalize_username(username: str) -> str`.

- [ ] **Step 1: Write failing model and security tests**

Add these imports and tests:

```python
# tests/backend/test_database.py
from alembic import command
from alembic.config import Config
from wsi_viewer.models import PasswordRecoveryAttempt, PasswordRecoveryCode

def test_sqlite_schema_contains_password_recovery_tables(tmp_path: Path) -> None:
    settings = Settings(database_url=f"sqlite:///{tmp_path / 'recovery.sqlite3'}", data_root=tmp_path)
    create_schema(settings)
    with session_factory(settings)() as database:
        tables = {
            row[0]
            for row in database.execute(text("SELECT name FROM sqlite_master WHERE type='table'"))
        }
    assert PasswordRecoveryCode.__tablename__ in tables
    assert PasswordRecoveryAttempt.__tablename__ in tables


def test_alembic_upgrade_adds_password_recovery_tables(tmp_path: Path, monkeypatch) -> None:
    database_path = tmp_path / "migrated.sqlite3"
    monkeypatch.setenv("PATHLAB_DATABASE_URL", f"sqlite:///{database_path}")
    monkeypatch.setenv("PATHLAB_DATA_ROOT", str(tmp_path / "data"))
    command.upgrade(Config("alembic.ini"), "head")
    with database_path.open("rb"):
        pass
    settings = Settings(database_url=f"sqlite:///{database_path}", data_root=tmp_path / "data")
    with session_factory(settings)() as database:
        tables = {row[0] for row in database.execute(text("SELECT name FROM sqlite_master WHERE type='table'"))}
    assert {"password_recovery_codes", "password_recovery_attempts"} <= tables
```

```python
# tests/backend/test_security.py
import pytest
from wsi_viewer.security import hash_password, normalize_username, recovery_code_hash

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
```

- [ ] **Step 2: Run the focused tests and verify failure**

Run:

```powershell
pytest tests/backend/test_database.py tests/backend/test_security.py -q
```

Expected: collection fails because the recovery models and helper functions do not exist.

- [ ] **Step 3: Add mapped models and security helpers**

Add to `server/wsi_viewer/models.py`:

```python
class PasswordRecoveryCode(Base):
    __tablename__ = "password_recovery_codes"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    code_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    invalidated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class PasswordRecoveryAttempt(Base):
    __tablename__ = "password_recovery_attempts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    client_key_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    attempted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
```

Update `server/wsi_viewer/security.py`:

```python
import hashlib

MIN_PASSWORD_LENGTH = 12
MAX_PASSWORD_LENGTH = 128


def validate_password(password: str) -> None:
    if len(password) < MIN_PASSWORD_LENGTH:
        raise ValueError("Admin password must contain at least 12 characters")
    if len(password) > MAX_PASSWORD_LENGTH:
        raise ValueError("Admin password must contain at most 128 characters")


def hash_password(password: str) -> str:
    validate_password(password)
    return _PASSWORD_HASHER.hash(password)


def recovery_code_hash(code: str) -> str:
    return hashlib.sha256(code.encode("utf-8")).hexdigest()


def normalize_username(username: str) -> str:
    return username.strip().casefold()
```

- [ ] **Step 4: Add the complete Alembic migration**

Create `migrations/versions/20260719_0002_password_recovery.py`:

```python
"""Add one-time admin password recovery."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260719_0002"
down_revision: str | None = "20260719_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "password_recovery_codes",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "user_id",
            sa.String(36),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("code_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True)),
        sa.Column("invalidated_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_password_recovery_codes_user_id", "password_recovery_codes", ["user_id"])
    op.create_index("ix_password_recovery_codes_expires_at", "password_recovery_codes", ["expires_at"])
    op.create_table(
        "password_recovery_attempts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("client_key_hash", sa.String(64), nullable=False),
        sa.Column("attempted_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_password_recovery_attempts_client_key_hash",
        "password_recovery_attempts",
        ["client_key_hash"],
    )
    op.create_index(
        "ix_password_recovery_attempts_attempted_at",
        "password_recovery_attempts",
        ["attempted_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_password_recovery_attempts_attempted_at", table_name="password_recovery_attempts")
    op.drop_index("ix_password_recovery_attempts_client_key_hash", table_name="password_recovery_attempts")
    op.drop_table("password_recovery_attempts")
    op.drop_index("ix_password_recovery_codes_expires_at", table_name="password_recovery_codes")
    op.drop_index("ix_password_recovery_codes_user_id", table_name="password_recovery_codes")
    op.drop_table("password_recovery_codes")
```

- [ ] **Step 5: Run migration, model, security, lint, and type checks**

Run:

```powershell
pytest tests/backend/test_database.py tests/backend/test_security.py -q
ruff check server/wsi_viewer/models.py server/wsi_viewer/security.py migrations/versions/20260719_0002_password_recovery.py tests/backend/test_database.py tests/backend/test_security.py
mypy
```

Expected: all tests pass, Ruff reports no errors, and mypy reports success.

- [ ] **Step 6: Commit persistence and primitives**

```powershell
git add migrations/versions/20260719_0002_password_recovery.py server/wsi_viewer/models.py server/wsi_viewer/security.py tests/backend/test_database.py tests/backend/test_security.py
git commit -m "feat: add password recovery persistence"
```

---

### Task 2: Authentication Service and Admin CLI

**Files:**
- Create: `server/wsi_viewer/auth.py`
- Modify: `server/wsi_viewer/cli.py`
- Modify: `tests/backend/test_cli.py`
- Create: `tests/backend/test_auth.py`

**Interfaces:**
- Consumes: `PasswordRecoveryCode`, `PasswordRecoveryAttempt`, `recovery_code_hash()`, `normalize_username()`.
- Produces: `issue_recovery_code(database: OrmSession, user: User, now: datetime | None = None) -> str`.
- Produces: `change_password(database: OrmSession, user: User, current_password: str, new_password: str, now: datetime | None = None) -> None`.
- Produces: `recover_password(database: OrmSession, username: str, code: str, new_password: str, client_address: str, now: datetime | None = None) -> None`.
- Produces: `reset_password_by_cli(database: OrmSession, user: User, password: str, now: datetime | None = None) -> None`.
- Produces exceptions: `InvalidCurrentPassword`, `PasswordReuse`, `InvalidRecoveryCode`, `RecoveryThrottled`.

- [ ] **Step 1: Write failing service and CLI tests**

Create `tests/backend/test_auth.py` with fixtures that create one user and assert the critical lifecycle:

```python
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import select
from wsi_viewer.auth import InvalidRecoveryCode, issue_recovery_code, recover_password
from wsi_viewer.config import Settings
from wsi_viewer.database import create_schema, session_factory
from wsi_viewer.models import PasswordRecoveryCode, Session, User
from wsi_viewer.security import hash_password, recovery_code_hash, verify_password


def test_recovery_code_is_hashed_single_use_and_revokes_sessions(tmp_path: Path) -> None:
    settings = Settings(database_url=f"sqlite:///{tmp_path / 'auth.sqlite3'}", data_root=tmp_path)
    create_schema(settings)
    now = datetime(2026, 7, 19, 8, 0, tzinfo=UTC)
    with session_factory(settings)() as database:
        user = User(username="admin", password_hash=hash_password("correct horse battery"))
        database.add(user)
        database.flush()
        database.add(Session(id="s" * 64, user_id=user.id, csrf_token="csrf", expires_at=now + timedelta(hours=1)))
        code = issue_recovery_code(database, user, now)
        database.commit()
        stored = database.scalar(select(PasswordRecoveryCode))
        assert stored is not None
        assert stored.code_hash == recovery_code_hash(code)
        assert code not in stored.code_hash

        recover_password(database, "admin", code, "new correct horse battery", "127.0.0.1", now)
        assert verify_password(user.password_hash, "new correct horse battery")
        assert database.get(Session, "s" * 64) is None
        with pytest.raises(InvalidRecoveryCode):
            recover_password(database, "admin", code, "another correct password", "127.0.0.1", now)
```

Add to `tests/backend/test_cli.py`:

```python
def test_issue_recovery_code_does_not_read_password(monkeypatch: pytest.MonkeyPatch) -> None:
    parser = _build_parser()
    args = parser.parse_args(["issue-recovery-code", "--username", "admin"])
    assert args.command == "issue-recovery-code"
    assert args.password_stdin is False
```

- [ ] **Step 2: Run focused tests and verify failure**

```powershell
pytest tests/backend/test_auth.py tests/backend/test_cli.py -q
```

Expected: collection fails because `wsi_viewer.auth` and `_build_parser` do not exist.

- [ ] **Step 3: Implement the focused authentication service**

Create `server/wsi_viewer/auth.py` with these exact constants and operations:

```python
import hashlib
import hmac
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session as OrmSession

from .models import AuditEvent, PasswordRecoveryAttempt, PasswordRecoveryCode, Session, User
from .security import hash_password, normalize_username, random_token, recovery_code_hash, verify_password

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
    material = f"{normalize_username(username)}\0{client_address}".encode("utf-8")
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


def issue_recovery_code(database: OrmSession, user: User, now: datetime | None = None) -> str:
    issued_at = _now(now)
    database.execute(delete(PasswordRecoveryAttempt).where(PasswordRecoveryAttempt.attempted_at < issued_at - ATTEMPT_RETENTION))
    invalidate_recovery_codes(database, user.id, issued_at)
    code = random_token(32)
    database.add(PasswordRecoveryCode(user_id=user.id, code_hash=recovery_code_hash(code), expires_at=issued_at + RECOVERY_TTL, created_at=issued_at))
    database.add(AuditEvent(action="auth.recovery_code_issued", target_id=user.id))
    return code


def change_password(database: OrmSession, user: User, current_password: str, new_password: str, now: datetime | None = None) -> None:
    changed_at = _now(now)
    if not verify_password(user.password_hash, current_password):
        raise InvalidCurrentPassword
    if verify_password(user.password_hash, new_password):
        raise PasswordReuse
    user.password_hash = hash_password(new_password)
    revoke_sessions(database, user.id)
    invalidate_recovery_codes(database, user.id, changed_at)
    database.add(AuditEvent(actor_user_id=user.id, action="auth.password_changed", target_id=user.id))
    database.commit()


def reset_password_by_cli(database: OrmSession, user: User, password: str, now: datetime | None = None) -> None:
    reset_at = _now(now)
    user.password_hash = hash_password(password)
    revoke_sessions(database, user.id)
    invalidate_recovery_codes(database, user.id, reset_at)
    database.add(AuditEvent(action="auth.password_reset_by_cli", target_id=user.id))
    database.commit()


def recover_password(database: OrmSession, username: str, code: str, new_password: str, client_address: str, now: datetime | None = None) -> None:
    attempted_at = _now(now)
    key = _client_key(username, client_address)
    database.execute(delete(PasswordRecoveryAttempt).where(PasswordRecoveryAttempt.attempted_at < attempted_at - ATTEMPT_RETENTION))
    recent = database.scalar(select(func.count()).select_from(PasswordRecoveryAttempt).where(PasswordRecoveryAttempt.client_key_hash == key, PasswordRecoveryAttempt.attempted_at >= attempted_at - ATTEMPT_WINDOW)) or 0
    if recent >= MAX_RECOVERY_FAILURES:
        raise RecoveryThrottled
    user = next((item for item in database.scalars(select(User)) if normalize_username(item.username) == normalize_username(username)), None)
    submitted_hash = recovery_code_hash(code)
    stored = None if user is None else database.scalar(select(PasswordRecoveryCode).where(PasswordRecoveryCode.user_id == user.id, PasswordRecoveryCode.consumed_at.is_(None), PasswordRecoveryCode.invalidated_at.is_(None)).order_by(PasswordRecoveryCode.created_at.desc()))
    valid = stored is not None and stored.expires_at >= attempted_at and hmac.compare_digest(stored.code_hash, submitted_hash)
    if not valid or user is None or stored is None:
        database.add(PasswordRecoveryAttempt(client_key_hash=key, attempted_at=attempted_at))
        database.add(AuditEvent(action="auth.password_recovery_failed", detail={"reason": "invalid_or_expired"}))
        database.commit()
        raise InvalidRecoveryCode
    result = database.execute(update(PasswordRecoveryCode).where(PasswordRecoveryCode.id == stored.id, PasswordRecoveryCode.consumed_at.is_(None), PasswordRecoveryCode.invalidated_at.is_(None), PasswordRecoveryCode.expires_at >= attempted_at).values(consumed_at=attempted_at))
    if result.rowcount != 1:
        database.rollback()
        raise InvalidRecoveryCode
    user.password_hash = hash_password(new_password)
    invalidate_recovery_codes(database, user.id, attempted_at)
    revoke_sessions(database, user.id)
    database.execute(delete(PasswordRecoveryAttempt).where(PasswordRecoveryAttempt.client_key_hash == key))
    database.add(AuditEvent(action="auth.password_recovered", target_id=user.id))
    database.commit()
```

- [ ] **Step 4: Refactor the CLI around a testable parser**

In `server/wsi_viewer/cli.py`, add `_build_parser() -> argparse.ArgumentParser`, include the three commands, skip password reads for issuance, call `issue_recovery_code()`, and print only the one-time code plus its expiry warning:

```python
def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Manage the single PathLab administrator")
    parser.add_argument("command", choices=["create-admin", "reset-password", "issue-recovery-code"])
    parser.add_argument("--username", default="admin")
    parser.add_argument("--password-stdin", action="store_true")
    return parser


def main() -> None:
    args = _build_parser().parse_args()
    settings = Settings()
    create_schema(settings)
    with session_factory(settings)() as database:
        user = database.scalar(select(User).where(User.username == args.username))
        if args.command == "issue-recovery-code":
            if user is None:
                raise SystemExit("Administrator does not exist")
            code = issue_recovery_code(database, user)
            database.commit()
            print(code)
            print("Expires in 15 minutes. Enter only on the PathLab HTTPS recovery form.", file=sys.stderr)
            return
        password = _read_password(args.password_stdin)
        if args.command == "create-admin":
            if user is not None:
                raise SystemExit("Administrator already exists")
            database.add(User(username=args.username, password_hash=hash_password(password)))
            database.commit()
            return
        if user is None:
            raise SystemExit("Administrator does not exist")
        reset_password_by_cli(database, user, password)
```

- [ ] **Step 5: Expand tests for expiry, supersession, throttling, audit secrecy, and CLI reset revocation**

Use fixed UTC timestamps and assert these exact outcomes in `tests/backend/test_auth.py` and `tests/backend/test_cli.py`:

```python
with pytest.raises(InvalidRecoveryCode):
    recover_password(database, "admin", expired_code, "valid replacement password", "10.0.0.1", now + timedelta(minutes=16))

for _ in range(5):
    with pytest.raises(InvalidRecoveryCode):
        recover_password(database, "admin", "wrong", "valid replacement password", "10.0.0.2", now)
with pytest.raises(RecoveryThrottled):
    recover_password(database, "admin", valid_code, "valid replacement password", "10.0.0.2", now)

serialized_audit = " ".join(str(event.detail) for event in database.scalars(select(AuditEvent)))
assert valid_code not in serialized_audit
assert "valid replacement password" not in serialized_audit
```

- [ ] **Step 6: Run service and CLI verification**

```powershell
pytest tests/backend/test_auth.py tests/backend/test_cli.py -q
ruff check server/wsi_viewer/auth.py server/wsi_viewer/cli.py tests/backend/test_auth.py tests/backend/test_cli.py
mypy
```

Expected: all tests pass, Ruff reports no errors, and mypy reports success.

- [ ] **Step 7: Commit service and CLI**

```powershell
git add server/wsi_viewer/auth.py server/wsi_viewer/cli.py tests/backend/test_auth.py tests/backend/test_cli.py
git commit -m "feat: add one-time recovery service"
```

---

### Task 3: FastAPI Password Endpoints

**Files:**
- Modify: `server/wsi_viewer/main.py`
- Modify: `tests/backend/test_api.py`

**Interfaces:**
- Consumes: `change_password()` and `recover_password()` from Task 2.
- Produces: `POST /api/v1/auth/password` with `{currentPassword,newPassword}`.
- Produces: `POST /api/v1/auth/password/recover` with `{username,recoveryCode,newPassword}`.

- [ ] **Step 1: Write failing endpoint tests**

Add tests that create multiple sessions, seed a recovery code through the service, and assert API error codes:

```python
def test_password_change_requires_csrf_and_revokes_sessions(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        csrf = _login(client)
        denied = client.post("/api/v1/auth/password", json={"currentPassword": "correct horse battery", "newPassword": "new correct horse battery"})
        assert denied.status_code == 403
        changed = client.post("/api/v1/auth/password", headers={"X-CSRF-Token": csrf}, json={"currentPassword": "correct horse battery", "newPassword": "new correct horse battery"})
        assert changed.status_code == 204
        assert client.get("/api/v1/admin/slides").status_code == 401
        assert client.post("/api/v1/auth/session", json={"username": "admin", "password": "correct horse battery"}).status_code == 401
        assert client.post("/api/v1/auth/session", json={"username": "admin", "password": "new correct horse battery"}).status_code == 201


def test_forgot_password_uses_generic_single_use_error(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        settings = client.app.state.settings
        with session_factory(settings)() as database:
            user = database.scalar(select(User).where(User.username == "admin"))
            assert user is not None
            code = issue_recovery_code(database, user)
            database.commit()
        reset = client.post("/api/v1/auth/password/recover", json={"username": "admin", "recoveryCode": code, "newPassword": "new correct horse battery"})
        assert reset.status_code == 204
        reused = client.post("/api/v1/auth/password/recover", json={"username": "admin", "recoveryCode": code, "newPassword": "another correct password"})
        unknown = client.post("/api/v1/auth/password/recover", json={"username": "missing", "recoveryCode": code, "newPassword": "another correct password"})
        assert reused.status_code == unknown.status_code == 400
        assert reused.json() == unknown.json() == {"detail": {"code": "INVALID_RECOVERY_CODE"}}
```

- [ ] **Step 2: Run endpoint tests and verify failure**

```powershell
pytest tests/backend/test_api.py -q
```

Expected: password endpoints return 404.

- [ ] **Step 3: Add request contracts and thin routes**

Add camel-case request models and imports to `server/wsi_viewer/main.py`:

```python
class PasswordChangeRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    current_password: str = Field(alias="currentPassword")
    new_password: str = Field(alias="newPassword")


class PasswordRecoveryRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    username: str
    recovery_code: str = Field(alias="recoveryCode")
    new_password: str = Field(alias="newPassword")
```

Add these routes after logout:

```python
@app.post("/api/v1/auth/password", status_code=status.HTTP_204_NO_CONTENT)
def update_password(payload: PasswordChangeRequest, authenticated: CsrfSession, request: Request, response: Response, db: Database) -> None:
    user = db.get(User, authenticated.user_id)
    if user is None:
        raise HTTPException(status_code=401, detail={"code": "AUTH_REQUIRED"})
    key = f"password:{user.id}:{request.client.host if request.client else 'unknown'}"
    throttle.check(key, datetime.now(UTC))
    try:
        change_password(db, user, payload.current_password, payload.new_password)
    except PasswordReuse as error:
        raise HTTPException(status_code=400, detail={"code": "PASSWORD_REUSE"}) from error
    except (InvalidCurrentPassword, ValueError) as error:
        raise HTTPException(status_code=400, detail={"code": "INVALID_PASSWORD"}) from error
    throttle.clear(key)
    response.delete_cookie(COOKIE_NAME, path="/")


@app.post("/api/v1/auth/password/recover", status_code=status.HTTP_204_NO_CONTENT)
def recover_admin_password(payload: PasswordRecoveryRequest, request: Request, response: Response, db: Database) -> None:
    try:
        recover_password(db, payload.username, payload.recovery_code, payload.new_password, request.client.host if request.client else "unknown")
    except RecoveryThrottled as error:
        raise HTTPException(status_code=429, detail={"code": "AUTH_THROTTLED"}) from error
    except InvalidRecoveryCode as error:
        raise HTTPException(status_code=400, detail={"code": "INVALID_RECOVERY_CODE"}) from error
    except ValueError as error:
        raise HTTPException(status_code=400, detail={"code": "INVALID_PASSWORD"}) from error
    response.delete_cookie(COOKIE_NAME, path="/")
```

- [ ] **Step 4: Add API tests for reuse, wrong current password, weak/oversized password, throttle, and cookie expiry**

Assert exact codes:

```python
assert wrong_current.json()["detail"]["code"] == "INVALID_PASSWORD"
assert reused_password.json()["detail"]["code"] == "PASSWORD_REUSE"
assert weak_password.json()["detail"]["code"] == "INVALID_PASSWORD"
assert throttled.status_code == 429
assert "pathlab_session=" in changed.headers["set-cookie"]
assert "Max-Age=0" in changed.headers["set-cookie"]
```

Prove the SQLite throttle is shared across separate FastAPI instances:

```python
def test_recovery_throttle_is_shared_across_api_workers(tmp_path: Path) -> None:
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'shared.sqlite3'}",
        data_root=tmp_path / "data",
        secret_key="test-secret-that-is-long-enough",
        secure_cookies=False,
    )
    create_schema(settings)
    with session_factory(settings)() as database:
        database.add(User(username="admin", password_hash=hash_password("correct horse battery")))
        database.commit()
    with TestClient(create_app(settings)) as worker_one, TestClient(create_app(settings)) as worker_two:
        payload = {"username": "admin", "recoveryCode": "wrong", "newPassword": "new correct horse battery"}
        for index in range(5):
            worker = worker_one if index % 2 == 0 else worker_two
            assert worker.post("/api/v1/auth/password/recover", json=payload).status_code == 400
        assert worker_two.post("/api/v1/auth/password/recover", json=payload).status_code == 429
```

- [ ] **Step 5: Run backend verification**

```powershell
pytest tests/backend/test_api.py tests/backend/test_auth.py -q
ruff check server/wsi_viewer/main.py tests/backend/test_api.py
mypy
```

Expected: all tests pass, Ruff reports no errors, and mypy reports success.

- [ ] **Step 6: Commit the API contract**

```powershell
git add server/wsi_viewer/main.py tests/backend/test_api.py
git commit -m "feat: expose secure password workflows"
```

---

### Task 4: React Password Management UI

**Files:**
- Create: `apps/web/src/components/AuthPanels.tsx`
- Modify: `apps/web/src/api.ts`
- Modify: `apps/web/src/pages/AdminPage.tsx`
- Modify: `apps/web/src/styles.css`
- Modify: `apps/web/src/test/admin.test.tsx`

**Interfaces:**
- Produces: `recoverPassword(username: string, recoveryCode: string, newPassword: string) -> Promise<void>`.
- Produces: `changePassword(currentPassword: string, newPassword: string) -> Promise<void>`.
- Produces: `AuthPanel({onSuccess})` and `AccountSecurityDialog({open,onClose,onChanged})`.

- [ ] **Step 1: Write failing browser tests**

Add tests to `apps/web/src/test/admin.test.tsx`:

```tsx
it('recovers a forgotten password without storing secrets', async () => {
  const fetchMock = vi.spyOn(globalThis, 'fetch')
    .mockResolvedValueOnce(new Response('', { status: 401 }))
    .mockResolvedValueOnce(new Response(null, { status: 204 }))
  render(<AdminPage />, { wrapper: MemoryRouter })
  await userEvent.click(await screen.findByRole('button', { name: /forgot password/i }))
  await userEvent.type(screen.getByLabelText(/recovery code/i), 'one-time-secret')
  await userEvent.type(screen.getByLabelText(/^new password$/i), 'new correct horse battery')
  await userEvent.type(screen.getByLabelText(/confirm new password/i), 'new correct horse battery')
  await userEvent.click(screen.getByRole('button', { name: /reset password/i }))
  await screen.findByText(/password reset/i)
  expect(JSON.stringify(fetchMock.mock.calls)).toContain('/api/v1/auth/password/recover')
  expect(sessionStorage.getItem('one-time-secret')).toBeNull()
})

it('changes the authenticated password and returns to sign in', async () => {
  vi.spyOn(globalThis, 'fetch')
    .mockResolvedValueOnce(new Response('[]', { status: 200 }))
    .mockResolvedValueOnce(new Response(null, { status: 204 }))
  render(<AdminPage />, { wrapper: MemoryRouter })
  await userEvent.click(await screen.findByRole('button', { name: /account security/i }))
  await userEvent.type(screen.getByLabelText(/current password/i), 'correct horse battery')
  await userEvent.type(screen.getByLabelText(/^new password$/i), 'new correct horse battery')
  await userEvent.type(screen.getByLabelText(/confirm new password/i), 'new correct horse battery')
  await userEvent.click(screen.getByRole('button', { name: /change password/i }))
  expect(await screen.findByText(/sign in again/i)).toBeVisible()
})
```

- [ ] **Step 2: Run the browser test and verify failure**

```powershell
pnpm --dir apps/web test -- --run src/test/admin.test.tsx
```

Expected: queries for “Forgot password” and “Account security” fail.

- [ ] **Step 3: Add API functions that clear auth state after credential changes**

Add to `apps/web/src/api.ts`:

```typescript
async function expectOk(response: Response): Promise<void> {
  if (!response.ok) await json<never>(response)
}

export async function recoverPassword(username: string, recoveryCode: string, newPassword: string): Promise<void> {
  await expectOk(await fetch('/api/v1/auth/password/recover', {
    method: 'POST',
    credentials: 'same-origin',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, recoveryCode, newPassword }),
  }))
  sessionStorage.removeItem(CSRF_KEY)
}

export async function changePassword(currentPassword: string, newPassword: string): Promise<void> {
  await expectOk(await fetch('/api/v1/auth/password', {
    method: 'POST',
    credentials: 'same-origin',
    headers: {
      'Content-Type': 'application/json',
      'X-CSRF-Token': sessionStorage.getItem(CSRF_KEY) ?? '',
    },
    body: JSON.stringify({ currentPassword, newPassword }),
  }))
  sessionStorage.removeItem(CSRF_KEY)
}
```

- [ ] **Step 4: Build the isolated auth components**

Create `apps/web/src/components/AuthPanels.tsx` with controlled inputs, confirmation checks, loading states, secret clearing in `finally`, and generic recovery errors:

```tsx
import { useState } from 'react'
import type { FormEvent } from 'react'
import { X } from 'lucide-react'

import { ApiError, changePassword, login, recoverPassword } from '../api'
import { Brand } from './Brand'

interface AuthPanelProps {
  onSuccess: () => void
  notice?: string
}

export function AuthPanel({ onSuccess, notice = '' }: AuthPanelProps) {
  const [mode, setMode] = useState<'login' | 'recover'>('login')
  const [username, setUsername] = useState('admin')
  const [password, setPassword] = useState('')
  const [recoveryCode, setRecoveryCode] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [confirmation, setConfirmation] = useState('')
  const [message, setMessage] = useState(notice)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  async function submitLogin(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setBusy(true); setError('')
    try { await login(username, password); onSuccess() }
    catch { setError('Sign-in failed. Check your credentials.') }
    finally { setPassword(''); setBusy(false) }
  }

  async function submitRecovery(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setError(''); setMessage('')
    if (newPassword !== confirmation) { setError('New passwords do not match.'); return }
    setBusy(true)
    try {
      await recoverPassword(username, recoveryCode, newPassword)
      setMode('login'); setMessage('Password reset. Sign in with your new password.')
    } catch (caught) {
      setError(caught instanceof ApiError && caught.code === 'INVALID_PASSWORD'
        ? 'Use a password between 12 and 128 characters.'
        : 'Invalid or expired recovery code.')
    } finally {
      setRecoveryCode(''); setNewPassword(''); setConfirmation(''); setBusy(false)
    }
  }

  function returnToLogin() {
    setMode('login'); setError(''); setMessage('')
    setRecoveryCode(''); setNewPassword(''); setConfirmation('')
  }

  return <main className="login-page"><form className="login-card" onSubmit={mode === 'login' ? submitLogin : submitRecovery}>
    <Brand />
    <div><p className="eyebrow">Administrator access</p><h1>{mode === 'login' ? 'Manage whole-slide images' : 'Recover your account'}</h1></div>
    {message && <p className="form-notice" role="status">{message}</p>}
    <label>Username<input value={username} onChange={(event) => setUsername(event.target.value)} autoComplete="username" /></label>
    {mode === 'login' ? <>
      <label>Password<input type="password" value={password} onChange={(event) => setPassword(event.target.value)} autoComplete="current-password" /></label>
      {error && <p className="form-error">{error}</p>}
      <button className="button primary" type="submit" disabled={busy}>Sign in</button>
      <button className="auth-link" type="button" onClick={() => { setMode('recover'); setError(''); setMessage('') }}>Forgot password?</button>
    </> : <>
      <p className="recovery-help">Generate a 15-minute code on the PathLab server, then enter it below.</p>
      <code className="recovery-command">docker compose -f deploy/compose.yaml exec api pathlab-admin issue-recovery-code --username admin</code>
      <label>Recovery code<input value={recoveryCode} onChange={(event) => setRecoveryCode(event.target.value)} autoComplete="one-time-code" /></label>
      <label>New password<input type="password" value={newPassword} onChange={(event) => setNewPassword(event.target.value)} autoComplete="new-password" /></label>
      <label>Confirm new password<input type="password" value={confirmation} onChange={(event) => setConfirmation(event.target.value)} autoComplete="new-password" /></label>
      {error && <p className="form-error">{error}</p>}
      <div className="auth-actions"><button className="button" type="button" onClick={returnToLogin}>Back to sign in</button><button className="button primary" type="submit" disabled={busy}>Reset password</button></div>
    </>}
  </form></main>
}

interface AccountSecurityDialogProps {
  open: boolean
  onClose: () => void
  onChanged: () => void
}

export function AccountSecurityDialog({ open, onClose, onChanged }: AccountSecurityDialogProps) {
  const [currentPassword, setCurrentPassword] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [confirmation, setConfirmation] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  if (!open) return null

  function close() {
    setCurrentPassword(''); setNewPassword(''); setConfirmation(''); setError('')
    onClose()
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setError('')
    if (newPassword !== confirmation) { setError('New passwords do not match.'); return }
    setBusy(true)
    try { await changePassword(currentPassword, newPassword); onChanged() }
    catch (caught) {
      setError(caught instanceof ApiError && caught.code === 'PASSWORD_REUSE'
        ? 'Choose a password different from the current password.'
        : 'Password change failed. Check the current password and requirements.')
    } finally {
      setCurrentPassword(''); setNewPassword(''); setConfirmation(''); setBusy(false)
    }
  }

  return <div className="dialog-backdrop"><form className="security-dialog" role="dialog" aria-modal="true" aria-labelledby="security-title" onSubmit={submit}>
    <button className="dialog-close" type="button" aria-label="Close account security" onClick={close}><X size={18} /></button>
    <p className="eyebrow">Account security</p><h2 id="security-title">Change password</h2>
    <label>Current password<input type="password" value={currentPassword} onChange={(event) => setCurrentPassword(event.target.value)} autoComplete="current-password" /></label>
    <label>New password<input type="password" value={newPassword} onChange={(event) => setNewPassword(event.target.value)} autoComplete="new-password" /></label>
    <label>Confirm new password<input type="password" value={confirmation} onChange={(event) => setConfirmation(event.target.value)} autoComplete="new-password" /></label>
    {error && <p className="form-error">{error}</p>}
    <div className="auth-actions"><button className="button" type="button" onClick={close}>Cancel</button><button className="button primary" type="submit" disabled={busy}>Change password</button></div>
  </form></div>
}
```

- [ ] **Step 5: Integrate account security into `AdminPage`**

Remove the inline `LoginPanel`, import the new components, and add state:

```tsx
const [securityOpen, setSecurityOpen] = useState(false)
const [authNotice, setAuthNotice] = useState('')

if (authorized === false) {
  return <AuthPanel notice={authNotice} onSuccess={() => { setAuthNotice(''); void refresh() }} />
}
```

Add the header action and dialog:

```tsx
<button type="button" className="icon-button" aria-label="Account security" onClick={() => setSecurityOpen(true)}>
  <KeyRound size={18} />
</button>
<AccountSecurityDialog
  open={securityOpen}
  onClose={() => setSecurityOpen(false)}
  onChanged={() => {
    setSecurityOpen(false)
    setAuthNotice('Password changed. Sign in again.')
    setAuthorized(false)
  }}
/>
```

- [ ] **Step 6: Add responsive CSS and complete error-state tests**

Add this CSS to `apps/web/src/styles.css`:

```css
.auth-link { border:0; background:transparent; color:var(--teal); font-weight:700; cursor:pointer; }
.auth-actions { display:flex; justify-content:flex-end; gap:10px; }
.form-notice { color:#267269; background:#edf8f6; border-radius:8px; padding:10px 12px; font-size:12px; }
.recovery-help { color:var(--muted); font-size:12px; line-height:1.5; }
.recovery-command { overflow-wrap:anywhere; color:#42576b; background:#f1f4f6; padding:10px; border-radius:8px; font-size:11px; }
.dialog-backdrop { position:fixed; inset:0; z-index:20; display:grid; place-items:center; padding:16px; background:rgba(16,36,61,.48); }
.security-dialog { position:relative; width:min(440px,calc(100vw - 32px)); max-height:calc(100vh - 32px); overflow:auto; display:grid; gap:18px; padding:28px; border:1px solid var(--line); border-radius:16px; background:white; box-shadow:0 22px 60px rgba(16,36,61,.24); }
.security-dialog label { display:grid; gap:7px; color:#536577; font-size:12px; font-weight:600; }
.security-dialog input { width:100%; border:1px solid #cad4dc; border-radius:8px; padding:11px 12px; }
.dialog-close { position:absolute; right:14px; top:14px; border:0; background:transparent; padding:7px; cursor:pointer; }
```

Add this exact mismatch assertion to `apps/web/src/test/admin.test.tsx`, then add equivalent assertions for generic invalid-code copy and cleared input values after a failed response:

```tsx
await userEvent.type(screen.getByLabelText(/^new password$/i), 'new correct horse battery')
await userEvent.type(screen.getByLabelText(/confirm new password/i), 'different correct password')
await userEvent.click(screen.getByRole('button', { name: /reset password/i }))
expect(fetchMock).toHaveBeenCalledTimes(1)
expect(screen.getByText(/do not match/i)).toBeVisible()
expect(localStorage.length).toBe(0)
```

- [ ] **Step 7: Run frontend checks**

```powershell
pnpm --dir apps/web test -- --run
pnpm --dir apps/web lint
pnpm --dir apps/web build
```

Expected: all Vitest tests pass, ESLint reports no errors, and Vite produces `apps/web/dist`.

- [ ] **Step 8: Commit the browser workflow**

```powershell
git add apps/web/src/components/AuthPanels.tsx apps/web/src/api.ts apps/web/src/pages/AdminPage.tsx apps/web/src/styles.css apps/web/src/test/admin.test.tsx
git commit -m "feat: add admin password management UI"
```

---

### Task 5: Regression, Operations, and OCI Deployment

**Files:**
- Modify: `deploy/README.md`
- Modify: `docs/evidence/QA.md`

**Interfaces:**
- Consumes: Tasks 1–4 as one deployable candidate.
- Produces: documented recovery commands and evidence-backed production health without rotating the live credential.

- [ ] **Step 1: Document safe production operations**

Add this content under a new `Administrator password recovery` heading in `deploy/README.md`:

```text
Generate a single-use recovery code on the server with `docker compose -f deploy/compose.yaml exec api pathlab-admin issue-recovery-code --username admin`.

The code expires after 15 minutes and invalidates earlier unused codes. Enter it only at the HTTPS Forgot password form. The command prints the code once; do not place it in shell arguments, logs, screenshots, or tickets.

For console-only emergency reset, run `docker compose -f deploy/compose.yaml exec api pathlab-admin reset-password --username admin`. A password change or reset revokes every existing session and unused recovery code.
```

- [ ] **Step 2: Run the complete local acceptance suite**

```powershell
pytest -q
ruff check .
mypy
pnpm --dir apps/web test -- --run
pnpm --dir apps/web lint
pnpm --dir apps/web build
docker compose -f deploy/compose.yaml config --quiet
git diff --check
```

Expected: every command exits 0.

- [ ] **Step 3: Verify the production-equivalent Compose recovery path without exposing secrets**

Run an isolated copy of the production backend container on port 18080. Secrets stay in process variables and are never printed:

```powershell
$workspaceRoot = (Resolve-Path -LiteralPath '.').Path
$acceptanceRoot = Join-Path $workspaceRoot '.tmp\password-recovery-acceptance'
if (Test-Path -LiteralPath $acceptanceRoot) { throw "Acceptance directory already exists: $acceptanceRoot" }
New-Item -ItemType Directory -Path $acceptanceRoot | Out-Null
$oldPassword = [Convert]::ToBase64String([Security.Cryptography.RandomNumberGenerator]::GetBytes(24))
$newPassword = [Convert]::ToBase64String([Security.Cryptography.RandomNumberGenerator]::GetBytes(24))
$secretKey = [Convert]::ToHexString([Security.Cryptography.RandomNumberGenerator]::GetBytes(32)).ToLowerInvariant()
try {
  docker build -f deploy/Dockerfile.backend -t pathlab-recovery-acceptance:local .
  docker run --detach --name pathlab-recovery-acceptance --publish 127.0.0.1:18080:8000 --env "PATHLAB_DATABASE_URL=sqlite:////data/database/pathlab.sqlite3" --env "PATHLAB_DATA_ROOT=/data" --env "PATHLAB_SECRET_KEY=$secretKey" --env "PATHLAB_SECURE_COOKIES=false" --volume "${acceptanceRoot}:/data" pathlab-recovery-acceptance:local sh -c "mkdir -p /data/database && alembic upgrade head && exec uvicorn wsi_viewer.main:app --host 0.0.0.0 --port 8000 --workers 2"
  $ready = $false
  1..30 | ForEach-Object {
    if (-not $ready) {
      try { $ready = (Invoke-WebRequest -UseBasicParsing 'http://127.0.0.1:18080/readyz').StatusCode -eq 200 } catch { Start-Sleep -Milliseconds 500 }
    }
  }
  if (-not $ready) { throw 'Acceptance API did not become ready' }
  $oldPassword | docker exec -i pathlab-recovery-acceptance pathlab-admin create-admin --username admin --password-stdin | Out-Null
  $recoveryCode = (& docker exec pathlab-recovery-acceptance pathlab-admin issue-recovery-code --username admin 2>$null | Select-Object -First 1).Trim()
  $resetBody = @{ username='admin'; recoveryCode=$recoveryCode; newPassword=$newPassword } | ConvertTo-Json -Compress
  $firstReset = Invoke-WebRequest -UseBasicParsing 'http://127.0.0.1:18080/api/v1/auth/password/recover' -Method Post -ContentType 'application/json' -Body $resetBody
  if ($firstReset.StatusCode -ne 204) { throw "First reset returned $($firstReset.StatusCode)" }
  try {
    Invoke-WebRequest -UseBasicParsing 'http://127.0.0.1:18080/api/v1/auth/password/recover' -Method Post -ContentType 'application/json' -Body $resetBody | Out-Null
    throw 'Recovery code reuse unexpectedly succeeded'
  } catch {
    if ($_.Exception.Response.StatusCode.value__ -ne 400) { throw }
  }
  $loginBody = @{ username='admin'; password=$newPassword } | ConvertTo-Json -Compress
  $login = Invoke-WebRequest -UseBasicParsing 'http://127.0.0.1:18080/api/v1/auth/session' -Method Post -ContentType 'application/json' -Body $loginBody
  if ($login.StatusCode -ne 201) { throw "New password login returned $($login.StatusCode)" }
} finally {
  docker rm --force pathlab-recovery-acceptance 2>$null | Out-Null
  if (Test-Path -LiteralPath $acceptanceRoot) {
    $resolvedAcceptance = (Resolve-Path -LiteralPath $acceptanceRoot).Path
    if (-not $resolvedAcceptance.StartsWith($workspaceRoot + [IO.Path]::DirectorySeparatorChar)) { throw "Unsafe cleanup target: $resolvedAcceptance" }
    Remove-Item -LiteralPath $resolvedAcceptance -Recurse -Force
  }
  $oldPassword = $null; $newPassword = $null; $secretKey = $null; $recoveryCode = $null; $resetBody = $null; $loginBody = $null
}
```

Record only pass/fail counts and HTTP status codes in `docs/evidence/QA.md`; never record the generated code or passwords.

- [ ] **Step 4: Commit operations and evidence**

```powershell
git add deploy/README.md docs/evidence/QA.md
git commit -m "docs: add password recovery operations"
```

- [ ] **Step 5: Push the reviewed branch**

```powershell
git status --short
git push origin codex/ome-tiff-wsi-viewer
```

Expected: worktree is clean and the branch push succeeds.

- [ ] **Step 6: Deploy the exact reviewed commit to OCI**

Use SSH alias `pathlab-oci`. On the host, verify the checkout is clean, fetch the reviewed branch, fast-forward without discarding host changes, verify the exact commit SHA, and reload the existing systemd-managed Compose deployment:

```powershell
ssh pathlab-oci 'cd /opt/pathlab-viewer && test -z "$(git status --porcelain)" && git fetch origin codex/ome-tiff-wsi-viewer && git switch codex/ome-tiff-wsi-viewer && git merge --ff-only origin/codex/ome-tiff-wsi-viewer && git rev-parse HEAD && sudo systemctl reload pathlab-viewer'
```

Before updating, verify `/opt/pathlab-viewer` is the intended deployment checkout. If it contains host-only changes or cannot fast-forward, stop and preserve them.

- [ ] **Step 7: Verify live migration and safe code issuance**

Run health checks and generate one recovery code through an interactive SSH session so it does not enter command history or captured tool output. Do not consume it and do not rotate the production password without separate owner approval.

```powershell
Invoke-WebRequest -UseBasicParsing 'https://pathlab-viewer.140-245-126-212.sslip.io/livez'
Invoke-WebRequest -UseBasicParsing 'https://pathlab-viewer.140-245-126-212.sslip.io/readyz'
```

Expected: both endpoints return HTTP 200. Confirm the login page contains **Forgot password?**, the authenticated page contains **Account security**, existing slide administration still loads, and a published viewer link still returns tiles without 404/5xx.

- [ ] **Step 8: Report the truthful stop state**

Report local/backend/frontend/Compose/live health evidence, deployed commit SHA, and the URL. State explicitly that full production recovery remains unconsumed until the owner chooses to rotate the live password; do not claim that final production reset as tested without that evidence.
