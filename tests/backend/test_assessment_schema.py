from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect
from wsi_viewer.config import Settings
from wsi_viewer.database import session_factory
from wsi_viewer.models import Base

ASSESSMENT_TABLES = {
    "assessment_access_throttles",
    "assessment_administrations",
    "assessment_aggregate_snapshots",
    "assessment_asset_grants",
    "assessment_attempts",
    "assessment_drafts",
    "assessment_gradebook_rows",
    "assessment_mutation_receipts",
    "assessment_participants",
    "assessment_releases",
    "assessment_responses",
    "assessment_roster_snapshots",
    "assessment_score_versions",
    "assessment_sessions",
    "assessment_versions",
}


def test_assessment_models_cover_the_declared_runtime_entities() -> None:
    assert set(Base.metadata.tables) >= ASSESSMENT_TABLES
    learner = Base.metadata.tables["learner_profiles"]
    assert {"login_identifier_hash", "display_name"} <= set(learner.columns.keys())


def test_assessment_migration_round_trips_from_the_actual_previous_head(
    tmp_path: Path,
    monkeypatch,
) -> None:
    database_path = tmp_path / "assessment.sqlite3"
    monkeypatch.setenv("PATHLAB_DATABASE_URL", f"sqlite:///{database_path}")
    monkeypatch.setenv("PATHLAB_DATA_ROOT", str(tmp_path / "data"))
    config = Config("alembic.ini")
    command.upgrade(config, "20260822_0025")
    command.upgrade(config, "head")
    settings = Settings(database_url=f"sqlite:///{database_path}", data_root=tmp_path / "data")

    with session_factory(settings)() as database:
        inspector = inspect(database.connection())
        assert set(inspector.get_table_names()) >= ASSESSMENT_TABLES
        assert {"login_identifier_hash", "display_name"} <= {
            column["name"] for column in inspector.get_columns("learner_profiles")
        }

    command.downgrade(config, "20260822_0025")
    with session_factory(settings)() as database:
        inspector = inspect(database.connection())
        assert not ASSESSMENT_TABLES & set(inspector.get_table_names())
        assert "login_identifier_hash" not in {
            column["name"] for column in inspector.get_columns("learner_profiles")
        }
