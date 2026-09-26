import sys
from unittest.mock import Mock

import pytest
import uvicorn
from wsi_viewer.main import run


def test_api_cli_passes_bind_options_and_defaults(monkeypatch):
    start = Mock()
    monkeypatch.setattr(uvicorn, "run", start)
    for argv, host, port in [
        (["pathlab-api"], "0.0.0.0", 8000),
        (["pathlab-api", "--host", "127.0.0.1", "--port", "8123"], "127.0.0.1", 8123),
    ]:
        monkeypatch.setattr(sys, "argv", argv)
        run()
        start.assert_called_with("wsi_viewer.main:app", host=host, port=port)


@pytest.mark.parametrize("args,code", [(["--help"], 0), (["--bogus"], 2), (["--port", "65536"], 2)])
def test_api_cli_help_and_invalid_arguments_do_not_start_server(monkeypatch, args, code):
    start = Mock()
    monkeypatch.setattr(uvicorn, "run", start)
    monkeypatch.setattr(sys, "argv", ["pathlab-api", *args])
    with pytest.raises(SystemExit) as stopped:
        run()
    assert stopped.value.code == code
    start.assert_not_called()
