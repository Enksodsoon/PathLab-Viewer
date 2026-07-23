import hashlib
import os
import shutil
import subprocess
import tarfile
from pathlib import Path

import pytest


@pytest.mark.skipif(shutil.which("tar") is None, reason="tar is unavailable")
def test_backup_archive_and_restore_preserve_public_private_hardlinks(
    tmp_path: Path,
) -> None:
    data = tmp_path / "data"
    private = data / "private" / "slide-1"
    public = data / "public" / "public-1"
    original = data / "originals" / "slide-1" / "source.ome.tif"
    private.mkdir(parents=True)
    public.mkdir(parents=True)
    original.parent.mkdir(parents=True)
    original.write_bytes(b"private-original")
    private_descriptor = private / "slide.dzi"
    private_tile = private / "0_0.jpeg"
    private_descriptor.write_bytes(b"<Image />")
    private_tile.write_bytes(b"jpeg-payload")
    os.link(private_descriptor, public / "slide.dzi")
    os.link(private_tile, public / "0_0.jpeg")
    archive = tmp_path / "files.tar.gz"

    subprocess.run(
        [
            "tar",
            "--create",
            "--gzip",
            "--file",
            str(archive),
            "--directory",
            str(data),
            "originals",
            "private",
            "public",
        ],
        check=True,
    )

    with tarfile.open(archive, "r:gz") as stored:
        public_tile = stored.getmember("public/public-1/0_0.jpeg")
        assert public_tile.islnk()
        assert public_tile.linkname == "private/slide-1/0_0.jpeg"
        assert "public/public-1/source.ome.tif" not in stored.getnames()

    restored = tmp_path / "restored"
    restored.mkdir()
    subprocess.run(
        [
            "tar",
            "--extract",
            "--gzip",
            "--file",
            str(archive),
            "--directory",
            str(restored),
        ],
        check=True,
    )

    restored_private = restored / "private" / "slide-1" / "0_0.jpeg"
    restored_public = restored / "public" / "public-1" / "0_0.jpeg"
    assert restored_private.stat().st_ino == restored_public.stat().st_ino
    assert (
        hashlib.sha256(restored_private.read_bytes()).digest()
        == hashlib.sha256(private_tile.read_bytes()).digest()
    )
    assert (restored / "originals" / "slide-1" / "source.ome.tif").read_bytes() == (
        b"private-original"
    )


def test_backup_and_restore_scripts_keep_integrity_and_recovery_guards() -> None:
    backup = Path("deploy/scripts/backup.sh").read_text(encoding="utf-8")
    restore = Path("deploy/scripts/restore.sh").read_text(encoding="utf-8")

    assert '--directory "$data_dir" originals private public' in backup
    assert "sha256sum" in backup
    assert "sha256sum --check SHA256SUMS" in restore
    assert ".before-restore-" in restore
