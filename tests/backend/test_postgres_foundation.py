import os
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session
from wsi_viewer.config import Settings
from wsi_viewer.database import engine_for, session_factory
from wsi_viewer.domain import SlideState
from wsi_viewer.library import _search_ids
from wsi_viewer.models import Job, Slide
from wsi_viewer.worker import _next_job_statement, expire_incomplete_uploads

POSTGRES_TEST_URL = os.getenv("PATHLAB_POSTGRES_TEST_URL")


@pytest.mark.skipif(
    POSTGRES_TEST_URL is None,
    reason="PATHLAB_POSTGRES_TEST_URL is required for the isolated PostgreSQL test",
)
def test_postgres_migrations_constraints_and_round_trip(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert POSTGRES_TEST_URL is not None
    monkeypatch.setenv("PATHLAB_DATABASE_URL", POSTGRES_TEST_URL)
    config = Config("alembic.ini")
    engine = create_engine(POSTGRES_TEST_URL)

    command.downgrade(config, "base")
    command.upgrade(config, "20260723_0005")
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO slides "
                "(id, public_id, display_name, original_filename, source_bytes, state, "
                "reserved_bytes, derivative_bytes, derivative_file_count, created_at, "
                "updated_at, published_at) VALUES "
                "('postgres-slide', 'postgres-public', 'Published', 'source.ome.tiff', "
                "10, 'published', 0, 20, 2, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, "
                "CURRENT_TIMESTAMP)"
            )
        )
    command.upgrade(config, "head")

    with engine.begin() as connection:
        assert connection.scalar(text("SELECT version_num FROM alembic_version")) == (
            "20260822_0027"
        )
        assert "slide_search" not in inspect(connection).get_table_names()
        assert connection.scalar(
            text(
                "SELECT source_type || ':' || source_id FROM publication_grants "
                "WHERE slide_id = 'postgres-slide'"
            )
        ) == "individual:postgres-slide"
        index_rows = connection.execute(
            text(
                "SELECT indexname, indexdef FROM pg_indexes "
                "WHERE schemaname = 'public' AND indexname IN "
                "('uq_folders_root_normalized_name', "
                "'uq_classroom_sessions_one_active', "
                "'uq_study_courses_one_live')"
            )
        ).all()
        definitions = {str(name): str(definition) for name, definition in index_rows}
        assert "WHERE (parent_id IS NULL)" in definitions[
            "uq_folders_root_normalized_name"
        ]
        assert "WHERE ((status)::text = 'active'::text)" in definitions[
            "uq_classroom_sessions_one_active"
        ]
        assert "WHERE ((status)::text = ANY" in definitions[
            "uq_study_courses_one_live"
        ]

    with Session(engine) as database:
        assert _search_ids(database, "bounded search") is None

    command.downgrade(config, "base")
    assert inspect(engine).get_table_names() == ["alembic_version"]
    command.upgrade(config, "head")
    engine.dispose()


@pytest.mark.skipif(
    POSTGRES_TEST_URL is None,
    reason="PATHLAB_POSTGRES_TEST_URL is required for the isolated PostgreSQL test",
)
def test_postgres_runtime_timeouts_and_worker_claims_are_isolated(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert POSTGRES_TEST_URL is not None
    target = make_url(POSTGRES_TEST_URL)
    assert target.password is not None
    password_file = tmp_path / "alembic-postgres-password"
    password_file.write_text(target.password + "\n", encoding="utf-8")
    monkeypatch.setenv(
        "PATHLAB_DATABASE_URL",
        target.set(password=None).render_as_string(hide_password=False),
    )
    monkeypatch.setenv("PATHLAB_DATABASE_PASSWORD_FILE", str(password_file))
    command.upgrade(Config("alembic.ini"), "head")
    classroom = Settings(
        _env_file=None,
        database_url=POSTGRES_TEST_URL,
        service_role="classroom",
    )
    worker = Settings(
        _env_file=None,
        database_url=POSTGRES_TEST_URL,
        service_role="worker",
    )

    with engine_for(classroom).connect() as connection:
        assert connection.scalar(text("SELECT current_setting('statement_timeout')")) == "2s"
        assert connection.scalar(text("SELECT current_setting('lock_timeout')")) == "250ms"
    with engine_for(worker).connect() as connection:
        assert connection.scalar(text("SELECT current_setting('statement_timeout')")) == "30s"
        assert connection.scalar(text("SELECT current_setting('lock_timeout')")) == "1s"

    factory = session_factory(worker)
    with factory() as database:
        database.query(Job).delete()
        database.add_all([Job(kind="probe-a"), Job(kind="probe-b")])
        database.commit()

    now = datetime.now(UTC).replace(tzinfo=None)
    first_session = factory()
    second_session = factory()
    try:
        first = first_session.scalar(_next_job_statement(now=now, postgres=True))
        second = second_session.scalar(_next_job_statement(now=now, postgres=True))
        assert first is not None
        assert second is not None
        assert second.id != first.id
    finally:
        first_session.rollback()
        second_session.rollback()
        first_session.close()
        second_session.close()
    with factory() as database:
        database.query(Job).delete()
        database.commit()

    upload_root = tmp_path / "tus"
    upload_root.mkdir()
    with factory() as database:
        slide = Slide(
            display_name="Expired PostgreSQL upload",
            original_filename="expired.ome.tif",
            source_bytes=1,
            reserved_bytes=1,
            state=SlideState.UPLOADING,
        )
        database.add(slide)
        database.commit()
        slide_id = slide.id
    info = upload_root / f"{slide_id}.info"
    payload = upload_root / slide_id
    info.write_text("{}", encoding="utf-8")
    payload.write_bytes(b"x")
    stale = (datetime.now(UTC) - timedelta(hours=25)).timestamp()
    os.utime(info, (stale, stale))

    assert expire_incomplete_uploads(
        upload_root,
        older_than=timedelta(hours=24),
        factory=factory,
    ) == 1
    with factory() as database:
        assert database.get(Slide, slide_id) is None
