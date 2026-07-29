import hashlib
import json
import os
import shutil
import tarfile
import uuid
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from .storage import DerivativeMeasurement, PublicationError, measure_derivative

MAX_MANIFEST_BYTES = 16 * 1024 * 1024
MAX_DERIVATIVE_FILES = 2_000_000


class PreparedIngestError(ValueError):
    pass


@dataclass(frozen=True)
class PreparedIngestResult:
    measurement: DerivativeMeasurement
    manifest: dict[str, Any]
    manifest_sha256: str


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while block := source.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def install_prepared_package(
    package: Path,
    destination: Path,
    *,
    expected_package_sha256: str,
    expected_artifact_revision_id: str,
    expected_manifest_sha256: str,
) -> PreparedIngestResult:
    if not _is_sha256(expected_package_sha256) or not _is_sha256(
        expected_manifest_sha256
    ):
        raise PreparedIngestError("INVALID_HASH")
    if not expected_artifact_revision_id.strip():
        raise PreparedIngestError("INVALID_ARTIFACT_REVISION")
    if not package.is_file() or sha256_file(package) != expected_package_sha256.lower():
        raise PreparedIngestError("PACKAGE_HASH_MISMATCH")

    staging = destination.with_name(f".{destination.name}.ingest-{uuid.uuid4().hex}")
    staging.parent.mkdir(parents=True, exist_ok=True)
    try:
        staging.mkdir()
        with tarfile.open(package, mode="r:") as archive:
            members = archive.getmembers()
            if len(members) > MAX_DERIVATIVE_FILES + 2:
                raise PreparedIngestError("PACKAGE_FILE_LIMIT")
            by_name = {member.name: member for member in members}
            if len(by_name) != len(members):
                raise PreparedIngestError("DUPLICATE_PACKAGE_PATH")
            manifest_bytes = _read_entry(
                archive, by_name.get("manifest.json"), MAX_MANIFEST_BYTES
            )
            manifest_hash_bytes = _read_entry(
                archive, by_name.get("manifest.sha256"), 64
            )
            actual_manifest_sha256 = hashlib.sha256(manifest_bytes).hexdigest()
            if (
                manifest_hash_bytes.decode("ascii", errors="strict").lower()
                != actual_manifest_sha256
                or actual_manifest_sha256 != expected_manifest_sha256.lower()
            ):
                raise PreparedIngestError("MANIFEST_HASH_MISMATCH")
            try:
                manifest = json.loads(manifest_bytes)
            except (UnicodeDecodeError, json.JSONDecodeError) as error:
                raise PreparedIngestError("INVALID_MANIFEST") from error
            _validate_manifest(manifest, expected_artifact_revision_id)

            declared = {
                str(entry["path"]): (int(entry["size"]), str(entry["sha256"]).lower())
                for entry in manifest["files"]
            }
            archive_payloads = {
                name for name in by_name if name.startswith("derivative/")
            }
            if archive_payloads != set(declared):
                raise PreparedIngestError("PACKAGE_INVENTORY_MISMATCH")
            for name in sorted(declared):
                relative = _derivative_relative(name)
                member = by_name[name]
                if not member.isfile() or member.issym() or member.islnk():
                    raise PreparedIngestError("UNSAFE_PACKAGE_ENTRY")
                expected_size, expected_hash = declared[name]
                if member.size != expected_size or not _is_sha256(expected_hash):
                    raise PreparedIngestError("PACKAGE_METADATA_MISMATCH")
                target = staging / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                digest = hashlib.sha256()
                source = archive.extractfile(member)
                if source is None:
                    raise PreparedIngestError("PACKAGE_ENTRY_MISSING")
                with source, target.open("xb") as output:
                    while block := source.read(1024 * 1024):
                        digest.update(block)
                        output.write(block)
                if target.stat().st_size != expected_size or digest.hexdigest() != expected_hash:
                    raise PreparedIngestError("PACKAGE_PAYLOAD_HASH_MISMATCH")
        try:
            measurement = measure_derivative(staging)
        except PublicationError as error:
            raise PreparedIngestError("UNSAFE_DERIVATIVE") from error
        if os.path.lexists(destination):
            raise PreparedIngestError("DERIVATIVE_ALREADY_EXISTS")
        staging.replace(destination)
        return PreparedIngestResult(measurement, manifest, actual_manifest_sha256)
    finally:
        shutil.rmtree(staging, ignore_errors=True)


def _read_entry(
    archive: tarfile.TarFile, member: tarfile.TarInfo | None, maximum: int
) -> bytes:
    if member is None or not member.isfile() or member.size > maximum:
        raise PreparedIngestError("PACKAGE_CONTROL_FILE_MISSING")
    source = archive.extractfile(member)
    if source is None:
        raise PreparedIngestError("PACKAGE_CONTROL_FILE_MISSING")
    with source:
        return source.read(maximum + 1)


def _validate_manifest(manifest: Any, expected_revision: str) -> None:
    try:
        schema = manifest["schema"]
        provenance = manifest["provenance"]
        slide = manifest["slide"]
        files = manifest["files"]
        revision = provenance["artifactRevisionId"]
        source_fingerprint = provenance["sourceFingerprint"]
        configuration_revision = provenance["configurationRevision"]
        transform = provenance["coordinateTransform"]
        calibration = provenance["calibration"]
    except (KeyError, TypeError) as error:
        raise PreparedIngestError("INVALID_MANIFEST") from error
    if (
        schema != "pathlab-prepared-slide/v2"
        or revision != expected_revision
        or not _is_sha256(str(source_fingerprint))
        or not _is_sha256(str(configuration_revision))
        or int(slide.get("width", 0)) <= 0
        or int(slide.get("height", 0)) <= 0
        or slide.get("tileSize") != 512
        or not isinstance(files, list)
        or not files
        or not isinstance(transform, dict)
        or not isinstance(calibration, dict)
    ):
        raise PreparedIngestError("INVALID_MANIFEST")


def _derivative_relative(name: str) -> Path:
    pure = PurePosixPath(name)
    if (
        pure.is_absolute()
        or len(pure.parts) < 2
        or pure.parts[0] != "derivative"
        or any(part in {"", ".", ".."} for part in pure.parts)
    ):
        raise PreparedIngestError("UNSAFE_PACKAGE_PATH")
    relative = PurePosixPath(*pure.parts[1:])
    suffix = relative.suffix.lower()
    if suffix not in {".dzi", ".jpg", ".jpeg"}:
        raise PreparedIngestError("UNSAFE_PACKAGE_PATH")
    return Path(*relative.parts)


def _is_sha256(value: str) -> bool:
    return len(value) == 64 and all(character in "0123456789abcdefABCDEF" for character in value)
