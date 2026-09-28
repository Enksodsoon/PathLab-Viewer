from pathlib import Path

import pytest

from scripts import frontend_qa_fault, seed_frontend_qa


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
