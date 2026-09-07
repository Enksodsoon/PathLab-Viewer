"""Bounded metadata-only storage probes, isolated from all existing PG schemas."""

import os
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from threading import Event
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import BigInteger, create_engine, event, inspect, select, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session, sessionmaker
from wsi_viewer import storage_accounting as accounting
from wsi_viewer.admission import lock_admission
from wsi_viewer.domain import SlideState
from wsi_viewer.models import Base, DesktopCredential, DesktopIngest, Slide, User
from wsi_viewer.readiness import ALEMBIC_HEAD, schema_is_current
from wsi_viewer.storage import InsufficientStorage, StorageLayout, admission_required

PG_URL = os.getenv("PATHLAB_POSTGRES_TEST_URL")
OLD_HEAD = "20260905_0036"
BYTE_COLUMNS = {
    "slides": ("source_bytes", "reserved_bytes", "derivative_bytes"),
    "desktop_ingests": ("package_length", "received_bytes", "derivative_bytes"),
}
LARGE = 3 * 1024**3 + 123


@pytest.fixture(params=["sqlite", "postgresql"])
def storage_engine(request, tmp_path):
    if request.param == "sqlite":
        engine = create_engine(f"sqlite:///{tmp_path / 'storage.sqlite3'}")
        try:
            yield engine
        finally:
            engine.dispose()
        return
    if not PG_URL:
        pytest.skip("PATHLAB_POSTGRES_TEST_URL required for disposable PostgreSQL")
    schema = "storage_test_" + uuid4().hex
    admin = create_engine(PG_URL)
    with admin.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    engine = create_engine(
        PG_URL,
        connect_args={
            "options": f"-c search_path={schema} -c statement_timeout=5000 -c lock_timeout=2000",
        },
    )
    try:
        yield engine
    finally:
        engine.dispose()
        with admin.begin() as connection:
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin.dispose()


def migrate(engine, revision, *, downgrade=False):
    with engine.connect() as connection:
        config = Config("alembic.ini")
        config.attributes["connection"] = connection
        (command.downgrade if downgrade else command.upgrade)(config, revision)
        connection.commit()


def seed(engine):
    with Session(engine) as database:
        user = User(id="storage-user", username="storage", password_hash="synthetic")
        database.add(user)
        database.flush()
        database.add(
            DesktopCredential(
                id="storage-credential",
                user_id=user.id,
                device_name="Storage probe",
                expires_at=datetime.now(UTC) + timedelta(days=1),
            )
        )
        database.add(
            Slide(
                id="storage-slide",
                public_id="storage-public",
                display_name="Keep name",
                original_filename="synthetic.ome.tif",
                source_bytes=1234567,
                reserved_bytes=2345678,
                derivative_bytes=3456789,
                derivative_file_count=17,
                state=SlideState.READY_PRIVATE,
            )
        )
        database.flush()
        database.add(
            DesktopIngest(
                id="storage-ingest",
                credential_id="storage-credential",
                slide_id="storage-slide",
                display_name="Keep ingest",
                artifact_revision_id="revision-14",
                package_length=7654321,
                received_bytes=123456,
                derivative_bytes=234567,
                derivative_file_count=19,
                package_sha256="a" * 64,
                manifest_sha256="b" * 64,
            )
        )
        database.commit()


@pytest.mark.parametrize(
    "table,column",
    [(table, column) for table, columns in BYTE_COLUMNS.items() for column in columns],
)
def test_large_byte_round_trip(storage_engine, table, column):
    Base.metadata.create_all(storage_engine)
    seed(storage_engine)
    with storage_engine.begin() as connection:
        # The received <= length constraint remains enforced for resumed uploads.
        if column == "received_bytes":
            connection.execute(text("UPDATE desktop_ingests SET package_length=:v"), {"v": LARGE})
        connection.execute(text(f"UPDATE {table} SET {column}=:v"), {"v": LARGE})
    with storage_engine.connect() as connection:
        assert connection.scalar(text(f"SELECT {column} FROM {table}")) == LARGE


def test_sqlite_noop_rollback_preserves_large_bytes_dependents_and_schema(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'rollback.sqlite3'}")
    try:
        migrate(engine, OLD_HEAD)
        seed(engine)
        with engine.begin() as connection:
            for table, columns in BYTE_COLUMNS.items():
                assignments = ", ".join(f"{column}=:v" for column in columns)
                connection.execute(text(f"UPDATE {table} SET {assignments}"), {"v": LARGE})

        def snapshot():
            with engine.connect() as connection:
                assert connection.scalar(text("PRAGMA foreign_keys")) == 1
                assert connection.execute(text("PRAGMA foreign_key_check")).all() == []
                rows = {
                    table: connection.execute(text(f"SELECT * FROM {table}")).all()
                    for table in (*BYTE_COLUMNS, "users", "desktop_credentials")
                }
                schema = connection.execute(
                    text(
                        "SELECT type, name, tbl_name, rootpage, sql FROM sqlite_schema "
                        "ORDER BY type, name"
                    )
                ).all()
                return rows, schema

        before = snapshot()
        migrate(engine, "head")
        assert snapshot() == before
        migrate(engine, OLD_HEAD, downgrade=True)
        assert snapshot() == before
        with engine.connect() as connection:
            assert connection.scalar(text("SELECT version_num FROM alembic_version")) == OLD_HEAD
        migrate(engine, "head")
        assert snapshot() == before
    finally:
        engine.dispose()


def test_byte_migration_preserves_data_and_guards_postgres_narrowing(storage_engine):
    migrate(storage_engine, OLD_HEAD)
    seed(storage_engine)
    with storage_engine.connect() as connection:
        before = {
            table: connection.execute(text(f"SELECT * FROM {table}")).all()
            for table in BYTE_COLUMNS
        }
    migrate(storage_engine, "head")
    with Session(storage_engine) as database:
        assert schema_is_current(database)
    with storage_engine.connect() as connection:
        for table, columns in BYTE_COLUMNS.items():
            assert connection.execute(text(f"SELECT * FROM {table}")).all() == before[table]
            actual = {c["name"]: c for c in inspect(connection).get_columns(table)}
            for column in columns:
                expected = Base.metadata.tables[table].c[column].type
                assert str(actual[column]["type"]) == str(expected.compile(storage_engine.dialect))
    if storage_engine.dialect.name == "postgresql":
        for table, columns in BYTE_COLUMNS.items():
            for column in columns:
                with storage_engine.begin() as connection:
                    if column == "received_bytes":
                        connection.execute(
                            text("UPDATE desktop_ingests SET package_length=:v"), {"v": LARGE}
                        )
                    connection.execute(text(f"UPDATE {table} SET {column}=:v"), {"v": LARGE})
                with pytest.raises(RuntimeError, match="int32"):
                    migrate(storage_engine, OLD_HEAD, downgrade=True)
                with storage_engine.begin() as connection:
                    assert connection.scalar(text("SELECT version_num FROM alembic_version")) == (
                        ALEMBIC_HEAD
                    )
                    assert connection.scalar(text(f"SELECT {column} FROM {table}")) == LARGE
                    connection.execute(text(f"UPDATE {table} SET {column}=123456"))
                    if column == "received_bytes":
                        connection.execute(
                            text("UPDATE desktop_ingests SET package_length=7654321")
                        )
        with storage_engine.begin() as connection:
            connection.execute(text("UPDATE slides SET source_bytes=:v"), {"v": -LARGE})
        with pytest.raises(RuntimeError, match="int32"):
            migrate(storage_engine, OLD_HEAD, downgrade=True)
        with storage_engine.begin() as connection:
            assert connection.scalar(text("SELECT source_bytes FROM slides")) == -LARGE
            connection.execute(text("UPDATE slides SET source_bytes=123456"))
            connection.execute(text("UPDATE desktop_ingests SET derivative_bytes=NULL"))
    with storage_engine.connect() as connection:
        before_rollback = {
            table: connection.execute(text(f"SELECT * FROM {table}")).all()
            for table in BYTE_COLUMNS
        }
    migrate(storage_engine, OLD_HEAD, downgrade=True)
    with storage_engine.connect() as connection:
        for table in BYTE_COLUMNS:
            assert (
                connection.execute(text(f"SELECT * FROM {table}")).all() == (before_rollback[table])
            )
        assert connection.scalar(text("SELECT display_name FROM slides")) == "Keep name"
        assert connection.scalar(text("SELECT slide_id FROM desktop_ingests")) == "storage-slide"
        if storage_engine.dialect.name == "postgresql":
            for table, columns in BYTE_COLUMNS.items():
                actual = {c["name"]: c for c in inspect(connection).get_columns(table)}
                assert all(not isinstance(actual[column]["type"], BigInteger) for column in columns)
    migrate(storage_engine, "head")


def test_fresh_migration_accepts_large_bytes_and_readiness_rejects_false_stamp(storage_engine):
    migrate(storage_engine, "head")
    seed(storage_engine)
    with storage_engine.begin() as connection:
        connection.execute(
            text("UPDATE slides SET source_bytes=:v, derivative_bytes=:v"), {"v": LARGE}
        )
        connection.execute(
            text(
                "UPDATE desktop_ingests SET package_length=:v, "
                "received_bytes=:v, derivative_bytes=:v"
            ),
            {"v": LARGE},
        )
    with Session(storage_engine) as database:
        assert schema_is_current(database)
        assert accounting._accounted_bytes(database) == 2 * LARGE
        assert database.get(DesktopIngest, "storage-ingest").received_bytes == LARGE
    if storage_engine.dialect.name == "postgresql":
        with storage_engine.begin() as connection:
            connection.execute(text("UPDATE slides SET source_bytes=1"))
            connection.execute(text("ALTER TABLE slides ALTER COLUMN source_bytes TYPE INTEGER"))
        with Session(storage_engine) as database:
            assert not schema_is_current(database)


@pytest.mark.parametrize("render_mode", ["static_dzi", "ome_dynamic"])
def test_large_new_and_retry_reservations_use_metadata_only(
    storage_engine, tmp_path, monkeypatch, render_mode
):
    Base.metadata.create_all(storage_engine)
    factory = sessionmaker(storage_engine, expire_on_commit=False)
    required = admission_required(LARGE, render_mode=render_mode)
    layout = StorageLayout(tmp_path, cap_bytes=required)
    monkeypatch.setattr(accounting, "_require_physical_space", lambda *_: None)
    slide = accounting.reserve_new_slide(
        factory,
        layout,
        display_name="Large",
        original_filename="large.tif",
        source_bytes=LARGE,
        render_mode=render_mode,
        actor_user_id=None,
    )
    with factory() as database:
        assert accounting._accounted_bytes(database) == required
        stored = database.get(Slide, slide.id)
        stored.state = SlideState.FAILED
        stored.reserved_bytes = 0
        database.commit()
    retried = accounting.reserve_retry(factory, layout, slide_id=slide.id, actor_user_id=None)
    assert retried.reserved_bytes == required
    with factory() as database:
        assert accounting._accounted_bytes(database) == required


def test_exception_after_flush_rolls_back_bytes_and_releases_lock(
    storage_engine, tmp_path, monkeypatch
):
    Base.metadata.create_all(storage_engine)
    factory = sessionmaker(storage_engine, expire_on_commit=False)
    layout = StorageLayout(tmp_path)
    monkeypatch.setattr(accounting, "_require_physical_space", lambda *_: None)

    def cancel_after_flush(database, context):
        raise RuntimeError("synthetic cancellation after insert")

    event.listen(factory, "after_flush", cancel_after_flush)
    try:
        with pytest.raises(RuntimeError, match="synthetic cancellation"):
            accounting.reserve_new_slide(
                factory,
                layout,
                display_name="Cancelled",
                original_filename="cancelled.tif",
                source_bytes=1,
                render_mode="ome_dynamic",
                actor_user_id=None,
            )
    finally:
        event.remove(factory, "after_flush", cancel_after_flush)
    with factory() as database:
        assert accounting._accounted_bytes(database) == 0
    # A new connection can acquire the transaction lock after exception rollback.
    with ThreadPoolExecutor(max_workers=1) as pool:
        slide = pool.submit(
            accounting.reserve_new_slide,
            factory,
            layout,
            display_name="After rollback",
            original_filename="after.tif",
            source_bytes=1,
            render_mode="ome_dynamic",
            actor_user_id=None,
        ).result(3)
    assert slide.reserved_bytes == admission_required(1, render_mode="ome_dynamic")


@pytest.mark.parametrize("kinds", [("new", "new"), ("new", "retry"), ("retry", "retry")])
def test_competing_admissions_share_one_capacity_boundary(
    storage_engine, tmp_path, monkeypatch, kinds
):
    Base.metadata.create_all(storage_engine)
    factory = sessionmaker(storage_engine, expire_on_commit=False)
    for index, kind in enumerate(kinds):
        if kind == "retry":
            with factory() as database:
                database.add(
                    Slide(
                        id=f"retry-{index}",
                        display_name="Retry",
                        original_filename="retry.ome.tif",
                        source_bytes=1,
                        state=SlideState.FAILED,
                        render_mode="ome_dynamic",
                    )
                )
                database.commit()
    required = admission_required(1, render_mode="ome_dynamic")
    layout = StorageLayout(tmp_path, cap_bytes=required + 2)
    monkeypatch.setattr(accounting, "_require_physical_space", lambda *_: None)
    checked = Event()
    release = Event()
    original = accounting._require_application_capacity

    def held_check(*args, **kwargs):
        original(*args, **kwargs)
        if not checked.is_set():
            checked.set()
            assert release.wait(3)

    monkeypatch.setattr(accounting, "_require_application_capacity", held_check)

    def reserve(index):
        try:
            if kinds[index] == "retry":
                accounting.reserve_retry(
                    factory, layout, slide_id=f"retry-{index}", actor_user_id=None
                )
            else:
                accounting.reserve_new_slide(
                    factory,
                    layout,
                    display_name="New",
                    original_filename="new.ome.tif",
                    source_bytes=1,
                    render_mode="ome_dynamic",
                    actor_user_id=None,
                )
        except InsufficientStorage:
            return False
        return True

    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(reserve, 0)
        assert checked.wait(3)
        second = pool.submit(reserve, 1)
        try:
            # Pre-fix the second admission completes while the first holds its stale read.
            second.result(timeout=0.4)
        except TimeoutError:
            pass
        finally:
            release.set()
        assert sorted([first.result(timeout=3), second.result(timeout=3)]) == [False, True]
    with factory() as database:
        assert accounting._accounted_bytes(database) <= layout.cap_bytes
        assert database.scalar(text("SELECT count(*) FROM audit_events")) == 1
        assert database.scalar(text("SELECT count(*) FROM jobs")) == int(kinds[0] == "retry")
        if kinds[1] == "retry":
            loser = database.get(Slide, "retry-1")
            assert loser.state is SlideState.FAILED
            assert loser.reserved_bytes == 0


def test_postgres_lock_timeout_leaves_no_reservation(storage_engine, tmp_path, monkeypatch):
    if storage_engine.dialect.name != "postgresql":
        pytest.skip("PostgreSQL advisory lock timeout probe")
    Base.metadata.create_all(storage_engine)
    factory = sessionmaker(storage_engine, expire_on_commit=False)
    layout = StorageLayout(tmp_path)
    monkeypatch.setattr(accounting, "_require_physical_space", lambda *_: None)
    with factory() as holder:
        lock_admission(holder, "storage")
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(
                accounting.reserve_new_slide,
                factory,
                layout,
                display_name="Blocked",
                original_filename="blocked.tif",
                source_bytes=1,
                render_mode="ome_dynamic",
                actor_user_id=None,
            )
            with pytest.raises(OperationalError) as error:
                future.result(4)
            assert error.value.orig.sqlstate == "55P03"
        holder.rollback()
    with factory() as database:
        assert accounting._accounted_bytes(database) == 0
        assert database.scalar(text("SELECT count(*) FROM audit_events")) == 0
    slide = accounting.reserve_new_slide(
        factory,
        layout,
        display_name="After timeout",
        original_filename="after.tif",
        source_bytes=1,
        render_mode="ome_dynamic",
        actor_user_id=None,
    )
    assert slide.reserved_bytes == admission_required(1, render_mode="ome_dynamic")


def test_failed_reservation_and_cancelled_transaction_restore_totals(
    storage_engine, tmp_path, monkeypatch
):
    Base.metadata.create_all(storage_engine)
    factory = sessionmaker(storage_engine, expire_on_commit=False)
    layout = StorageLayout(tmp_path)
    monkeypatch.setattr(accounting, "_require_physical_space", lambda *_: None)
    with pytest.raises(LookupError):
        accounting.reserve_new_slide(
            factory,
            layout,
            display_name="Missing folder",
            original_filename="test.tif",
            source_bytes=1,
            folder_id="absent",
            actor_user_id=None,
        )
    with factory() as database:
        assert accounting._accounted_bytes(database) == 0
    slide = accounting.reserve_new_slide(
        factory,
        layout,
        display_name="Reserved",
        original_filename="test.tif",
        source_bytes=1,
        render_mode="ome_dynamic",
        actor_user_id=None,
    )
    with factory() as database:
        reserved = accounting._accounted_bytes(database)
        database.delete(database.get(Slide, slide.id))
        database.flush()
        assert accounting._accounted_bytes(database) == 0
        database.rollback()
    with factory() as database:
        assert accounting._accounted_bytes(database) == reserved
        database.delete(database.get(Slide, slide.id))
        database.commit()
    with factory() as database:
        assert accounting._accounted_bytes(database) == 0
        assert database.scalar(select(Slide)) is None
