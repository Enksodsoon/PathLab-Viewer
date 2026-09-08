import hashlib
import hmac
import importlib.util
import json
import os
import tarfile
from pathlib import Path
from types import SimpleNamespace

import pytest


def _load_manifest_module():
    path = Path("deploy/scripts/postgres_backup_manifest.py")
    spec = importlib.util.spec_from_file_location("postgres_backup_manifest", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _backup(tmp_path: Path) -> Path:
    backup = tmp_path / "backup"
    (backup / "database").mkdir(parents=True)
    (backup / "database" / "pathlab.dump").write_bytes(b"PGDMP synthetic")
    source = tmp_path / "files"
    for root in ("originals", "private", "public"):
        directory = source / root
        directory.mkdir(parents=True)
        (directory / "proof.txt").write_text(root, encoding="utf-8")
    with tarfile.open(backup / "files.tar.gz", "w:gz") as archive:
        for root in ("originals", "private", "public"):
            archive.add(source / root, arcname=root)
    return backup


def test_signed_manifest_binds_dump_files_release_and_revision(tmp_path: Path) -> None:
    module = _load_manifest_module()
    backup = _backup(tmp_path)
    key = "synthetic-postgres-backup-signing-key"
    manifest = module.create_manifest(
        backup,
        release_sha="a" * 40,
        schema_revision="20260821_0021",
        database_name="pathlab",
        signing_key=key,
        created_at="2026-08-21T00:00:00Z",
    )
    (backup / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    verified = module.verify_manifest(backup, signing_key=key)

    assert verified["releaseSha"] == "a" * 40
    assert verified["schemaRevision"] == "20260821_0021"
    assert verified["database"]["format"] == "pg_dump-custom"
    assert verified["privateFiles"]["roots"] == ["originals", "private", "public"]
    unsigned = dict(manifest)
    signature = unsigned.pop("signature")
    expected = hmac.new(key.encode(), module._canonical_json(unsigned), hashlib.sha256).hexdigest()
    assert signature == {"algorithm": "hmac-sha256", "value": expected}


def test_isolated_restore_preserves_assessment_grant_bytes_and_hardlinks(tmp_path: Path) -> None:
    module = _load_manifest_module()
    backup = _backup(tmp_path)
    source = tmp_path / "files"
    grant = source / "delivery/assessment/synthetic-administration/slide/version/slide.dzi"
    grant.parent.mkdir(parents=True)
    os.link(source / "private/proof.txt", grant)
    with tarfile.open(backup / "files.tar.gz", "w:gz") as archive:
        for root in ("originals", "private", "public", "delivery"):
            archive.add(source / root, arcname=root)
    key = "synthetic-postgres-backup-signing-key"
    manifest = module.create_manifest(
        backup,
        release_sha="a" * 40,
        schema_revision="test_revision",
        database_name="pathlab",
        signing_key=key,
    )
    (backup / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    destination = tmp_path / "restored"
    destination.mkdir()

    result = module.restore_files(backup, destination, signing_key=key)

    restored_grant = destination / grant.relative_to(source)
    assert restored_grant.read_bytes() == b"private"
    assert restored_grant.samefile(destination / "private/proof.txt")
    assert result["archiveRoots"] == ["delivery", "originals", "private", "public"]
    assert result["filesIntegrity"] == "restored"
    assert result["fileCount"] == 4
    assert not (backup / "delivery").exists()


@pytest.mark.parametrize("unsafe", ["../outside", "/outside", "delivery/../outside"])
def test_archive_rejects_unsafe_grant_paths(tmp_path: Path, unsafe: str) -> None:
    module = _load_manifest_module()
    backup = _backup(tmp_path)
    with tarfile.open(backup / "files.tar.gz", "w:gz") as archive:
        entry = tarfile.TarInfo(unsafe)
        entry.type = tarfile.DIRTYPE
        archive.addfile(entry)
    with pytest.raises(module.BackupManifestError):
        module._archive_roots(backup / "files.tar.gz")


def test_file_restore_refuses_nonempty_destination_and_low_space(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = _load_manifest_module()
    backup = _backup(tmp_path)
    key = "synthetic-postgres-backup-signing-key"
    manifest = module.create_manifest(
        backup,
        release_sha="a" * 40,
        schema_revision="test_revision",
        database_name="pathlab",
        signing_key=key,
    )
    (backup / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    destination = tmp_path / "restored"
    destination.mkdir()
    sentinel = destination / "keep.txt"
    sentinel.write_text("retain")
    with pytest.raises(module.BackupManifestError, match="empty real directory"):
        module.restore_files(backup, destination, signing_key=key)
    assert sentinel.read_text() == "retain"
    sentinel.unlink()
    monkeypatch.setattr(module.shutil, "disk_usage", lambda _: SimpleNamespace(free=10))
    with pytest.raises(module.BackupManifestError, match="insufficient space"):
        module.restore_files(backup, destination, signing_key=key)
    assert not list(destination.iterdir())


def test_manifest_verification_rejects_mutated_payload(tmp_path: Path) -> None:
    module = _load_manifest_module()
    backup = _backup(tmp_path)
    key = "synthetic-postgres-backup-signing-key"
    manifest = module.create_manifest(
        backup,
        release_sha="b" * 40,
        schema_revision="20260821_0021",
        database_name="pathlab",
        signing_key=key,
    )
    (backup / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    (backup / "database" / "pathlab.dump").write_bytes(b"mutated")

    with pytest.raises(module.BackupManifestError, match="checksum mismatch"):
        module.verify_manifest(backup, signing_key=key)


def test_manifest_verification_rejects_undeclared_fields(tmp_path: Path) -> None:
    module = _load_manifest_module()
    backup = _backup(tmp_path)
    key = "synthetic-postgres-backup-signing-key"
    manifest = module.create_manifest(
        backup,
        release_sha="b" * 40,
        schema_revision="20260821_0021",
        database_name="pathlab",
        signing_key=key,
    )
    manifest["unexpected"] = True
    unsigned = dict(manifest)
    unsigned.pop("signature")
    manifest["signature"]["value"] = module._sign(unsigned, key)
    (backup / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(module.BackupManifestError, match="fields are invalid"):
        module.verify_manifest(backup, signing_key=key)


def test_manifest_rejects_archive_with_unapproved_root(tmp_path: Path) -> None:
    module = _load_manifest_module()
    backup = _backup(tmp_path)
    source = tmp_path / "unexpected"
    source.mkdir()
    with tarfile.open(backup / "files.tar.gz", "w:gz") as archive:
        archive.add(source, arcname="backups")

    with pytest.raises(module.BackupManifestError, match="invalid root"):
        module.create_manifest(
            backup,
            release_sha="c" * 40,
            schema_revision="20260821_0021",
            database_name="pathlab",
            signing_key="synthetic-postgres-backup-signing-key",
        )


def test_postgres_scripts_are_fail_closed_and_disposable() -> None:
    backup = Path("deploy/scripts/backup-postgres.sh").read_text(encoding="utf-8")
    drill = Path("deploy/scripts/verify-postgres-restore-drill.sh").read_text(encoding="utf-8")

    assert "pg_dump --format=custom" in backup
    assert "PATHLAB_BACKUP_SIGNING_KEY is required" in backup
    assert "PATHLAB_RELEASE_SHA must be an exact lowercase release SHA" in backup
    assert 'server_version" == "180006"' in backup
    assert "pg_database_size(current_database())" in backup
    assert "Backup refused: insufficient space" in backup
    assert "PATHLAB_POSTGRES_CONTAINER is invalid" in backup
    assert "archive_roots=(originals private public)" in backup
    assert "archive_roots+=(delivery)" in backup
    assert '--directory "$data_dir" "${archive_roots[@]}"' in backup
    assert "cache/ome-tiles" not in backup
    assert "pg_restore --exit-on-error" in drill
    assert "createdb" in drill
    assert "dropdb --if-exists --force" in drill
    assert "trap cleanup EXIT" in drill
    assert "SELECT version_num FROM alembic_version" in drill
    assert 'server_version" == "180006"' in drill
    assert "PATHLAB_POSTGRES_CONTAINER" in drill
    assert 'restore-files "$backup" "$files_drill"' in drill


def test_database_aware_backup_and_postgres_rollback_preserve_failed_database() -> None:
    backup = Path("deploy/scripts/backup-current-database.sh").read_text(encoding="utf-8")
    verify = Path("deploy/scripts/verify-current-restore-drill.sh").read_text(encoding="utf-8")
    rollback = Path("deploy/scripts/restore-deploy-rollback-postgres.sh").read_text(
        encoding="utf-8"
    )
    selector = Path("deploy/scripts/restore-deploy-rollback-database.sh").read_text(
        encoding="utf-8"
    )

    assert "backup.sh" in backup
    assert "backup-postgres.sh" in backup
    assert "PATHLAB_POSTGRES_BACKUP_SIGNING_KEY_FILE" in backup
    assert "verify_restore_drill.py" in verify
    assert "verify-postgres-restore-drill.sh" in verify
    assert "postgres_backup_manifest.py" in rollback
    assert "restored_revision" in rollback
    assert "manifest_revision" in rollback
    assert "pg_terminate_backend" in rollback
    assert "RENAME TO" in rollback
    assert "pg_restore --exit-on-error" in rollback
    assert "restore_failed_database" in rollback
    assert "application_services+=(assessment)" in rollback
    assert 'stop "${application_services[@]}"' in rollback
    assert "failed database preserved" in rollback
    assert "restore-deploy-rollback-postgres.sh" in selector


def test_cutover_evidence_script_is_staging_only_and_composes_existing_proofs() -> None:
    cutover = Path("deploy/scripts/verify-postgres-cutover.sh").read_text(encoding="utf-8")
    workflow = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")

    assert 'PATHLAB_CUTOVER_ENVIRONMENT:-}" != "staging"' in cutover
    assert "postgres-cutover-source-check" in cutover
    assert "migrate-sqlite-to-postgres" in cutover
    assert "--target-password-file" in cutover
    assert "PATHLAB_POSTGRES_TARGET_URL must contain a username and no password" in cutover
    assert "deployment-check" in cutover
    assert "backup-postgres.sh" in cutover
    assert "verify-postgres-restore-drill.sh" in cutover
    assert 'state="FAILED_TERMINAL"' in cutover
    assert 'state="SUCCEEDED"' in cutover
    assert "status.json" in workflow
    assert 'status["state"] == "SUCCEEDED"' in workflow
    assert "env -u PATHLAB_DATABASE_PASSWORD_FILE" in workflow
