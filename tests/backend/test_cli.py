import hmac
from io import StringIO
from pathlib import Path

import pytest
from sqlalchemy import select
from wsi_viewer.cli import _build_parser, _read_password, main
from wsi_viewer.config import Settings
from wsi_viewer.database import create_schema, session_factory
from wsi_viewer.models import PasswordRecoveryCode, User
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
