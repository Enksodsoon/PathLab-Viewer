import hashlib
import io
import json
import tarfile
from pathlib import Path

import pytest
from PIL import Image
from wsi_viewer.prepared_ingest import (
    PreparedIngestError,
    _validate_manifest,
    install_prepared_package,
)


def test_accepts_forge_compact_visual_v2_encoding() -> None:
    manifest = {
        "schema": "pathlab-prepared-slide/v2",
        "provenance": {
            "artifactRevisionId": "artifact-1",
            "configurationRevision": "a" * 64,
            "sourceFingerprint": "b" * 64,
            "coordinateTransform": {},
            "calibration": {},
        },
        "slide": {
            "width": 2048,
            "height": 1536,
            "tileSize": 512,
            "overlap": 1,
            "format": "jpg",
            "encoding": {
                "codec": "jpeg",
                "quality": 65,
                "selector": "quality-gated-v2-64-roi",
                "qualityProfile": "pathlab-compact-visual-v2",
                "encoderProfile": "compact-420-trellis",
            },
        },
    }

    assert _validate_manifest(manifest, "artifact-1") is manifest


def _package(
    path: Path,
    *,
    corrupt_tile: bool = False,
    ndjson_inventory: bool = False,
    incomplete_pyramid: bool = False,
) -> tuple[str, str]:
    jpeg = io.BytesIO()
    Image.new("RGB", (1, 1), "white").save(jpeg, format="JPEG", quality=85)
    jpeg_bytes = jpeg.getvalue()
    width = 1024 if incomplete_pyramid else 1
    files = {
        "derivative/slide.dzi": (
            b'<Image TileSize="512" Overlap="1" Format="jpg">'
            + f'<Size Width="{width}" Height="1"/></Image>'.encode()
        ),
        "derivative/slide_files/0/0_0.jpg": jpeg_bytes,
        "derivative/thumbnail.jpg": jpeg_bytes,
    }
    manifest = {
        "schema": "pathlab-prepared-slide/v2",
        "producer": {"name": "PathLab Forge", "version": "test"},
        "provenance": {
            "artifactRevisionId": "artifact-1",
            "configurationRevision": "a" * 64,
            "sourceFingerprint": "b" * 64,
            "series": 2,
            "crop": {"x": 10, "y": 20, "width": 30, "height": 40},
            "downsample": 1.5,
            "coordinateTransform": {
                "translateX": -10,
                "translateY": -20,
                "scale": 2 / 3,
            },
            "calibration": {
                "pixelSizeX": 0.375,
                "pixelSizeY": 0.375,
                "unit": "µm",
            },
        },
        "slide": {
            "width": width,
            "height": 1,
            "tileSize": 512,
            "overlap": 1,
            "format": "jpg",
        },
    }
    inventory = [
        {
            "path": name,
            "size": len(value),
            "sha256": hashlib.sha256(value).hexdigest(),
        }
        for name, value in files.items()
    ]
    controls: dict[str, bytes] = {}
    if ndjson_inventory:
        inventory_bytes = b"".join(
            json.dumps(item, separators=(",", ":")).encode() + b"\n"
            for item in inventory
        )
        manifest["inventory"] = {
            "format": "ndjson-v1",
            "path": "inventory.ndjson",
            "sha256": hashlib.sha256(inventory_bytes).hexdigest(),
            "fileCount": len(inventory),
            "derivativeBytes": sum(item["size"] for item in inventory),
        }
        controls["inventory.ndjson"] = inventory_bytes
    else:
        manifest["files"] = inventory
    manifest_bytes = json.dumps(
        manifest, ensure_ascii=False, separators=(",", ":")
    ).encode()
    manifest_sha = hashlib.sha256(manifest_bytes).hexdigest()
    with tarfile.open(path, "w") as archive:
        for name, value in {
            "manifest.json": manifest_bytes,
            "manifest.sha256": manifest_sha.encode(),
            **controls,
            **files,
        }.items():
            if corrupt_tile and name.endswith("0_0.jpg"):
                value = value + b"mutated"
            info = tarfile.TarInfo(name)
            info.size = len(value)
            info.mtime = 0
            archive.addfile(info, io.BytesIO(value))
    return hashlib.sha256(path.read_bytes()).hexdigest(), manifest_sha


def test_installs_hash_verified_v2_package(tmp_path: Path) -> None:
    package = tmp_path / "slide.plslide"
    package_sha, manifest_sha = _package(package)

    result = install_prepared_package(
        package,
        tmp_path / "private" / "slide-1",
        expected_package_sha256=package_sha,
        expected_artifact_revision_id="artifact-1",
        expected_manifest_sha256=manifest_sha,
    )

    assert result.measurement.file_count == 3
    assert result.manifest["provenance"]["sourceFingerprint"] == "b" * 64
    assert (tmp_path / "private" / "slide-1" / "slide.dzi").is_file()


def test_rejects_payload_mutated_after_manifest(tmp_path: Path) -> None:
    package = tmp_path / "slide.plslide"
    package_sha, manifest_sha = _package(package, corrupt_tile=True)

    with pytest.raises(PreparedIngestError, match="PACKAGE_METADATA_MISMATCH"):
        install_prepared_package(
            package,
            tmp_path / "private" / "slide-1",
            expected_package_sha256=package_sha,
            expected_artifact_revision_id="artifact-1",
            expected_manifest_sha256=manifest_sha,
        )


def test_rejects_stale_artifact_revision(tmp_path: Path) -> None:
    package = tmp_path / "slide.plslide"
    package_sha, manifest_sha = _package(package)

    with pytest.raises(PreparedIngestError, match="INVALID_MANIFEST"):
        install_prepared_package(
            package,
            tmp_path / "private" / "slide-1",
            expected_package_sha256=package_sha,
            expected_artifact_revision_id="artifact-2",
            expected_manifest_sha256=manifest_sha,
        )


def test_rejects_incomplete_dzi_pyramid(tmp_path: Path) -> None:
    package = tmp_path / "slide.plslide"
    package_sha, manifest_sha = _package(package, incomplete_pyramid=True)

    with pytest.raises(PreparedIngestError, match="INCOMPLETE_DZI_PYRAMID"):
        install_prepared_package(
            package,
            tmp_path / "private" / "slide-1",
            expected_package_sha256=package_sha,
            expected_artifact_revision_id="artifact-1",
            expected_manifest_sha256=manifest_sha,
        )


def test_installs_streaming_ndjson_inventory_without_member_list(tmp_path: Path) -> None:
    package = tmp_path / "slide.plslide"
    package_sha, manifest_sha = _package(package, ndjson_inventory=True)

    result = install_prepared_package(
        package,
        tmp_path / "private" / "slide-1",
        expected_package_sha256=package_sha,
        expected_artifact_revision_id="artifact-1",
        expected_manifest_sha256=manifest_sha,
    )

    assert result.measurement.file_count == 3
    assert result.manifest["inventory"]["format"] == "ndjson-v1"
    assert not (tmp_path / "private" / "slide-1" / ".inventory.ndjson").exists()


def test_rejects_package_hash_only_after_private_staging(tmp_path: Path) -> None:
    package = tmp_path / "slide.plslide"
    _, manifest_sha = _package(package, ndjson_inventory=True)
    destination = tmp_path / "private" / "slide-1"

    with pytest.raises(PreparedIngestError, match="PACKAGE_HASH_MISMATCH"):
        install_prepared_package(
            package,
            destination,
            expected_package_sha256="f" * 64,
            expected_artifact_revision_id="artifact-1",
            expected_manifest_sha256=manifest_sha,
        )

    assert not destination.exists()
