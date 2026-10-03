from pathlib import Path

import pytest

from scripts import frontend_qa_fault, seed_frontend_qa


def test_alignment_fixture_tiles_are_served_by_actual_private_route(tmp_path):
    import xml.etree.ElementTree as ET

    from wsi_viewer.config import Settings
    from wsi_viewer.database import create_schema
    from wsi_viewer.storage import StorageLayout
    from wsi_viewer.tile_routes import private_static_target

    settings = Settings(database_url=f"sqlite:///{tmp_path / 'qa.sqlite3'}",
                        data_root=tmp_path / "data")
    create_schema(settings)
    seed_frontend_qa.seed_alignment(settings)
    storage = StorageLayout(settings.data_root)
    for index in range(12):
        slide_id = f"alignment-qa-{index:02d}"
        descriptor = private_static_target(storage, slide_id, "slide.dzi")
        extension = ET.parse(descriptor).getroot().attrib["Format"]
        tile = private_static_target(storage, slide_id, f"slide_files/10/0_0.{extension}")
        assert tile.stat().st_size > 100


@pytest.mark.parametrize("environment", ["production", "test"])
def test_seed_refuses_arbitrary_database_before_opening_it(monkeypatch, tmp_path, environment):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("PATHLAB_ENVIRONMENT", environment)
    monkeypatch.setenv("PATHLAB_DATA_ROOT", str(tmp_path / "data"))
    target = tmp_path / "untouched.sqlite3"
    monkeypatch.setenv("PATHLAB_DATABASE_URL", f"sqlite:///{target.as_posix()}")
    monkeypatch.setattr("sys.argv", ["seed_frontend_qa.py", "1000"])
    with pytest.raises(RuntimeError, match="Only the disposable fullstack launcher"):
        seed_frontend_qa.main()
    assert not target.exists()


@pytest.mark.parametrize(
    "fault",
    ["quota-full", "quota-clear", "expire-session", "expire-share", "expire-assessment-cooldown"],
)
def test_fault_refuses_production_before_opening_database(monkeypatch, tmp_path, fault):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("PATHLAB_ENVIRONMENT", "production")
    target = tmp_path / "untouched.sqlite3"
    monkeypatch.setenv("PATHLAB_DATABASE_URL", f"sqlite:///{target.as_posix()}")
    monkeypatch.setattr("sys.argv", ["frontend_qa_fault.py", fault, "synthetic"])
    with pytest.raises(RuntimeError, match="Only the disposable fullstack launcher"):
        frontend_qa_fault.main()
    assert not target.exists()


def test_seed_refuses_database_outside_disposable_root(monkeypatch, tmp_path: Path):
    monkeypatch.chdir(tmp_path)
    disposable = tmp_path / "pathlab-fullstack-test"
    monkeypatch.setenv("PATHLAB_ENVIRONMENT", "test")
    monkeypatch.setenv("PATHLAB_DATA_ROOT", str(disposable / "data"))
    target = tmp_path / "outside.sqlite3"
    monkeypatch.setenv("PATHLAB_DATABASE_URL", f"sqlite:///{target.as_posix()}")
    monkeypatch.setattr("sys.argv", ["seed_frontend_qa.py", "1000"])
    with pytest.raises(RuntimeError, match="Only the disposable fullstack launcher"):
        seed_frontend_qa.main()
    assert not target.exists()
