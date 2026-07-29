import hashlib
import io
import json
import tarfile
from pathlib import Path

import pytest
from wsi_viewer.prepared_ingest import PreparedIngestError, install_prepared_package


def _package(path: Path, *, corrupt_tile: bool = False) -> tuple[str, str]:
    files = {
        "derivative/slide.dzi": (
            b'<Image TileSize="512"><Size Width="1" Height="1"/></Image>'
        ),
        "derivative/slide_files/0/0_0.jpg": b"\xff\xd8\xff\xd9",
        "derivative/thumbnail.jpg": b"\xff\xd8\xff\xd9",
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
            "width": 1,
            "height": 1,
            "tileSize": 512,
            "overlap": 1,
            "format": "jpg",
        },
        "files": [
            {
                "path": name,
                "size": len(value),
                "sha256": hashlib.sha256(value).hexdigest(),
            }
            for name, value in files.items()
        ],
    }
    manifest_bytes = json.dumps(
        manifest, ensure_ascii=False, separators=(",", ":")
    ).encode()
    manifest_sha = hashlib.sha256(manifest_bytes).hexdigest()
    with tarfile.open(path, "w") as archive:
        for name, value in {
            "manifest.json": manifest_bytes,
            "manifest.sha256": manifest_sha.encode(),
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
