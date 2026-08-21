import os

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Session
from wsi_viewer.library import _search_ids

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
            "20260822_0024"
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
