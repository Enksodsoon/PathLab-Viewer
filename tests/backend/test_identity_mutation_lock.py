from __future__ import annotations

import os
import threading
import time
import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi import HTTPException
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.orm import Session, sessionmaker
from wsi_viewer.identity_mutation_lock import (
    LOCK_CONFLICT_CODE,
    lock_organization_mutation,
)

POSTGRES_TEST_URL = os.getenv("PATHLAB_POSTGRES_TEST_URL")
ORGANIZATION_ID = "organization-lock-fixture"


def _create_fixture(engine: Engine) -> None:
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE organizations (id VARCHAR(36) PRIMARY KEY)"))
        connection.execute(text("CREATE TABLE sessions (id VARCHAR(64) PRIMARY KEY)"))
        connection.execute(
            text(
                "CREATE TABLE organization_memberships ("
                "id VARCHAR(36) PRIMARY KEY, organization_id VARCHAR(36) NOT NULL, "
                "role VARCHAR(30) NOT NULL, status VARCHAR(20) NOT NULL)"
            )
        )
        connection.execute(
            text("INSERT INTO organizations (id) VALUES (:id)"),
            {"id": ORGANIZATION_ID},
        )
        connection.execute(text("INSERT INTO sessions (id) VALUES ('auth-a'), ('auth-b')"))
        connection.execute(
            text(
                "INSERT INTO organization_memberships "
                "(id, organization_id, role, status) VALUES "
                "('owner-a', :organization_id, 'owner', 'active'), "
                "('owner-b', :organization_id, 'owner', 'active')"
            ),
            {"organization_id": ORGANIZATION_ID},
        )


def _auth_read(database: Session, session_id: str) -> None:
    assert (
        database.scalar(text("SELECT id FROM sessions WHERE id = :id"), {"id": session_id})
        == session_id
    )
    assert database.in_transaction()


def _assert_lock_is_held_until_transaction_end(engine: Engine) -> None:
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as owner, factory() as contender:
        _auth_read(owner, "auth-a")
        _auth_read(contender, "auth-b")
        lock_organization_mutation(owner, ORGANIZATION_ID)

        started = time.monotonic()
        with pytest.raises(HTTPException) as caught:
            lock_organization_mutation(contender, ORGANIZATION_ID)
        elapsed = time.monotonic() - started

        assert caught.value.status_code == 409
        assert caught.value.detail == {  # type: ignore[comparison-overlap]
            "code": LOCK_CONFLICT_CODE
        }
        assert caught.value.headers == {"Retry-After": "1"}
        assert elapsed < 3
        assert not contender.in_transaction()
        owner.rollback()

    with factory() as after_release:
        _auth_read(after_release, "auth-a")
        lock_organization_mutation(after_release, ORGANIZATION_ID)
        after_release.rollback()


def _assert_two_owner_disable_protocol_keeps_an_owner(engine: Engine) -> None:
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    barrier = threading.Barrier(2)
    outcomes: list[str] = []
    errors: list[BaseException] = []

    def disable_other(actor: str, target: str, session_id: str) -> None:
        try:
            with factory() as database:
                _auth_read(database, session_id)
                stale_count = database.scalar(
                    text(
                        "SELECT COUNT(*) FROM organization_memberships "
                        "WHERE organization_id = :organization_id "
                        "AND role = 'owner' AND status = 'active'"
                    ),
                    {"organization_id": ORGANIZATION_ID},
                )
                assert stale_count == 2
                barrier.wait(timeout=5)
                try:
                    lock_organization_mutation(database, ORGANIZATION_ID)
                except HTTPException as error:
                    assert error.status_code == 409
                    outcomes.append("busy")
                    return
                current_count = database.scalar(
                    text(
                        "SELECT COUNT(*) FROM organization_memberships "
                        "WHERE organization_id = :organization_id "
                        "AND role = 'owner' AND status = 'active'"
                    ),
                    {"organization_id": ORGANIZATION_ID},
                )
                if int(current_count or 0) <= 1:
                    database.rollback()
                    outcomes.append("last-owner")
                    return
                database.execute(
                    text(
                        "UPDATE organization_memberships SET status = 'disabled' "
                        "WHERE id = :target AND organization_id = :organization_id"
                    ),
                    {"target": target, "organization_id": ORGANIZATION_ID},
                )
                time.sleep(0.1)
                database.commit()
                outcomes.append(f"disabled-by-{actor}")
        except BaseException as error:
            errors.append(error)

    threads = [
        threading.Thread(target=disable_other, args=("a", "owner-b", "auth-a")),
        threading.Thread(target=disable_other, args=("b", "owner-a", "auth-b")),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=5)
        assert not thread.is_alive()

    assert errors == []
    assert len([value for value in outcomes if value.startswith("disabled-by-")]) == 1
    assert set(outcomes).issubset({"disabled-by-a", "disabled-by-b", "busy", "last-owner"})
    with engine.connect() as connection:
        assert (
            connection.scalar(
                text(
                    "SELECT COUNT(*) FROM organization_memberships "
                    "WHERE organization_id = :organization_id "
                    "AND role = 'owner' AND status = 'active'"
                ),
                {"organization_id": ORGANIZATION_ID},
            )
            == 1
        )


def test_sqlite_lock_serializes_after_preexisting_auth_reads(tmp_path: Path) -> None:
    engine = create_engine(
        f"sqlite:///{tmp_path / 'identity-lock.sqlite3'}",
        connect_args={"check_same_thread": False},
    )
    try:
        _create_fixture(engine)
        _assert_lock_is_held_until_transaction_end(engine)
        _assert_two_owner_disable_protocol_keeps_an_owner(engine)
    finally:
        engine.dispose()


def test_pool_exhaustion_returns_bounded_conflict(tmp_path: Path) -> None:
    engine = create_engine(
        f"sqlite:///{tmp_path / 'identity-pool-lock.sqlite3'}",
        pool_size=1,
        max_overflow=0,
        pool_timeout=0.05,
    )
    try:
        _create_fixture(engine)
        with engine.connect(), Session(engine) as contender:
            started = time.monotonic()
            with pytest.raises(HTTPException) as caught:
                lock_organization_mutation(contender, ORGANIZATION_ID)
            elapsed = time.monotonic() - started

            assert caught.value.status_code == 409
            assert caught.value.detail == {  # type: ignore[comparison-overlap]
                "code": LOCK_CONFLICT_CODE
            }
            assert elapsed < 1
            assert not contender.in_transaction()
    finally:
        engine.dispose()


@pytest.fixture
def postgres_engine() -> Iterator[Engine]:
    if POSTGRES_TEST_URL is None:
        pytest.skip("PATHLAB_POSTGRES_TEST_URL is required for the PostgreSQL lock test")
    schema = f"identity_lock_{uuid.uuid4().hex}"
    admin = create_engine(POSTGRES_TEST_URL)
    with admin.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    engine = create_engine(
        POSTGRES_TEST_URL,
        connect_args={"options": f"-c search_path={schema}"},
    )
    try:
        _create_fixture(engine)
        yield engine
    finally:
        engine.dispose()
        with admin.begin() as connection:
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin.dispose()


def test_postgres_lock_serializes_after_preexisting_auth_reads(
    postgres_engine: Engine,
) -> None:
    _assert_lock_is_held_until_transaction_end(postgres_engine)
    _assert_two_owner_disable_protocol_keeps_an_owner(postgres_engine)
