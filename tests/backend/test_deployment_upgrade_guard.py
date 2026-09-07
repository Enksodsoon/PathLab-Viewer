from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import MetaData, Table, inspect
from wsi_viewer.cli import main
from wsi_viewer.config import Settings
from wsi_viewer.database import engine_for, session_factory


@pytest.mark.parametrize("mode", ["idle", "classroom_live", "classroom_cooldown"])
def test_deployment_check_before_classroom_owner_migration(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mode: str
) -> None:
    monkeypatch.setenv("PATHLAB_DATABASE_URL", f"sqlite:///{tmp_path / 'legacy.sqlite3'}")
    monkeypatch.setenv("PATHLAB_DATA_ROOT", str(tmp_path))
    command.upgrade(Config("alembic.ini"), "20260822_0025")
    settings = Settings()
    assert "created_by_user_id" not in {
        column["name"]
        for column in inspect(engine_for(settings)).get_columns("classroom_sessions")
    }
    with session_factory(settings)() as database:
        legacy_guard = Table("runtime_guards", MetaData(), autoload_with=database.get_bind())
        database.execute(legacy_guard.insert().values(
            id="classroom-protection", mode=mode,
            version=1, updated_at=datetime.now(UTC),
            cooldown_until=datetime.now(UTC) + timedelta(minutes=2)
            if mode == "classroom_cooldown" else None,
        ))
        database.commit()
    monkeypatch.setattr("sys.argv", ["pathlab-admin", "deployment-check"])
    if mode == "idle":
        main()
    else:
        with pytest.raises(SystemExit, match=f"Classroom protection is {mode}"):
            main()
