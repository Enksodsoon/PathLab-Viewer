import hashlib
import json
from pathlib import Path

import pytest
from wsi_viewer import cli
from wsi_viewer.config import Settings


@pytest.mark.parametrize(
    "mode", ["success", "copy_failure", "replace_failure", "cleanup_denied", "source_is_staging"]
)
def test_study_model_install_cleanup_preserves_existing_model_and_source(
    tmp_path: Path,
    monkeypatch,
    caplog,
    capsys,
    mode: str,
) -> None:
    payload = b"synthetic model"
    source = tmp_path / "synthetic.onnx"
    source.write_bytes(payload)
    manifest = {
        "assetFile": "synthetic-model.onnx",
        "artifactBytes": len(payload),
        "artifactSha256": hashlib.sha256(payload).hexdigest(),
    }
    (tmp_path / "trace_sim_release.json").write_text(json.dumps(manifest), encoding="utf-8")
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'model.sqlite3'}", data_root=tmp_path / "data"
    )
    monkeypatch.setattr(cli, "__file__", str(tmp_path / "cli.py"))
    monkeypatch.setattr(cli, "Settings", lambda: settings)
    monkeypatch.setattr(
        cli.sys, "argv", ["wsi-viewer", "install-study-model", "--artifact", str(source)]
    )
    target = settings.data_root / "private" / "study-models" / manifest["assetFile"]
    target.parent.mkdir(parents=True)
    target.write_bytes(b"previous installed model")
    staging = target.with_suffix(target.suffix + ".installing")
    if mode == "source_is_staging":
        source = staging
        source.write_bytes(payload)
        monkeypatch.setattr(
            cli.sys, "argv", ["wsi-viewer", "install-study-model", "--artifact", str(source)]
        )
    if mode in {"copy_failure", "cleanup_denied"}:

        def fail_copy(source_file, destination):
            destination.write(b"partial model")
            raise OSError("synthetic model copy failure")

        monkeypatch.setattr(cli.shutil, "copyfileobj", fail_copy)
    if mode == "replace_failure":

        def fail_replace(*args):
            raise PermissionError("synthetic model replace failure")

        monkeypatch.setattr(cli.os, "replace", fail_replace)
    if mode == "cleanup_denied":
        unlink = Path.unlink

        def deny_cleanup(path, *args, **kwargs):
            if path == staging:
                raise PermissionError("synthetic staging cleanup denial")
            return unlink(path, *args, **kwargs)

        monkeypatch.setattr(Path, "unlink", deny_cleanup)
    if mode == "source_is_staging":
        with pytest.raises(SystemExit, match="staging path"):
            cli.main()
        assert target.read_bytes() == b"previous installed model"
    elif mode == "success":
        cli.main()
        assert target.read_bytes() == payload
        assert "Installed synthetic-model.onnx" in capsys.readouterr().out
    else:
        with pytest.raises(OSError, match="synthetic model (copy|replace) failure"):
            cli.main()
        assert target.read_bytes() == b"previous installed model"
        assert "Installed" not in capsys.readouterr().out
    assert source.read_bytes() == payload
    assert staging.exists() == (mode in {"cleanup_denied", "source_is_staging"})
    if mode == "cleanup_denied":
        assert staging.read_bytes() == b"partial model"
        assert "STUDY_MODEL_STAGING_CLEANUP_FAILED" in caplog.text
