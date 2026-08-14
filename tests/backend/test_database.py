from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError
from wsi_viewer.config import Settings
from wsi_viewer.database import create_schema, pool_options_for, session_factory
from wsi_viewer.main import create_app
from wsi_viewer.models import (
    AuditEvent,
    Job,
    PasswordRecoveryAttempt,
    PasswordRecoveryCode,
    Session,
    Slide,
    User,
)


def test_sqlite_schema_has_contract_tables_and_wal(tmp_path: Path) -> None:
    settings = Settings(database_url=f"sqlite:///{tmp_path / 'db.sqlite3'}", data_root=tmp_path)
    create_schema(settings)
    with session_factory(settings)() as database:
        tables = {
            row[0]
            for row in database.execute(text("SELECT name FROM sqlite_master WHERE type='table'"))
        }
        mode = database.execute(text("PRAGMA journal_mode")).scalar_one().lower()
    assert {
        User.__tablename__,
        Session.__tablename__,
        Slide.__tablename__,
        Job.__tablename__,
        AuditEvent.__tablename__,
    } <= tables
    assert mode == "wal"


@pytest.mark.parametrize(
    ("role", "expected_size"),
    (("general", 5), ("classroom", 4), ("all", 5)),
)
def test_sqlite_pool_is_bounded_by_runtime_role(role: str, expected_size: int) -> None:
    settings = Settings(_env_file=None, service_role=role)

    assert pool_options_for(settings) == {
        "pool_size": expected_size,
        "max_overflow": 0,
        "pool_timeout": 1.0,
    }


def test_runtime_app_startup_does_not_create_or_stamp_schema(tmp_path: Path) -> None:
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'runtime.sqlite3'}",
        data_root=tmp_path / "data",
    )
    create_app(settings)
    with session_factory(settings)() as database:
        tables = {
            row[0]
            for row in database.execute(text("SELECT name FROM sqlite_master WHERE type='table'"))
        }
    assert tables == set()


def test_sqlite_schema_contains_password_recovery_tables(tmp_path: Path) -> None:
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'recovery.sqlite3'}", data_root=tmp_path
    )
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
        tables = {
            row[0]
            for row in database.execute(text("SELECT name FROM sqlite_master WHERE type='table'"))
        }
    assert {"password_recovery_codes", "password_recovery_attempts"} <= tables


def test_alembic_upgrade_from_0001_preserves_users_and_sessions(
    tmp_path: Path, monkeypatch
) -> None:
    database_path = tmp_path / "upgrade-from-0001.sqlite3"
    monkeypatch.setenv("PATHLAB_DATABASE_URL", f"sqlite:///{database_path}")
    monkeypatch.setenv("PATHLAB_DATA_ROOT", str(tmp_path / "data"))
    config = Config("alembic.ini")
    command.upgrade(config, "20260719_0001")
    settings = Settings(database_url=f"sqlite:///{database_path}", data_root=tmp_path / "data")
    with session_factory(settings)() as database:
        database.execute(
            text(
                "INSERT INTO users (id, username, password_hash, created_at) "
                "VALUES ('user-1', 'admin', 'hash', '2026-07-19 08:00:00')"
            )
        )
        database.execute(
            text(
                "INSERT INTO sessions (id, user_id, csrf_token, expires_at, created_at) "
                "VALUES ('session-1', 'user-1', 'csrf', "
                "'2026-07-20 08:00:00', '2026-07-19 08:00:00')"
            )
        )
        database.commit()

    command.upgrade(config, "head")

    with session_factory(settings)() as database:
        assert database.execute(text("SELECT username FROM users")).scalar_one() == "admin"
        assert database.execute(text("SELECT user_id FROM sessions")).scalar_one() == "user-1"
        assert database.execute(
            text("SELECT credential_generation FROM users")
        ).scalar_one() == 1
        assert database.execute(
            text("SELECT credential_generation FROM sessions")
        ).scalar_one() == 1


def test_current_migration_indexes_recovery_audit_retention_queries(
    tmp_path: Path, monkeypatch
) -> None:
    database_path = tmp_path / "audit-index.sqlite3"
    monkeypatch.setenv("PATHLAB_DATABASE_URL", f"sqlite:///{database_path}")
    monkeypatch.setenv("PATHLAB_DATA_ROOT", str(tmp_path / "data"))
    command.upgrade(Config("alembic.ini"), "head")
    settings = Settings(database_url=f"sqlite:///{database_path}", data_root=tmp_path / "data")
    with session_factory(settings)() as database:
        indexes = inspect(database.connection()).get_indexes("audit_events")

    assert any(index["column_names"] == ["action", "created_at"] for index in indexes)


def test_storage_accounting_migration_upgrades_and_downgrades(
    tmp_path: Path, monkeypatch
) -> None:
    database_path = tmp_path / "storage-accounting.sqlite3"
    monkeypatch.setenv("PATHLAB_DATABASE_URL", f"sqlite:///{database_path}")
    monkeypatch.setenv("PATHLAB_DATA_ROOT", str(tmp_path / "data"))
    config = Config("alembic.ini")

    command.upgrade(config, "head")
    settings = Settings(database_url=f"sqlite:///{database_path}", data_root=tmp_path / "data")
    with session_factory(settings)() as database:
        columns = {
            column["name"]
            for column in inspect(database.connection()).get_columns("slides")
        }
    assert {"reserved_bytes", "derivative_bytes", "derivative_file_count"} <= columns

    command.downgrade(config, "20260719_0004")
    with session_factory(settings)() as database:
        downgraded = {
            column["name"] for column in inspect(database.connection()).get_columns("slides")
        }
    assert not {
        "reserved_bytes",
        "derivative_bytes",
        "derivative_file_count",
    } & downgraded


def test_desktop_ingest_capacity_migration_round_trips_existing_row(
    tmp_path: Path, monkeypatch
) -> None:
    database_path = tmp_path / "desktop-ingest-capacity.sqlite3"
    monkeypatch.setenv("PATHLAB_DATABASE_URL", f"sqlite:///{database_path}")
    monkeypatch.setenv("PATHLAB_DATA_ROOT", str(tmp_path / "data"))
    config = Config("alembic.ini")
    command.upgrade(config, "20260729_0011")
    settings = Settings(database_url=f"sqlite:///{database_path}", data_root=tmp_path / "data")
    with session_factory(settings)() as database:
        database.execute(
            text(
                "INSERT INTO users (id, username, password_hash, created_at) "
                "VALUES ('user-1', 'admin', 'hash', CURRENT_TIMESTAMP)"
            )
        )
        database.execute(
            text(
                "INSERT INTO desktop_credentials "
                "(id, user_id, device_name, scopes, expires_at, created_at) "
                "VALUES ('credential-1', 'user-1', 'Forge', '[]', "
                "'2027-01-01 00:00:00', CURRENT_TIMESTAMP)"
            )
        )
        database.execute(
            text(
                "INSERT INTO desktop_ingests "
                "(id, credential_id, display_name, artifact_revision_id, package_length, "
                "received_bytes, package_sha256, manifest_sha256, status, created_at, updated_at) "
                "VALUES ('ingest-1', 'credential-1', 'Existing', 'artifact-1', 10, 0, "
                ":hash, :hash, 'uploading', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
            ),
            {"hash": "a" * 64},
        )
        database.commit()

    command.upgrade(config, "head")
    with session_factory(settings)() as database:
        row = database.execute(
            text(
                "SELECT derivative_bytes, derivative_file_count "
                "FROM desktop_ingests WHERE id = 'ingest-1'"
            )
        ).one()
        assert row == (None, None)

    command.downgrade(config, "20260729_0011")
    command.upgrade(config, "head")
    with session_factory(settings)() as database:
        assert database.execute(
            text("SELECT display_name FROM desktop_ingests WHERE id = 'ingest-1'")
        ).scalar_one() == "Existing"


def test_ome_dynamic_render_mode_migration_round_trips_existing_slide(
    tmp_path: Path, monkeypatch
) -> None:
    database_path = tmp_path / "ome-render-mode.sqlite3"
    monkeypatch.setenv("PATHLAB_DATABASE_URL", f"sqlite:///{database_path}")
    monkeypatch.setenv("PATHLAB_DATA_ROOT", str(tmp_path / "data"))
    config = Config("alembic.ini")
    command.upgrade(config, "20260730_0012")
    settings = Settings(database_url=f"sqlite:///{database_path}", data_root=tmp_path / "data")
    with session_factory(settings)() as database:
        database.execute(
            text(
                "INSERT INTO slides "
                "(id, public_id, display_name, original_filename, source_bytes, state, "
                "reserved_bytes, derivative_bytes, derivative_file_count, description, "
                "case_id, organ_site, stain, diagnosis, course, tags, teaching_note, "
                "admin_notes, sort_order, created_at, updated_at) VALUES "
                "('slide-before-render-mode', 'public-before-render-mode', 'Existing', "
                "'existing.ome.tif', 1, 'ready_private', 0, 0, 0, '', '', '', '', '', '', "
                "'[]', '', '', 0, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
            )
        )
        database.commit()

    command.upgrade(config, "head")
    with session_factory(settings)() as database:
        row = database.execute(
            text(
                "SELECT render_mode FROM slides "
                "WHERE id = 'slide-before-render-mode'"
            )
        ).scalar_one()
        assert row == "static_dzi"

    command.downgrade(config, "20260730_0012")
    with session_factory(settings)() as database:
        columns = {
            column["name"] for column in inspect(database.connection()).get_columns("slides")
        }
        assert "render_mode" not in columns
        assert database.execute(
            text("SELECT display_name FROM slides WHERE id = 'slide-before-render-mode'")
        ).scalar_one() == "Existing"

    command.upgrade(config, "head")
    with session_factory(settings)() as database:
        assert database.execute(
            text(
                "SELECT render_mode FROM slides "
                "WHERE id = 'slide-before-render-mode'"
            )
        ).scalar_one() == "static_dzi"


def test_desktop_ome_ingest_migration_defaults_existing_ingests(
    tmp_path: Path, monkeypatch
) -> None:
    database_path = tmp_path / "desktop-ome-ingest.sqlite3"
    monkeypatch.setenv("PATHLAB_DATABASE_URL", f"sqlite:///{database_path}")
    monkeypatch.setenv("PATHLAB_DATA_ROOT", str(tmp_path / "data"))
    config = Config("alembic.ini")
    command.upgrade(config, "20260730_0013")
    settings = Settings(database_url=f"sqlite:///{database_path}", data_root=tmp_path / "data")
    with session_factory(settings)() as database:
        database.execute(
            text(
                "INSERT INTO users (id, username, password_hash, created_at) "
                "VALUES ('user-ome', 'admin-ome', 'hash', CURRENT_TIMESTAMP)"
            )
        )
        database.execute(
            text(
                "INSERT INTO desktop_credentials "
                "(id, user_id, device_name, scopes, expires_at, created_at) "
                "VALUES ('credential-ome', 'user-ome', 'Forge', '[]', "
                "'2027-01-01 00:00:00', CURRENT_TIMESTAMP)"
            )
        )
        database.execute(
            text(
                "INSERT INTO desktop_ingests "
                "(id, credential_id, display_name, artifact_revision_id, package_length, "
                "received_bytes, package_sha256, manifest_sha256, status, created_at, updated_at) "
                "VALUES ('ingest-ome', 'credential-ome', 'Existing', 'artifact-ome', 10, 0, "
                ":hash, :hash, 'uploading', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
            ),
            {"hash": "a" * 64},
        )
        database.commit()

    command.upgrade(config, "head")
    with session_factory(settings)() as database:
        assert database.execute(
            text(
                "SELECT ingest_mode FROM desktop_ingests "
                "WHERE id = 'ingest-ome'"
            )
        ).scalar_one() == "prepared_v2"

    command.downgrade(config, "20260730_0013")
    command.upgrade(config, "head")
    with session_factory(settings)() as database:
        assert database.execute(
            text(
                "SELECT ingest_mode FROM desktop_ingests "
                "WHERE id = 'ingest-ome'"
            )
        ).scalar_one() == "prepared_v2"


def test_library_v2_migration_preserves_public_ids_and_round_trips(
    tmp_path: Path, monkeypatch
) -> None:
    database_path = tmp_path / "library-v2.sqlite3"
    monkeypatch.setenv("PATHLAB_DATABASE_URL", f"sqlite:///{database_path}")
    monkeypatch.setenv("PATHLAB_DATA_ROOT", str(tmp_path / "data"))
    config = Config("alembic.ini")
    command.upgrade(config, "20260723_0005")
    settings = Settings(database_url=f"sqlite:///{database_path}", data_root=tmp_path / "data")
    with session_factory(settings)() as database:
        database.execute(
            text(
                "INSERT INTO slides "
                "(id, public_id, display_name, original_filename, source_bytes, state, "
                "reserved_bytes, derivative_bytes, derivative_file_count, created_at, "
                "updated_at, published_at) VALUES "
                "('slide-1', 'stable-public-id', 'Published', 'source.ome.tiff', 10, "
                "'published', 0, 20, 2, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, "
                "CURRENT_TIMESTAMP)"
            )
        )
        database.commit()

    command.upgrade(config, "head")
    with session_factory(settings)() as database:
        tables = {
            row[0]
            for row in database.execute(
                text("SELECT name FROM sqlite_master WHERE type IN ('table', 'view')")
            )
        }
        assert {
            "folders",
            "collections",
            "collection_slides",
            "saved_views",
            "library_shares",
            "share_slides",
            "publication_grants",
        } <= tables
        assert database.execute(
            text("SELECT public_id FROM slides WHERE id = 'slide-1'")
        ).scalar_one() == "stable-public-id"
        assert database.execute(
            text(
                "SELECT source_type || ':' || source_id FROM publication_grants "
                "WHERE slide_id = 'slide-1'"
            )
        ).scalar_one() == "individual:slide-1"
        migrated_slide = database.get(Slide, "slide-1")
        assert migrated_slide is not None
        assert migrated_slide.tags == []

    command.downgrade(config, "20260723_0005")
    command.upgrade(config, "head")
    with session_factory(settings)() as database:
        assert database.execute(
            text("SELECT public_id FROM slides WHERE id = 'slide-1'")
        ).scalar_one() == "stable-public-id"
        migrated_slide = database.get(Slide, "slide-1")
        assert migrated_slide is not None
        assert migrated_slide.tags == []


def test_storage_accounting_columns_reject_negative_values(
    tmp_path: Path, monkeypatch
) -> None:
    database_path = tmp_path / "storage-accounting-negative.sqlite3"
    monkeypatch.setenv("PATHLAB_DATABASE_URL", f"sqlite:///{database_path}")
    monkeypatch.setenv("PATHLAB_DATA_ROOT", str(tmp_path / "data"))
    command.upgrade(Config("alembic.ini"), "head")
    settings = Settings(database_url=f"sqlite:///{database_path}", data_root=tmp_path / "data")

    with (
        session_factory(settings)() as database,
        pytest.raises(IntegrityError),
    ):
        database.execute(
            text(
                "INSERT INTO slides "
                "(id, public_id, display_name, original_filename, source_bytes, state, "
                "reserved_bytes, derivative_bytes, derivative_file_count, created_at, "
                "updated_at) VALUES ('slide-1', 'public-1', 'Test', 'test.ome.tif', 1, "
                "'uploading', -1, 0, 0, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
            )
        )
        database.commit()


def test_library_performance_indexes_upgrade_and_round_trip(
    tmp_path: Path, monkeypatch
) -> None:
    database_path = tmp_path / "library-indexes.sqlite3"
    monkeypatch.setenv("PATHLAB_DATABASE_URL", f"sqlite:///{database_path}")
    monkeypatch.setenv("PATHLAB_DATA_ROOT", str(tmp_path / "data"))
    config = Config("alembic.ini")

    command.upgrade(config, "head")
    settings = Settings(database_url=f"sqlite:///{database_path}", data_root=tmp_path / "data")
    expected = {
        "ix_slides_display_name_id",
        "ix_slides_organ_site_ci",
        "ix_slides_stain_ci",
        "ix_slides_diagnosis_ci",
        "ix_slides_course_ci",
    }
    with session_factory(settings)() as database:
        indexes = {
            row[1]
            for row in database.execute(text("PRAGMA index_list('slides')"))
        }
    assert expected <= indexes

    command.downgrade(config, "20260723_0007")
    with session_factory(settings)() as database:
        downgraded = {
            row[1]
            for row in database.execute(text("PRAGMA index_list('slides')"))
        }
    assert not expected & downgraded

    command.upgrade(config, "head")
    with session_factory(settings)() as database:
        restored = {
            row[1]
            for row in database.execute(text("PRAGMA index_list('slides')"))
        }
    assert expected <= restored


def test_admin_annotation_migration_is_additive_and_round_trips_existing_slides(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database_path = tmp_path / "admin-annotations.sqlite3"
    monkeypatch.setenv("PATHLAB_DATABASE_URL", f"sqlite:///{database_path}")
    monkeypatch.setenv("PATHLAB_DATA_ROOT", str(tmp_path / "data"))
    config = Config("alembic.ini")
    command.upgrade(config, "20260724_0008")
    settings = Settings(database_url=f"sqlite:///{database_path}", data_root=tmp_path / "data")
    with session_factory(settings)() as database:
        database.execute(
            text(
                "INSERT INTO slides "
                "(id, public_id, display_name, original_filename, source_bytes, state, "
                "reserved_bytes, derivative_bytes, derivative_file_count, description, "
                "case_id, organ_site, stain, diagnosis, course, tags, teaching_note, "
                "admin_notes, sort_order, created_at, updated_at) VALUES "
                "('slide-before-annotations', 'public-before-annotations', 'Existing', "
                "'existing.ome.tif', 1, 'ready_private', 0, 0, 0, '', '', '', '', '', '', "
                "'[]', '', '', 0, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
            )
        )
        database.commit()

    command.upgrade(config, "head")
    with session_factory(settings)() as database:
        inspector = inspect(database.connection())
        assert {
            "annotation_layers",
            "annotations",
            "annotation_revisions",
        } <= set(inspector.get_table_names())
        annotation_indexes = {
            index["name"]: index["column_names"]
            for index in inspector.get_indexes("annotations")
        }
        assert annotation_indexes["ix_annotations_slide_active"] == [
            "slide_id",
            "deleted_at",
            "created_at",
            "id",
        ]
        slide_columns = {column["name"] for column in inspector.get_columns("slides")}
        assert "annotation_version" in slide_columns
        assert database.execute(
            text(
                "SELECT public_id || ':' || annotation_version FROM slides "
                "WHERE id = 'slide-before-annotations'"
            )
        ).scalar_one() == "public-before-annotations:0"
        database.execute(
            text(
                "INSERT INTO annotation_layers "
                "(id, slide_id, name, sort_order, visible, locked, opacity, "
                "created_at, updated_at) VALUES "
                "('11111111-1111-4111-8111-111111111111', "
                "'slide-before-annotations', 'Existing layer', 0, 1, 0, 1.0, "
                "CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
            )
        )
        database.execute(
            text(
                "INSERT INTO annotations "
                "(id, slide_id, layer_id, geometry_type, geometry, style, "
                "annotation_metadata, bbox_min_x, bbox_min_y, bbox_max_x, bbox_max_y, "
                "vertex_count, version, mutation_id, created_at, updated_at) VALUES "
                "('22222222-2222-4222-8222-222222222222', "
                "'slide-before-annotations', "
                "'11111111-1111-4111-8111-111111111111', 'point', "
                "json_object('type', 'point', 'x', 1, 'y', 2), "
                "json_object('strokeColor', '#c43d3d', 'fillColor', '#c43d3d', "
                "'strokeWidth', 2, 'opacity', 0.35, 'labelVisible', json('true')), "
                "json_object('title', 'Existing annotation', 'classification', '', "
                "'tags', json('[]'), 'notes', ''), "
                "1, 2, 1, 2, 1, 1, "
                "'33333333-3333-4333-8333-333333333333', "
                "CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
            )
        )
        database.execute(
            text(
                "INSERT INTO annotation_revisions "
                "(id, annotation_id, version, layer_id, geometry_type, geometry, style, "
                "annotation_metadata, bbox_min_x, bbox_min_y, bbox_max_x, bbox_max_y, "
                "vertex_count, mutation_id, created_at) VALUES "
                "('44444444-4444-4444-8444-444444444444', "
                "'22222222-2222-4222-8222-222222222222', 1, "
                "'11111111-1111-4111-8111-111111111111', 'point', "
                "json_object('type', 'point', 'x', 1, 'y', 2), "
                "json_object('strokeColor', '#c43d3d', 'fillColor', '#c43d3d', "
                "'strokeWidth', 2, 'opacity', 0.35, 'labelVisible', json('true')), "
                "json_object('title', 'Existing annotation', 'classification', '', "
                "'tags', json('[]'), 'notes', ''), "
                "1, 2, 1, 2, 1, "
                "'33333333-3333-4333-8333-333333333333', CURRENT_TIMESTAMP)"
            )
        )
        database.execute(
            text(
                "UPDATE slides SET annotation_version = 1 "
                "WHERE id = 'slide-before-annotations'"
            )
        )
        database.commit()
        assert database.execute(
            text(
                "SELECT "
                "(SELECT COUNT(*) FROM annotation_layers), "
                "(SELECT COUNT(*) FROM annotations), "
                "(SELECT COUNT(*) FROM annotation_revisions)"
            )
        ).one() == (1, 1, 1)

    command.downgrade(config, "20260724_0008")
    with session_factory(settings)() as database:
        inspector = inspect(database.connection())
        assert not {
            "annotation_layers",
            "annotations",
            "annotation_revisions",
        } & set(inspector.get_table_names())
        assert "annotation_version" not in {
            column["name"] for column in inspector.get_columns("slides")
        }
        assert database.execute(
            text(
                "SELECT public_id FROM slides WHERE id = 'slide-before-annotations'"
            )
        ).scalar_one() == "public-before-annotations"

    command.upgrade(config, "head")
    with session_factory(settings)() as database:
        assert database.execute(
            text(
                "SELECT public_id || ':' || annotation_version FROM slides "
                "WHERE id = 'slide-before-annotations'"
            )
        ).scalar_one() == "public-before-annotations:0"
        assert database.execute(
            text(
                "SELECT "
                "(SELECT COUNT(*) FROM annotation_layers), "
                "(SELECT COUNT(*) FROM annotations), "
                "(SELECT COUNT(*) FROM annotation_revisions)"
            )
        ).one() == (0, 0, 0)


def test_share_folder_path_migration_preserves_existing_memberships(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_path = tmp_path / "share-folder-path.sqlite3"
    monkeypatch.setenv("PATHLAB_DATABASE_URL", f"sqlite:///{database_path}")
    monkeypatch.setenv("PATHLAB_DATA_ROOT", str(tmp_path / "data"))
    config = Config("alembic.ini")
    command.upgrade(config, "20260726_0009")
    settings = Settings(database_url=f"sqlite:///{database_path}", data_root=tmp_path / "data")

    with session_factory(settings)() as database:
        database.execute(
            text(
                "INSERT INTO slides "
                "(id, public_id, display_name, original_filename, source_bytes, state, "
                "created_at, updated_at) VALUES "
                "('slide-1', 'public-1', 'Existing slide', 'private.ome.tiff', 1, "
                "'ready_private', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
            )
        )
        database.execute(
            text(
                "INSERT INTO library_shares "
                "(id, public_id, target_type, target_id, created_at, updated_at) VALUES "
                "('share-1', 'public-share-1', 'folder', 'folder-1', "
                "CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
            )
        )
        database.execute(
            text(
                "INSERT INTO share_slides "
                "(id, share_id, slide_id, created_at) VALUES "
                "('membership-1', 'share-1', 'slide-1', CURRENT_TIMESTAMP)"
            )
        )
        database.commit()

    command.upgrade(config, "head")
    with session_factory(settings)() as database:
        share_slide_columns = {
            column["name"]
            for column in inspect(database.connection()).get_columns("share_slides")
        }
        library_share_columns = {
            column["name"]
            for column in inspect(database.connection()).get_columns("library_shares")
        }
        assert "folder_path" in share_slide_columns
        assert "folder_paths" in library_share_columns
        assert database.execute(
            text("SELECT folder_path FROM share_slides WHERE id = 'membership-1'")
        ).scalar_one() == "[]"
        assert database.execute(
            text("SELECT folder_paths FROM library_shares WHERE id = 'share-1'")
        ).scalar_one() == "[]"

    command.downgrade(config, "20260726_0009")
    with session_factory(settings)() as database:
        share_slide_columns = {
            column["name"]
            for column in inspect(database.connection()).get_columns("share_slides")
        }
        library_share_columns = {
            column["name"]
            for column in inspect(database.connection()).get_columns("library_shares")
        }
        assert "folder_path" not in share_slide_columns
        assert "folder_paths" not in library_share_columns
        assert database.execute(
            text("SELECT slide_id FROM share_slides WHERE id = 'membership-1'")
        ).scalar_one() == "slide-1"

    command.upgrade(config, "head")
    with session_factory(settings)() as database:
        assert database.execute(
            text("SELECT folder_path FROM share_slides WHERE id = 'membership-1'")
        ).scalar_one() == "[]"
        assert database.execute(
            text("SELECT folder_paths FROM library_shares WHERE id = 'share-1'")
        ).scalar_one() == "[]"
