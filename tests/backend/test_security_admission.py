import asyncio
import os
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import Barrier
from uuid import uuid4

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, func, select, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import sessionmaker
from wsi_viewer import auth
from wsi_viewer.admission import SharedAdmission
from wsi_viewer.config import Settings
from wsi_viewer.database import create_schema, session_factory
from wsi_viewer.identity import ensure_default_owner_membership
from wsi_viewer.main import create_app
from wsi_viewer.models import (
    AdmissionAttempt,
    Base,
    DesktopCredential,
    DesktopPairing,
    PasswordRecoveryAttempt,
    Session,
    User,
)
from wsi_viewer.security import hash_password, verify_password


@pytest.fixture(params=["sqlite", "postgresql"])
def factory(request, tmp_path):
    if request.param == "sqlite":
        settings = Settings(
            database_url=f"sqlite:///{tmp_path / 'admission.sqlite3'}", data_root=tmp_path
        )
        create_schema(settings)
        yield session_factory(settings)
        return
    url = os.getenv("PATHLAB_POSTGRES_TEST_URL")
    if not url:
        pytest.skip("PATHLAB_POSTGRES_TEST_URL required for isolated PostgreSQL checks")
    schema = f"security_{uuid4().hex}"
    engine = create_engine(url)
    with engine.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    scoped = engine.execution_options(schema_translate_map={None: schema})
    try:
        Base.metadata.create_all(scoped)
        yield sessionmaker(bind=scoped, expire_on_commit=False)
    finally:
        with engine.begin() as connection:
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        engine.dispose()


def test_shared_atomic_admission_and_expiry(factory):
    workers = [SharedAdmission(factory), SharedAdmission(factory)]
    now = datetime.now(UTC)

    def attempt(index):
        try:
            workers[index % 2].check("pairing", "one-client", now)
            return 201
        except HTTPException as error:
            assert error.headers and int(error.headers["Retry-After"]) > 0
            return error.status_code

    with ThreadPoolExecutor(max_workers=4) as pool:
        outcomes = list(pool.map(attempt, range(12)))
    assert outcomes.count(201) == 5
    assert outcomes.count(429) == 7
    workers[1].check("pairing", "one-client", now + timedelta(minutes=10))
    with factory() as database:
        assert database.scalar(select(func.count()).select_from(AdmissionAttempt)) == 1


def test_global_budget_bounds_rotating_client_retention(factory):
    admission = SharedAdmission(factory)
    now = datetime.now(UTC)
    for index in range(100):
        admission.check("pairing", f"client-{index}", now)
    with pytest.raises(HTTPException) as raised:
        admission.check("pairing", "another-client", now)
    assert raised.value.status_code == 429
    with factory() as database:
        assert database.scalar(select(func.count()).select_from(AdmissionAttempt)) == 100
    admission.check("pairing", "another-client", now + timedelta(minutes=10))
    with factory() as database:
        assert database.scalar(select(func.count()).select_from(AdmissionAttempt)) == 1


def test_login_success_clears_matching_scopes_but_keeps_other_user_and_global_budget(factory):
    admission = SharedAdmission(factory)
    now = datetime.now(UTC)
    for index in range(5):
        admission.check("login", f"client-{index}", now, "other-user")
    admission.check("login", "shared-client", now, "signed-in-user")
    admission.clear("login", "shared-client", now, "signed-in-user")
    with pytest.raises(HTTPException) as raised:
        admission.check("login", "shared-client", now, "other-user")
    assert raised.value.status_code == 429
    admission.check("login", "shared-client", now, "signed-in-user")
    with factory() as database:
        assert database.scalar(select(func.count()).select_from(AdmissionAttempt)) == 7


def test_sqlite_admission_lock_pressure_returns_controlled_retry(tmp_path):
    settings = Settings(database_url=f"sqlite:///{tmp_path / 'locked.sqlite3'}", data_root=tmp_path)
    create_schema(settings)
    factory = session_factory(settings)
    engine = factory.kw["bind"]

    def short_timeout(connection, record, proxy):
        connection.execute("PRAGMA busy_timeout=20")

    event.listen(engine, "checkout", short_timeout)
    try:
        with factory() as blocker:
            blocker.execute(text("BEGIN IMMEDIATE"))
            with pytest.raises(HTTPException) as raised:
                SharedAdmission(factory).check("pairing", "client", datetime.now(UTC))
            assert raised.value.status_code == 429
            assert raised.value.headers["Retry-After"] == "1"
            blocker.rollback()
    finally:
        event.remove(engine, "checkout", short_timeout)


@pytest.mark.parametrize("scope,limit", [("client", 5), ("ip", 20), ("global", 100)])
def test_recovery_allowances_are_atomic_across_sessions(factory, monkeypatch, scope, limit):
    now = datetime.now(UTC)

    def identity(index):
        return (
            "unknown" if scope == "client" else f"unknown-{index}",
            f"client-{index}" if scope == "global" else "same-client",
        )

    def fail(index, timestamp=now):
        username, client = identity(index)
        with factory() as database:
            try:
                auth.recover_password(database, username, "invalid", "unused", client, timestamp)
            except auth.InvalidRecoveryCode:
                return "admitted"
            except auth.RecoveryThrottled:
                return "throttled"
        pytest.fail("An invalid recovery attempt unexpectedly succeeded")

    for index in range(limit - 1):
        assert fail(index) == "admitted"

    original_check = auth._recovery_is_throttled
    start = Barrier(4)

    def synchronized_check(database, *args):
        result = original_check(database, *args)
        if not database.info.get("recovery_precheck_complete"):
            database.info["recovery_precheck_complete"] = True
            start.wait(timeout=10)  # Every request sees the last free slot before locking.
        elif not result:
            time.sleep(0.05)  # Widen the check/insert race if serialization regresses.
        return result

    with monkeypatch.context() as patch:
        patch.setattr(auth, "_recovery_is_throttled", synchronized_check)
        with ThreadPoolExecutor(max_workers=4) as pool:
            outcomes = list(pool.map(fail, range(limit, limit + 4)))
    assert outcomes.count("admitted") == 1
    assert outcomes.count("throttled") == 3
    with factory() as database:
        assert database.scalar(select(func.count()).select_from(PasswordRecoveryAttempt)) == limit
    assert fail(limit + 9, now + auth.ATTEMPT_WINDOW + timedelta(microseconds=1)) == "admitted"


def test_sqlite_recovery_write_contention_fails_closed_without_mutation(tmp_path):
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'recovery-lock.sqlite3'}", data_root=tmp_path
    )
    create_schema(settings)
    factory = session_factory(settings)
    engine = factory.kw["bind"]
    now = datetime.now(UTC)
    with factory() as database:
        user = User(username="admin", password_hash=hash_password("original fixture password"))
        database.add(user)
        database.flush()
        code = auth.issue_recovery_code(database, user, now)
        database.commit()
        user_id = user.id
        original_hash = user.password_hash

    def short_timeout(connection, record, proxy):
        connection.execute("PRAGMA busy_timeout=20")

    event.listen(engine, "checkout", short_timeout)
    try:
        with factory() as blocker:
            blocker.execute(text("BEGIN IMMEDIATE"))
            with factory() as database, pytest.raises(OperationalError):
                auth.recover_password(
                    database, "admin", code, "replacement fixture password", "client", now
                )
            blocker.rollback()
        with factory() as database:
            assert database.get(User, user_id).password_hash == original_hash
            assert database.scalar(select(func.count()).select_from(PasswordRecoveryAttempt)) == 0
            # The same valid code still works after the competing transaction releases its lock.
            auth.recover_password(
                database, "admin", code, "replacement fixture password", "client", now
            )
            assert verify_password(
                database.get(User, user_id).password_hash, "replacement fixture password"
            )
    finally:
        event.remove(engine, "checkout", short_timeout)
        engine.dispose()


def _client(factory, tmp_path, monkeypatch):
    monkeypatch.setattr("wsi_viewer.main.session_factory", lambda _: factory)
    settings = Settings(
        data_root=tmp_path / "data", secure_cookies=False, tus_internal_upload_dir=tmp_path / "tus"
    )
    return TestClient(create_app(settings))


@pytest.mark.parametrize("operation", ["login", "password"])
def test_committed_auth_success_survives_sqlite_cleanup_contention(
    tmp_path, monkeypatch, operation
):
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'cleanup.sqlite3'}", data_root=tmp_path
    )
    create_schema(settings)
    factory = session_factory(settings)
    engine = factory.kw["bind"]
    with factory() as database:
        database.add(User(username="admin", password_hash=hash_password("correct horse battery")))
        database.commit()

    def short_timeout(connection, record, proxy):
        connection.execute("PRAGMA busy_timeout=20")

    event.listen(engine, "checkout", short_timeout)
    try:
        with _client(factory, tmp_path, monkeypatch) as client:
            if operation == "password":
                login = client.post(
                    "/api/v1/auth/session",
                    json={"username": "admin", "password": "correct horse battery"},
                )
                assert login.status_code == 201
                stale_cookie = client.cookies.get("pathlab_session")
            admission = client.app.state.shared_admission
            original_clear = admission.clear
            cleanup_calls = 0

            def clear_under_write_lock(*args, **kwargs):
                nonlocal cleanup_calls
                cleanup_calls += 1
                with factory() as blocker:
                    blocker.execute(text("BEGIN IMMEDIATE"))
                    original_clear(*args, **kwargs)
                    blocker.rollback()

            monkeypatch.setattr(admission, "clear", clear_under_write_lock)
            if operation == "login":
                response = client.post(
                    "/api/v1/auth/session",
                    json={"username": "admin", "password": "correct horse battery"},
                )
                assert response.status_code == 201
                assert response.json().get("csrfToken")
                assert "pathlab_session=" in response.headers["set-cookie"]
                assert client.get("/api/v1/auth/session").status_code == 200
            else:
                response = client.post(
                    "/api/v1/auth/password",
                    headers={"X-CSRF-Token": login.json()["csrfToken"]},
                    json={
                        "currentPassword": "correct horse battery",
                        "newPassword": "new correct horse battery",
                    },
                )
                assert response.status_code == 204
                assert "Max-Age=0" in response.headers["set-cookie"]
                assert client.cookies.get("pathlab_session") is None
                assert (
                    client.get(
                        "/api/v1/auth/session",
                        headers={"Cookie": f"pathlab_session={stale_cookie}"},
                    ).status_code
                    == 401
                )
            assert cleanup_calls == 1
            with factory() as database:
                attempts = list(
                    database.scalars(
                        select(AdmissionAttempt).where(AdmissionAttempt.namespace == operation)
                    )
                )
                assert len(attempts) == 1
                assert attempts[0].client_key_hash is not None
                assert database.scalar(select(func.count()).select_from(AdmissionAttempt)) == (
                    1 if operation == "login" else 2
                )
                assert database.scalar(select(func.count()).select_from(Session)) == (
                    1 if operation == "login" else 0
                )
                user = database.scalar(select(User).where(User.username == "admin"))
                expected = (
                    "correct horse battery" if operation == "login" else "new correct horse battery"
                )
                assert verify_password(user.password_hash, expected)
    finally:
        event.remove(engine, "checkout", short_timeout)
        engine.dispose()


def test_login_and_pairing_limits_are_shared_across_apps(factory, tmp_path, monkeypatch):
    with (
        _client(factory, tmp_path, monkeypatch) as one,
        _client(factory, tmp_path, monkeypatch) as two,
    ):
        for index in range(5):
            client = one if index % 2 else two
            assert (
                client.post(
                    "/api/v1/auth/session", json={"username": "unknown", "password": "wrong"}
                ).status_code
                == 401
            )
            assert (
                client.post(
                    "/api/v1/desktop/pairings", json={"deviceName": "Fixture device"}
                ).status_code
                == 201
            )
        for path, payload in [
            ("/api/v1/auth/session", {"username": "unknown", "password": "wrong"}),
            ("/api/v1/desktop/pairings", {"deviceName": "Fixture device"}),
        ]:
            response = two.post(path, json=payload)
            assert response.status_code == 429
            assert int(response.headers["Retry-After"]) > 0


def test_pairing_normal_flow_expiry_and_concurrent_single_redemption(
    factory, tmp_path, monkeypatch
):
    with factory() as database:
        admin = User(username="admin", password_hash=hash_password("correct horse battery"))
        database.add(admin)
        database.flush()
        ensure_default_owner_membership(database, admin)
        database.commit()
    with _client(factory, tmp_path, monkeypatch) as client:
        login = client.post(
            "/api/v1/auth/session", json={"username": "admin", "password": "correct horse battery"}
        )
        assert login.status_code == 201
        pairing = client.post("/api/v1/desktop/pairings", json={"deviceName": "Fixture"}).json()
        payload = {"deviceCode": pairing["deviceCode"], "deviceSecret": pairing["deviceSecret"]}
        assert client.post("/api/v1/desktop/pairings/exchange", json=payload).status_code == 409
        invalid = payload | {"deviceSecret": "invalid-secret-with-enough-length"}
        assert client.post("/api/v1/desktop/pairings/exchange", json=invalid).status_code == 401
        assert (
            client.post(
                "/api/v1/desktop/pairings/approve",
                headers={"X-CSRF-Token": login.json()["csrfToken"]},
                json={"userCode": pairing["userCode"]},
            ).status_code
            == 204
        )
        barrier = Barrier(2)
        engine = factory.kw["bind"]

        def both_read_before_claim(connection, cursor, statement, parameters, context, executemany):
            if statement.lstrip().upper().startswith("SELECT") and (
                "desktop_pairings.device_code_hash =" in statement
            ):
                barrier.wait(timeout=10)

        event.listen(engine, "after_cursor_execute", both_read_before_claim)
        try:
            with ThreadPoolExecutor(max_workers=2) as pool:
                results = list(
                    pool.map(
                        lambda _: client.post("/api/v1/desktop/pairings/exchange", json=payload),
                        range(2),
                    )
                )
        finally:
            event.remove(engine, "after_cursor_execute", both_read_before_claim)
        assert sorted(response.status_code for response in results) == [200, 409]
        assert client.post("/api/v1/desktop/pairings/exchange", json=payload).status_code == 409
        with factory() as database:
            assert database.scalar(select(func.count()).select_from(DesktopCredential)) == 1
            stored = database.get(DesktopPairing, pairing["pairingId"])
            stored.expires_at = datetime.now(UTC) - timedelta(seconds=1)
            database.commit()
        assert client.post("/api/v1/desktop/pairings/exchange", json=payload).status_code == 401
        assert (
            client.post("/api/v1/desktop/pairings", json={"deviceName": "Next"}).status_code == 201
        )
        with factory() as database:
            assert database.get(DesktopPairing, pairing["pairingId"]) is None
            assert database.scalar(select(func.count()).select_from(DesktopCredential)) == 1


@pytest.mark.parametrize(
    ("path", "limit"),
    [
        ("/api/v1/admin/slides", 64 * 1024),
        ("/api/v1/desktop/pairings", 4096),
        ("/api/v1/desktop/ingests", 64 * 1024),
        ("/api/v2/desktop/slides/fixture", 64 * 1024),
        ("/api/v1/classroom/join", 64 * 1024),
        ("/api/v1/admin/classroom/readiness", 64 * 1024),
        ("/api/v1/study/ai-events", 64 * 1024),
        ("/api/v1/desktop/slides/fixture/annotations/batch", 256 * 1024),
        ("/api/v1/admin/study/packs/validate", 2 * 1024 * 1024),
        ("/api/v2/admin/annotations/fixture/import", 8 * 1024 * 1024),
    ],
)
@pytest.mark.parametrize("declared", [True, False])
def test_json_limits_stop_before_buffering_or_consuming_tail(tmp_path: Path, path, limit, declared):
    app = create_app(Settings(data_root=tmp_path))
    calls = 0
    sent = []

    async def receive():
        nonlocal calls
        calls += 1
        assert calls <= 2, "Oversize body tail must not be consumed"
        return {
            "type": "http.request",
            "body": b"x" * (limit if calls == 1 else 1),
            "more_body": True,
        }

    async def send(message):
        sent.append(message)

    headers = [(b"content-type", b"application/json")]
    if declared:
        headers.append((b"content-length", str(limit + 1).encode()))
    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": path,
        "raw_path": path.encode(),
        "query_string": b"",
        "headers": headers,
        "client": ("127.0.0.1", 1),
        "server": ("testserver", 80),
        "root_path": "",
    }
    asyncio.run(app(scope, receive, send))
    assert calls == (0 if declared else 2)
    assert sent[0]["status"] == 413


def test_binary_exclusions_are_method_and_route_specific(tmp_path):
    app = create_app(Settings(data_root=tmp_path))
    middleware = next(
        item for item in app.user_middleware if item.cls.__name__ == "AuthBodyLimitMiddleware"
    )
    from wsi_viewer.request_limits import AuthBodyLimitMiddleware

    reached = []

    async def binary_app(scope, receive, send):
        reached.append(scope["path"])

    limiter = AuthBodyLimitMiddleware(binary_app, **middleware.kwargs)

    async def forbidden_receive():
        raise AssertionError("Exclusions must stream directly to their owning route")

    async def send(message):
        assert message.get("status", 413) == 413

    for method, path, excluded in [
        ("PATCH", "/api/v1/desktop/ingests/id/content", True),
        ("PATCH", "/api/v2/desktop/slides/id/result-deliveries/id/content", True),
        ("POST", "/api/v1/desktop/ingests/id/content", False),
        ("POST", "/api/v1/desktop/pairings/content", False),
        ("PATCH", "/api/v1/desktop/ingests/id/content/extra", False),
    ]:
        reached.clear()
        scope = {
            "type": "http",
            "method": method,
            "path": path,
            "headers": [(b"content-length", str(65 * 1024 * 1024).encode())],
        }
        asyncio.run(limiter(scope, forbidden_receive, send))
        assert bool(reached) == excluded
