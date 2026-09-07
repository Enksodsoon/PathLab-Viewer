import hmac
from datetime import UTC, datetime, timedelta
from io import StringIO
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, select, text
from wsi_viewer.cli import (
    RUNTIME_GUARD_PREDECESSOR_REVISIONS,
    _build_parser,
    _read_password,
    main,
)
from wsi_viewer.config import Settings
from wsi_viewer.database import create_schema, engine_for, session_factory
from wsi_viewer.domain import SlideState
from wsi_viewer.models import (
    ClassroomSession,
    DesktopCredential,
    Job,
    PasswordRecoveryCode,
    RuntimeGuard,
    Session,
    Slide,
    User,
)
from wsi_viewer.security import hash_password, recovery_code_hash, verify_password


def test_read_password_from_stdin(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("sys.stdin", StringIO("generated-password\n"))

    password = _read_password(True)
    if not hmac.compare_digest(password, "generated-password"):
        pytest.fail("Password read from stdin did not match")


def test_reject_empty_password_from_stdin(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("sys.stdin", StringIO("\n"))

    with pytest.raises(SystemExit, match="Password must not be empty"):
        _read_password(True)


def _configure_cli_database(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Settings:
    database_path = tmp_path / "cli-credentials.sqlite3"
    monkeypatch.setenv("PATHLAB_DATABASE_URL", f"sqlite:///{database_path}")
    monkeypatch.setenv("PATHLAB_DATA_ROOT", str(tmp_path))
    settings = Settings()
    create_schema(settings)
    return settings


def test_create_admin_rejects_blank_normalized_username_before_write(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = _configure_cli_database(tmp_path, monkeypatch)
    monkeypatch.setattr("sys.stdin", StringIO("valid admin passphrase\n"))
    monkeypatch.setattr(
        "sys.argv",
        ["pathlab-admin", "create-admin", "--username", "   ", "--password-stdin"],
    )

    with pytest.raises(SystemExit, match="Username must not be empty"):
        main()

    with session_factory(settings)() as database:
        assert database.scalar(select(User)) is None


def test_create_admin_reports_invalid_password_without_writing_user(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = _configure_cli_database(tmp_path, monkeypatch)
    monkeypatch.setattr("sys.stdin", StringIO("short\n"))
    monkeypatch.setattr(
        "sys.argv",
        ["pathlab-admin", "create-admin", "--username", "admin", "--password-stdin"],
    )

    with pytest.raises(SystemExit, match="Admin password must contain at least 12 characters"):
        main()

    with session_factory(settings)() as database:
        assert database.scalar(select(User)) is None


def test_create_and_reset_admin_use_normalized_username_and_valid_stdin_password(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = _configure_cli_database(tmp_path, monkeypatch)
    monkeypatch.setattr("sys.stdin", StringIO("initial admin passphrase\n"))
    monkeypatch.setattr(
        "sys.argv",
        ["pathlab-admin", "create-admin", "--username", "  AdMiN  ", "--password-stdin"],
    )
    main()

    with session_factory(settings)() as database:
        user = database.scalar(select(User))
        assert user is not None
        assert user.username == "admin"
        assert verify_password(user.password_hash, "initial admin passphrase")

    monkeypatch.setattr("sys.stdin", StringIO("replacement admin passphrase\n"))
    monkeypatch.setattr(
        "sys.argv",
        ["pathlab-admin", "reset-password", "--username", " ADMIN ", "--password-stdin"],
    )
    main()

    with session_factory(settings)() as database:
        user = database.scalar(select(User))
        assert user is not None
        assert user.username == "admin"
        assert verify_password(user.password_hash, "replacement admin passphrase")


def test_reset_admin_reports_invalid_password_without_changing_credentials(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = _configure_cli_database(tmp_path, monkeypatch)
    with session_factory(settings)() as database:
        database.add(User(username="admin", password_hash=hash_password("existing password")))
        database.commit()

    monkeypatch.setattr("sys.stdin", StringIO("short\n"))
    monkeypatch.setattr(
        "sys.argv",
        ["pathlab-admin", "reset-password", "--username", "admin", "--password-stdin"],
    )

    with pytest.raises(SystemExit, match="Admin password must contain at least 12 characters"):
        main()

    with session_factory(settings)() as database:
        user = database.scalar(select(User))
        assert user is not None
        assert verify_password(user.password_hash, "existing password")


def test_reset_admin_preserves_lone_legacy_mixed_case_identity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = _configure_cli_database(tmp_path, monkeypatch)
    with session_factory(settings)() as database:
        database.add(User(username="AdMiN", password_hash=hash_password("legacy password one")))
        database.commit()

    for supplied_username, replacement in [
        ("AdMiN", "replacement password one"),
        (" admin ", "replacement password two"),
    ]:
        monkeypatch.setattr("sys.stdin", StringIO(f"{replacement}\n"))
        monkeypatch.setattr(
            "sys.argv",
            [
                "pathlab-admin",
                "reset-password",
                "--username",
                supplied_username,
                "--password-stdin",
            ],
        )
        main()

        with session_factory(settings)() as database:
            user = database.scalar(select(User).where(User.username == "AdMiN"))
            assert user is not None
            assert verify_password(user.password_hash, replacement)


def test_reset_admin_exact_match_wins_between_legacy_collisions_and_revokes_only_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = _configure_cli_database(tmp_path, monkeypatch)
    now = datetime(2026, 9, 7, 8, 0, tzinfo=UTC)
    with session_factory(settings)() as database:
        mixed = User(username="AdMiN", password_hash=hash_password("mixed original password"))
        lower = User(username="admin", password_hash=hash_password("lower original password"))
        database.add_all([mixed, lower])
        database.flush()
        database.add_all(
            [
                Session(
                    id="m" * 64,
                    user_id=mixed.id,
                    csrf_token="mixed-csrf",
                    expires_at=now + timedelta(hours=1),
                ),
                Session(
                    id="l" * 64,
                    user_id=lower.id,
                    csrf_token="lower-csrf",
                    expires_at=now + timedelta(hours=1),
                ),
                DesktopCredential(
                    id="M" * 64,
                    user_id=mixed.id,
                    device_name="Mixed case device",
                    scopes=["desktop:ingest"],
                    expires_at=now + timedelta(days=1),
                ),
                DesktopCredential(
                    id="L" * 64,
                    user_id=lower.id,
                    device_name="Lower case device",
                    scopes=["desktop:ingest"],
                    expires_at=now + timedelta(days=1),
                ),
            ]
        )
        database.commit()

    monkeypatch.setattr("sys.stdin", StringIO("mixed replacement password\n"))
    monkeypatch.setattr(
        "sys.argv",
        ["pathlab-admin", "reset-password", "--username", "AdMiN", "--password-stdin"],
    )
    main()

    with session_factory(settings)() as database:
        mixed = database.scalar(select(User).where(User.username == "AdMiN"))
        lower = database.scalar(select(User).where(User.username == "admin"))
        assert mixed is not None and lower is not None
        assert verify_password(mixed.password_hash, "mixed replacement password")
        assert verify_password(lower.password_hash, "lower original password")
        assert database.get(Session, "m" * 64) is None
        assert database.get(Session, "l" * 64) is not None
        assert database.get(DesktopCredential, "M" * 64).revoked_at is not None
        assert database.get(DesktopCredential, "L" * 64).revoked_at is None


def test_reset_admin_rejects_ambiguous_normalized_fallback_without_changes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = _configure_cli_database(tmp_path, monkeypatch)
    with session_factory(settings)() as database:
        database.add_all(
            [
                User(username="AdMiN", password_hash=hash_password("mixed original password")),
                User(username="admin", password_hash=hash_password("lower original password")),
            ]
        )
        database.commit()

    monkeypatch.setattr("sys.stdin", StringIO("ambiguous replacement password\n"))
    monkeypatch.setattr(
        "sys.argv",
        ["pathlab-admin", "reset-password", "--username", " ADMIN ", "--password-stdin"],
    )

    with pytest.raises(SystemExit, match="Administrator username is ambiguous"):
        main()

    with session_factory(settings)() as database:
        mixed = database.scalar(select(User).where(User.username == "AdMiN"))
        lower = database.scalar(select(User).where(User.username == "admin"))
        assert mixed is not None and lower is not None
        assert verify_password(mixed.password_hash, "mixed original password")
        assert verify_password(lower.password_hash, "lower original password")


def test_create_admin_rejects_normalized_duplicate_of_legacy_account(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = _configure_cli_database(tmp_path, monkeypatch)
    with session_factory(settings)() as database:
        database.add(User(username="AdMiN", password_hash=hash_password("legacy password")))
        database.commit()

    monkeypatch.setattr("sys.stdin", StringIO("new administrator password\n"))
    monkeypatch.setattr(
        "sys.argv",
        ["pathlab-admin", "create-admin", "--username", " admin ", "--password-stdin"],
    )

    with pytest.raises(SystemExit, match="Administrator already exists"):
        main()

    with session_factory(settings)() as database:
        assert list(database.scalars(select(User.username))) == ["AdMiN"]


def test_issue_recovery_code_preserves_exact_legacy_whitespace_identity(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    settings = _configure_cli_database(tmp_path, monkeypatch)
    with session_factory(settings)() as database:
        spaced = User(
            username="  Admin  ", password_hash=hash_password("legacy spaced password")
        )
        canonical = User(
            username="admin", password_hash=hash_password("canonical account password")
        )
        database.add_all([spaced, canonical])
        database.commit()
        spaced_id = spaced.id
        canonical_id = canonical.id

    monkeypatch.setattr(
        "sys.argv", ["pathlab-admin", "issue-recovery-code", "--username", "  Admin  "]
    )
    main()
    capsys.readouterr()

    with session_factory(settings)() as database:
        stored = database.scalar(select(PasswordRecoveryCode))
        assert stored is not None
        assert stored.user_id == spaced_id
        assert stored.user_id != canonical_id


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


@pytest.mark.parametrize("revision", sorted(RUNTIME_GUARD_PREDECESSOR_REVISIONS))
def test_deployment_check_accepts_known_pre_runtime_guard_schemas(
    revision: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database_path = tmp_path / f"deployment-check-{revision}.sqlite3"
    monkeypatch.setenv("PATHLAB_DATABASE_URL", f"sqlite:///{database_path}")
    monkeypatch.setenv("PATHLAB_DATA_ROOT", str(tmp_path))
    settings = Settings()
    command.upgrade(Config("alembic.ini"), revision)
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


def test_deployment_check_reconciles_expired_and_synthetic_classroom_sessions(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_path = tmp_path / "deployment-check-expired-classroom.sqlite3"
    monkeypatch.setenv("PATHLAB_DATABASE_URL", f"sqlite:///{database_path}")
    monkeypatch.setenv("PATHLAB_DATA_ROOT", str(tmp_path))
    settings = Settings()
    create_schema(settings)
    with session_factory(settings)() as database:
        database.add(
            ClassroomSession(
                join_code_hash="b" * 64,
                expires_at=datetime.now(UTC) - timedelta(hours=2),
                status="active",
            )
        )
        database.commit()
    monkeypatch.setattr("sys.argv", ["pathlab-admin", "deployment-check"])

    main()

    with session_factory(settings)() as database:
        session = database.scalar(
            select(ClassroomSession).where(ClassroomSession.join_code_hash == "b" * 64)
        )
        assert session is not None
        assert session.status == "ended"


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
