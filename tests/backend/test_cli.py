import hmac
from datetime import UTC, datetime, timedelta
from io import StringIO
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, select, text
from wsi_viewer.cli import _build_parser, _read_password, main
from wsi_viewer.config import Settings
from wsi_viewer.database import create_schema, engine_for, session_factory
from wsi_viewer.domain import SlideState
from wsi_viewer.models import (
    ClassroomSession,
    Job,
    PasswordRecoveryCode,
    RuntimeGuard,
    Slide,
    User,
)
from wsi_viewer.security import hash_password, recovery_code_hash


def test_read_password_from_stdin(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("sys.stdin", StringIO("generated-password\n"))

    password = _read_password(True)
    if not hmac.compare_digest(password, "generated-password"):
        pytest.fail("Password read from stdin did not match")


def test_reject_empty_password_from_stdin(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("sys.stdin", StringIO("\n"))

    with pytest.raises(SystemExit, match="Password must not be empty"):
        _read_password(True)


def test_issue_recovery_code_does_not_read_password() -> None:
    parser = _build_parser()
    args = parser.parse_args(["issue-recovery-code", "--username", "admin"])
    assert args.command == "issue-recovery-code"
    assert args.password_stdin is False


def test_issue_recovery_code_prints_code_once_without_password_prompt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database_path = tmp_path / "cli.sqlite3"
    monkeypatch.setenv("PATHLAB_DATABASE_URL", f"sqlite:///{database_path}")
    monkeypatch.setenv("PATHLAB_DATA_ROOT", str(tmp_path))
    settings = Settings()
    create_schema(settings)
    with session_factory(settings)() as database:
        database.add(User(username="admin", password_hash=hash_password("existing password")))
        database.commit()

    def fail_prompt(_: str) -> str:
        raise AssertionError("recovery-code issuance must not prompt for a password")

    monkeypatch.setattr("getpass.getpass", fail_prompt)
    monkeypatch.setattr("sys.argv", ["pathlab-admin", "issue-recovery-code"])
    main()

    output = capsys.readouterr()
    stdout_lines = output.out.splitlines()
    if len(stdout_lines) != 1:
        pytest.fail("CLI did not emit exactly one recovery-code line")
    code = stdout_lines[0]
    if not code:
        pytest.fail("Recovery-code output was empty")
    expected_warning = (
        "Expires in 15 minutes. Enter only on the PathLab HTTPS recovery form.\n"
    )
    if not hmac.compare_digest(output.err, expected_warning):
        pytest.fail("CLI recovery-code warning did not match")
    with session_factory(settings)() as database:
        stored = database.scalar(select(PasswordRecoveryCode))
        assert stored is not None
        if not hmac.compare_digest(stored.code_hash, recovery_code_hash(code)):
            pytest.fail("Stored recovery-code digest did not match CLI output")


def test_deployment_check_does_not_require_credentials() -> None:
    args = _build_parser().parse_args(["deployment-check"])
    assert args.command == "deployment-check"


def test_postgres_migration_parser_requires_explicit_verification() -> None:
    args = _build_parser().parse_args(
        [
            "migrate-sqlite-to-postgres",
            "--source",
            "source.sqlite3",
            "--target",
            "postgresql+psycopg://localhost/pathlab",
            "--target-password-file",
            "postgres-password",
        ]
    )
    assert args.source == Path("source.sqlite3")
    assert args.target_password_file == Path("postgres-password")
    assert args.verify is False


def test_postgres_migration_command_is_noninteractive(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    source = tmp_path / "source.sqlite3"
    manifest = tmp_path / "manifest.json"
    captured: dict[str, object] = {}

    def migrate(**kwargs: object) -> dict[str, object]:
        captured.update(kwargs)
        return {"tables": [{"table": "users"}]}

    monkeypatch.setenv("PATHLAB_SECRET_KEY", "synthetic-migration-manifest-key-32-bytes")
    monkeypatch.setattr("wsi_viewer.cli.migrate_sqlite_to_postgres", migrate)
    monkeypatch.setattr(
        "sys.argv",
        [
            "pathlab-admin",
            "migrate-sqlite-to-postgres",
            "--source",
            str(source),
            "--target",
            "postgresql+psycopg://localhost/pathlab",
            "--target-password-file",
            str(tmp_path / "postgres-password"),
            "--manifest",
            str(manifest),
            "--verify",
        ],
    )

    main()

    assert captured["source_path"] == source
    assert captured["manifest_path"] == manifest
    assert captured["target_password_file"] == tmp_path / "postgres-password"
    assert captured["verify"] is True
    assert capsys.readouterr().out == (
        f"Migration verified: tables=1 manifest={manifest}\n"
    )


def test_deployment_check_allows_no_running_job(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    database_path = tmp_path / "deployment-check.sqlite3"
    monkeypatch.setenv("PATHLAB_DATABASE_URL", f"sqlite:///{database_path}")
    monkeypatch.setenv("PATHLAB_DATA_ROOT", str(tmp_path))
    settings = Settings()
    create_schema(settings)
    monkeypatch.setattr("sys.argv", ["pathlab-admin", "deployment-check"])

    main()

    output = capsys.readouterr()
    assert output.out == ""
    assert output.err == ""


def test_deployment_check_accepts_immediate_pre_runtime_guard_schema(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    database_path = tmp_path / "deployment-check-pre-runtime-guard.sqlite3"
    monkeypatch.setenv("PATHLAB_DATABASE_URL", f"sqlite:///{database_path}")
    monkeypatch.setenv("PATHLAB_DATA_ROOT", str(tmp_path))
    settings = Settings()
    command.upgrade(Config("alembic.ini"), "20260821_0023")
    assert not inspect(engine_for(settings)).has_table("runtime_guards")
    capsys.readouterr()
    monkeypatch.setattr("sys.argv", ["pathlab-admin", "deployment-check"])

    main()

    output = capsys.readouterr()
    assert output.out == ""
    assert output.err == ""


def test_deployment_check_rejects_unrecognized_missing_runtime_guard_schema(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database_path = tmp_path / "deployment-check-unknown-schema.sqlite3"
    monkeypatch.setenv("PATHLAB_DATABASE_URL", f"sqlite:///{database_path}")
    monkeypatch.setenv("PATHLAB_DATA_ROOT", str(tmp_path))
    settings = Settings()
    command.upgrade(Config("alembic.ini"), "20260821_0023")
    with engine_for(settings).begin() as connection:
        connection.execute(
            text("UPDATE alembic_version SET version_num = 'unexpected_revision'")
        )
    monkeypatch.setattr("sys.argv", ["pathlab-admin", "deployment-check"])

    with pytest.raises(SystemExit) as captured:
        main()

    assert captured.value.code == (
        "Deployment blocked: Classroom protection schema is unavailable"
    )


def test_deployment_check_blocks_running_job_without_private_details(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database_path = tmp_path / "deployment-check-running.sqlite3"
    monkeypatch.setenv("PATHLAB_DATABASE_URL", f"sqlite:///{database_path}")
    monkeypatch.setenv("PATHLAB_DATA_ROOT", str(tmp_path))
    settings = Settings()
    create_schema(settings)
    with session_factory(settings)() as database:
        slide = Slide(
            display_name="Private patient name",
            original_filename="private-patient-file.ome.tif",
            source_bytes=1,
            state=SlideState.CONVERTING,
        )
        database.add(slide)
        database.flush()
        database.add(Job(slide_id=slide.id, status="running"))
        database.commit()
    monkeypatch.setattr("sys.argv", ["pathlab-admin", "deployment-check"])

    with pytest.raises(SystemExit) as captured:
        main()

    assert captured.value.code == "Deployment blocked: worker job is active"
    output = capsys.readouterr()
    assert "Private patient name" not in output.err
    assert "private-patient-file.ome.tif" not in output.err


def test_deployment_check_blocks_an_active_real_classroom_session(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database_path = tmp_path / "deployment-check-classroom.sqlite3"
    monkeypatch.setenv("PATHLAB_DATABASE_URL", f"sqlite:///{database_path}")
    monkeypatch.setenv("PATHLAB_DATA_ROOT", str(tmp_path))
    settings = Settings()
    create_schema(settings)
    with session_factory(settings)() as database:
        database.add(
            ClassroomSession(
                join_code_hash="a" * 64,
                expires_at=datetime.now(UTC) + timedelta(hours=1),
                status="active",
            )
        )
        database.commit()
    monkeypatch.setattr("sys.argv", ["pathlab-admin", "deployment-check"])

    with pytest.raises(SystemExit) as captured:
        main()

    assert captured.value.code == "Deployment blocked: a Classroom session is active"
    output = capsys.readouterr()
    assert "a" * 64 not in output.err


def test_deployment_check_blocks_classroom_cooldown(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_path = tmp_path / "deployment-check-cooldown.sqlite3"
    monkeypatch.setenv("PATHLAB_DATABASE_URL", f"sqlite:///{database_path}")
    monkeypatch.setenv("PATHLAB_DATA_ROOT", str(tmp_path))
    settings = Settings()
    create_schema(settings)
    with session_factory(settings)() as database:
        database.add(
            RuntimeGuard(
                id="classroom-protection",
                mode="classroom_cooldown",
                cooldown_until=datetime.now(UTC) + timedelta(minutes=2),
            )
        )
        database.commit()
    monkeypatch.setattr("sys.argv", ["pathlab-admin", "deployment-check"])

    with pytest.raises(SystemExit) as captured:
        main()

    assert captured.value.code == (
        "Deployment blocked: Classroom protection is classroom_cooldown"
    )


def test_reconcile_storage_is_noninteractive_and_prints_aggregate_only(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database_path = tmp_path / "reconcile-storage.sqlite3"
    data_root = tmp_path / "data"
    monkeypatch.setenv("PATHLAB_DATABASE_URL", f"sqlite:///{database_path}")
    monkeypatch.setenv("PATHLAB_DATA_ROOT", str(data_root))
    settings = Settings()
    create_schema(settings)
    with session_factory(settings)() as database:
        database.add(
            Slide(
                display_name="Private patient name",
                original_filename="private-patient-file.ome.tif",
                source_bytes=1,
                state=SlideState.QUEUED,
            )
        )
        database.commit()

    def fail_prompt(_: str) -> str:
        raise AssertionError("reconciliation must not prompt")

    monkeypatch.setattr("getpass.getpass", fail_prompt)
    monkeypatch.setattr("sys.argv", ["pathlab-admin", "reconcile-storage"])
    main()

    output = capsys.readouterr()
    assert output.out == "Storage reconciled: slides=1 derivatives=0 active=1\n"
    assert output.err == ""
    assert "Private patient name" not in output.out
    assert "private-patient-file.ome.tif" not in output.out
