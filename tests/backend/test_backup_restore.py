import hashlib
import os
import shutil
import sqlite3
import subprocess
import tarfile
from pathlib import Path

import pytest
from wsi_viewer.config import Settings
from wsi_viewer.database import create_schema, session_factory
from wsi_viewer.domain import SlideState
from wsi_viewer.models import Annotation, AnnotationLayer, AnnotationRevision, Slide


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
    assert hashlib.sha256(restored_private.read_bytes()).digest() == hashlib.sha256(
        private_tile.read_bytes()
    ).digest()
    assert (restored / "originals" / "slide-1" / "source.ome.tif").read_bytes() == (
        b"private-original"
    )


def test_backup_and_restore_scripts_keep_integrity_and_recovery_guards() -> None:
    backup = Path("deploy/scripts/backup.sh").read_text(encoding="utf-8")
    restore = Path("deploy/scripts/restore.sh").read_text(encoding="utf-8")

    assert "--directory \"$data_dir\" originals private public" in backup
    assert "umask 077" in backup
    assert "install -d -m 700" in backup
    assert "sha256sum" in backup
    assert "sha256sum --check SHA256SUMS" in restore
    assert 'extractall(destination, filter="data")' in restore
    assert "tar --extract" not in restore
    assert ".before-restore-" in restore
    assert "cache/ome-tiles" not in backup
    assert "pathlab-tiles --purge-cache" in restore


def test_sqlite_backup_preserves_private_annotation_state(tmp_path: Path) -> None:
    source_path = tmp_path / "pathlab.sqlite3"
    backup_path = tmp_path / "backup.sqlite3"
    settings = Settings(
        database_url=f"sqlite:///{source_path}",
        data_root=tmp_path / "data",
    )
    create_schema(settings)
    with session_factory(settings)() as database:
        slide = Slide(
            id="backup-slide",
            display_name="Backup",
            original_filename="backup.ome.tif",
            source_bytes=1,
            state=SlideState.READY_PRIVATE,
            slide_metadata={"width": 100, "height": 100},
            annotation_version=2,
        )
        layer = AnnotationLayer(
            id="5e1a407e-c773-4782-9ab7-962485229894",
            slide_id=slide.id,
            name="Private annotations",
        )
        annotation = Annotation(
            id="e38e1283-dc44-4d55-8802-75e41111c665",
            slide_id=slide.id,
            layer_id=layer.id,
            geometry_type="point",
            geometry={"type": "point", "x": 10.0, "y": 20.0},
            style={
                "strokeColor": "#c43d3d",
                "fillColor": "#c43d3d",
                "strokeWidth": 2,
                "opacity": 0.35,
                "labelVisible": True,
            },
            annotation_metadata={
                "title": "Private label",
                "classification": "",
                "tags": [],
                "notes": "Private note",
            },
            bbox_min_x=10,
            bbox_min_y=20,
            bbox_max_x=10,
            bbox_max_y=20,
            vertex_count=1,
            version=1,
            mutation_id="cbe47918-c50b-4ff9-bd85-10141448a84d",
        )
        database.add(slide)
        database.commit()
        database.add(layer)
        database.commit()
        database.add(annotation)
        database.commit()
        database.add(
            AnnotationRevision(
                id="5b26bafe-9dc4-45d9-8bf8-bf1d9c26e703",
                annotation_id=annotation.id,
                version=1,
                layer_id=layer.id,
                geometry_type=annotation.geometry_type,
                geometry=annotation.geometry,
                style=annotation.style,
                annotation_metadata={
                    **annotation.annotation_metadata,
                    "title": "Private historical label",
                },
                bbox_min_x=annotation.bbox_min_x,
                bbox_min_y=annotation.bbox_min_y,
                bbox_max_x=annotation.bbox_max_x,
                bbox_max_y=annotation.bbox_max_y,
                vertex_count=annotation.vertex_count,
                mutation_id=annotation.mutation_id,
            )
        )
        database.commit()

    with (
        sqlite3.connect(source_path) as source,
        sqlite3.connect(backup_path) as target,
    ):
        source.backup(target)

    with sqlite3.connect(backup_path) as restored:
        assert restored.execute(
            "SELECT annotation_version FROM slides WHERE id = 'backup-slide'"
        ).fetchone() == (2,)
        assert restored.execute(
            "SELECT json_extract(annotation_metadata, '$.title') "
            "FROM annotations WHERE id = 'e38e1283-dc44-4d55-8802-75e41111c665'"
        ).fetchone() == ("Private label",)
        assert restored.execute(
            "SELECT json_extract(annotation_metadata, '$.title') "
            "FROM annotation_revisions "
            "WHERE id = '5b26bafe-9dc4-45d9-8bf8-bf1d9c26e703'"
        ).fetchone() == ("Private historical label",)
        assert restored.execute(
            "SELECT name || ':' || opacity FROM annotation_layers "
            "WHERE id = '5e1a407e-c773-4782-9ab7-962485229894'"
        ).fetchone() == ("Private annotations:1.0",)
