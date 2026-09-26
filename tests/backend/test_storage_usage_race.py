import os
from pathlib import Path

import pytest
from wsi_viewer.storage import StorageLayout


def test_usage_skips_only_files_removed_after_real_enumeration(tmp_path, monkeypatch):
    survivor = tmp_path / "source.ome.tif"
    survivor.write_bytes(b"surviving source")
    cache = tmp_path / "cache.jpg"
    cache.write_bytes(b"evicted tile")
    real_walk = os.walk
    enumerated = []

    def evict_after_enumeration(root):
        for directory, directories, files in real_walk(root):
            enumerated.extend(files)
            if cache.name in files:
                cache.unlink()
            yield directory, directories, files

    monkeypatch.setattr("wsi_viewer.storage.os.walk", evict_after_enumeration)
    assert StorageLayout(tmp_path).usage() == len(b"surviving source")
    assert cache.name in enumerated
    assert not cache.exists()

    real_stat = Path.stat
    for error in (PermissionError("denied"), OSError("disk failure")):
        def failed_stat(path, *args, failure=error, **kwargs):
            if path == survivor:
                raise failure
            return real_stat(path, *args, **kwargs)

        with monkeypatch.context() as context:
            context.setattr(Path, "stat", failed_stat)
            with pytest.raises(type(error), match=str(error)):
                StorageLayout(tmp_path).usage()
