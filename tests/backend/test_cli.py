from io import StringIO

import pytest

from wsi_viewer.cli import _read_password


def test_read_password_from_stdin(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("sys.stdin", StringIO("generated-password\n"))

    assert _read_password(True) == "generated-password"


def test_reject_empty_password_from_stdin(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("sys.stdin", StringIO("\n"))

    with pytest.raises(SystemExit, match="Password must not be empty"):
        _read_password(True)
