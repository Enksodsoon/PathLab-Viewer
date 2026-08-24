import hashlib
import importlib.util
import os
import shutil
import sqlite3
import subprocess
import sys
import tarfile
from pathlib import Path

import pytest
from wsi_viewer.config import Settings
from wsi_viewer.database import create_schema, session_factory
from wsi_viewer.domain import SlideState
from wsi_viewer.models import Annotation, AnnotationLayer, AnnotationRevision, Slide

BASH = Path(r"C:\Program Files\Git\bin\bash.exe")


def _bash_path(path: Path) -> str:
    resolved = path.resolve().as_posix()
    return f"/{resolved[0].lower()}{resolved[2:]}"


def _load_restore_drill():
    path = Path("deploy/scripts/verify_restore_drill.py")
    spec = importlib.util.spec_from_file_location("verify_restore_drill", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write_backup_checksums(backup: Path) -> None:
    entries = []
    for relative in (Path("database/pathlab.sqlite3"), Path("files.tar.gz")):
        digest = hashlib.sha256((backup / relative).read_bytes()).hexdigest()
        entries.append(f"{digest}  {relative.as_posix()}")
    with (backup / "SHA256SUMS").open("w", encoding="utf-8", newline="\n") as manifest:
        manifest.write("\n".join(entries) + "\n")


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
    retention = Path("deploy/scripts/prune-backups.sh").read_text(encoding="utf-8")
    restore = Path("deploy/scripts/restore.sh").read_text(encoding="utf-8")

    assert '--directory "$data_dir" originals private public' in backup
    assert "umask 077" in backup
    assert "install -d -m 700" in backup
    assert "sha256sum" in backup
    assert "sha256sum --check SHA256SUMS" in restore
    assert 'extractall(destination, filter="data")' in restore
    assert "tar --extract" not in restore
    assert ".before-restore-" in restore
    assert "cache/ome-tiles" not in backup
    assert "pathlab-tiles --purge-cache" in restore
    assert "docker compose stop caddy api classroom tile-service tusd worker" in restore
    assert 'staged="${data_dir}.restore-staged-${timestamp}"' in restore
    assert 'mv "$staged" "$data_dir"' in restore
    assert 'mv "${recovery}/backups" "${data_dir}/backups"' in restore
    assert "docker compose exec -T api" not in backup
    assert "docker compose run --rm --no-deps --entrypoint python api" in backup
    assert 'PATHLAB_BACKUP_RETENTION_COUNT:-5' in backup
    assert 'flock -n 9' in backup
    assert 'trap cleanup_incomplete_backup EXIT' in backup
    assert 'sha256sum --check --status SHA256SUMS' in backup
    assert 'prune-backups.sh' in backup
    assert 'readlink -f' in retention
    assert 'sha256sum --check --status SHA256SUMS' in retention


@pytest.mark.skipif(not BASH.exists(), reason="Git Bash is required")
def test_backup_retention_keeps_newest_verified_backups_only(tmp_path: Path) -> None:
    backup_root = tmp_path / "backups"
    backup_root.mkdir()
    names = [f"pathlab-202608{day:02d}T010203Z" for day in range(1, 8)]
    for name in names:
        backup = backup_root / name
        (backup / "database").mkdir(parents=True)
        (backup / "database" / "pathlab.sqlite3").write_bytes(name.encode())
        (backup / "files.tar.gz").write_bytes(b"archive")
        _write_backup_checksums(backup)
    invalid = backup_root / "pathlab-20260808T010203Z"
    invalid.mkdir()
    (backup_root / "pathlab-not-a-timestamp").mkdir()

    result = subprocess.run(
        [
            str(BASH),
            _bash_path(Path("deploy/scripts/prune-backups.sh")),
            _bash_path(backup_root),
            "5",
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert sorted(path.name for path in backup_root.iterdir() if path.name in names) == names[-5:]
    assert invalid.exists()
    assert (backup_root / "pathlab-not-a-timestamp").exists()


@pytest.mark.skipif(not BASH.exists(), reason="Git Bash is required")
def test_deploy_rollback_restores_verified_database_and_preserves_failed_revision(
    tmp_path: Path,
) -> None:
    data = tmp_path / "data"
    database_dir = data / "database"
    backup = data / "backups" / "pathlab-test"
    backup_database_dir = backup / "database"
    database_dir.mkdir(parents=True)
    backup_database_dir.mkdir(parents=True)

    live_database = database_dir / "pathlab.sqlite3"
    backup_database = backup_database_dir / "pathlab.sqlite3"
    for path, revision in (
        (live_database, "20260822_0022"),
        (backup_database, "20260821_0021"),
    ):
        database = sqlite3.connect(path)
        try:
            database.execute("CREATE TABLE alembic_version (version_num TEXT NOT NULL)")
            database.execute("INSERT INTO alembic_version VALUES (?)", (revision,))
            database.commit()
        finally:
            database.close()
    with tarfile.open(backup / "files.tar.gz", "w:gz"):
        pass
    _write_backup_checksums(backup)

    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    docker_log = tmp_path / "docker.log"
    for command in ("chown", "chmod", "sync"):
        executable = fake_bin / command
        executable.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
        executable.chmod(0o755)
    python3 = fake_bin / "python3"
    python3.write_text(
        "#!/usr/bin/env bash\n"
        f"exec '{_bash_path(Path(sys.executable))}' \"$@\"\n",
        encoding="utf-8",
    )
    python3.chmod(0o755)
    docker = fake_bin / "docker"
    docker.write_text(
        "#!/usr/bin/env bash\n"
        f"printf '%s\\n' \"$*\" >> '{_bash_path(docker_log)}'\n",
        encoding="utf-8",
    )
    docker.chmod(0o755)
    compose_env = tmp_path / "deploy.env"
    compose_env.write_text("PATHLAB_DATABASE_ENGINE=sqlite\n", encoding="utf-8")
    env = os.environ.copy()
    env.update(
        {
            "PATH": f"{_bash_path(fake_bin)}:{env['PATH']}",
            "PATHLAB_DATA_DIR": _bash_path(data),
            "PATHLAB_BACKUP_DIR": _bash_path(data / "backups"),
            "PATHLAB_COMPOSE_ENV_FILE": _bash_path(compose_env),
        }
    )
    result = subprocess.run(
        [
            str(BASH),
            _bash_path(Path("deploy/scripts/restore-deploy-rollback-database.sh")),
            _bash_path(backup),
        ],
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    with sqlite3.connect(live_database) as database:
        assert database.execute("SELECT version_num FROM alembic_version").fetchone() == (
            "20260821_0021",
        )
    preserved = list(database_dir.glob("pathlab.sqlite3.failed-deploy-*"))
    assert len(preserved) == 1
    with sqlite3.connect(preserved[0]) as database:
        assert database.execute("SELECT version_num FROM alembic_version").fetchone() == (
            "20260822_0022",
        )
    docker_command = docker_log.read_text(encoding="utf-8").strip()
    assert "compose --project-directory" in docker_command
    assert "-f " in docker_command
    assert docker_command.endswith("stop caddy api classroom tile-service tusd worker")


def test_restore_drill_streams_backup_with_bounded_scratch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    verifier = _load_restore_drill()
    backup = tmp_path / "backup"
    (backup / "database").mkdir(parents=True)
    database_path = backup / "database" / "pathlab.sqlite3"
    with sqlite3.connect(database_path) as database:
        database.execute("CREATE TABLE proof (value TEXT NOT NULL)")
        database.execute("INSERT INTO proof VALUES ('restored')")
    source = tmp_path / "source"
    (source / "originals").mkdir(parents=True)
    (source / "private").mkdir()
    (source / "public").mkdir()
    (source / "public" / "proof.txt").write_text("restored", encoding="utf-8")
    with tarfile.open(backup / "files.tar.gz", "w:gz") as archive:
        for name in ("originals", "private", "public"):
            archive.add(source / name, arcname=name)
    _write_backup_checksums(backup)

    monkeypatch.setattr(Path, "read_bytes", lambda self: pytest.fail("unbounded read_bytes"))
    monkeypatch.setattr(
        tarfile.TarFile,
        "extractall",
        lambda *args, **kwargs: pytest.fail("full archive extraction is forbidden"),
    )
    result = verifier.verify_restore_drill(backup, scratch_root=tmp_path / "scratch")

    assert result == {"databaseIntegrity": "ok", "archiveRoots": ["originals", "private", "public"]}


def test_restore_drill_rejects_corrupt_database(tmp_path: Path) -> None:
    verifier = _load_restore_drill()
    backup = tmp_path / "backup"
    (backup / "database").mkdir(parents=True)
    (backup / "database" / "pathlab.sqlite3").write_bytes(b"not sqlite")
    with tarfile.open(backup / "files.tar.gz", "w:gz"):
        pass
    _write_backup_checksums(backup)

    with pytest.raises(verifier.RestoreDrillFailure):
        verifier.verify_restore_drill(backup, scratch_root=tmp_path / "scratch")


def test_restore_drill_uses_the_configured_data_volume(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    verifier = _load_restore_drill()
    data_root = tmp_path / "production-data"
    backup_root = data_root / "backups"
    backup_root.mkdir(parents=True)
    monkeypatch.setenv("PATHLAB_DATA_DIR", str(data_root))
    monkeypatch.setenv("PATHLAB_BACKUP_DIR", str(backup_root))
    monkeypatch.setenv("PATHLAB_RESTORE_DRILL_DIR", str(data_root / ".restore-drill"))

    approved_backup, approved_scratch = verifier._approved_restore_paths()

    assert approved_backup == backup_root.resolve()
    assert approved_scratch == (data_root / ".restore-drill").resolve()


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
