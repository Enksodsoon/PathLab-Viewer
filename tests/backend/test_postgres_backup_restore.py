import hashlib
import hmac
import importlib.util
import json
import tarfile
from pathlib import Path

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
    expected = hmac.new(
        key.encode(), module._canonical_json(unsigned), hashlib.sha256
    ).hexdigest()
    assert signature == {"algorithm": "hmac-sha256", "value": expected}


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
    drill = Path("deploy/scripts/verify-postgres-restore-drill.sh").read_text(
        encoding="utf-8"
    )

    assert "pg_dump --format=custom" in backup
    assert "PATHLAB_BACKUP_SIGNING_KEY is required" in backup
    assert "PATHLAB_RELEASE_SHA must be an exact lowercase release SHA" in backup
    assert 'server_version" == "180006"' in backup
    assert "pg_database_size(current_database())" in backup
    assert "Backup refused: insufficient space" in backup
    assert "PATHLAB_POSTGRES_CONTAINER is invalid" in backup
    assert '--directory "$data_dir" originals private public' in backup
    assert "cache/ome-tiles" not in backup
    assert "pg_restore --exit-on-error" in drill
    assert "createdb" in drill
    assert "dropdb --if-exists --force" in drill
    assert "trap cleanup EXIT" in drill
    assert "SELECT version_num FROM alembic_version" in drill
    assert 'server_version" == "180006"' in drill
    assert "PATHLAB_POSTGRES_CONTAINER" in drill


def test_cutover_evidence_script_is_staging_only_and_composes_existing_proofs() -> None:
    cutover = Path("deploy/scripts/verify-postgres-cutover.sh").read_text(
        encoding="utf-8"
    )
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
