import hashlib
import json

import pytest
from PIL import Image
from wsi_viewer import worker
from wsi_viewer.alignment import AlignmentRejected


def snapshot(root):
    root.mkdir()
    image = Image.new("RGB", (13, 13), (170, 90, 130))
    image.save(root / "overview.png")
    pixel_hash = hashlib.sha256(
        image.mode.encode() + str(image.size).encode() + image.tobytes()
    ).hexdigest()
    geometry = {
        "schema": "pathlab-sampling-frame/1",
        "kind": "immutable-overview",
        "sourceSize": [100, 99],
        "analysisSize": [13, 13],
        "coordinateFrameSize": [104, 104],
        "samplingScale": [8, 8],
        "cropOrigin": [0, 0],
        "pyramidDivisor": 8,
        "snapshotPixelSha256": pixel_hash,
    }
    descriptor = {
        "schema": "pathlab-immutable-overview/1",
        "image": "overview.png",
        "imageSha256": hashlib.sha256((root / "overview.png").read_bytes()).hexdigest(),
        "pixelSha256": pixel_hash,
        "geometry": geometry,
        "regionSource": {"available": False},
        "originalSource": {"verified": False, "reason": "original-unavailable"},
    }
    (root / "immutable-overview.json").write_text(json.dumps(descriptor))
    return descriptor


def test_snapshot_loader_preserves_exact_pyramid_frame_and_pixels(tmp_path):
    root = tmp_path / "snapshot"
    descriptor = snapshot(root)
    image = worker._load_alignment_overview(root)
    assert image.size == (13, 13)
    assert image.getpixel((0, 0)) == (170, 90, 130)
    assert image.info["alignmentGeometry"] == descriptor["geometry"]


def test_changed_snapshot_bytes_never_fall_back_to_other_pixels(tmp_path):
    root = tmp_path / "snapshot"
    snapshot(root)
    Image.new("RGB", (13, 13), "white").save(root / "overview.png")
    Image.new("RGB", (13, 13), "white").save(root / "thumbnail.jpg")
    with pytest.raises(AlignmentRejected, match="immutable.*digest"):
        worker._load_alignment_overview(root)


def test_snapshot_input_identity_ignores_generated_tile_cache_and_binds_geometry(tmp_path):
    from wsi_viewer.alignment_benchmark import _input_digest

    root = tmp_path / "snapshot"
    descriptor = snapshot(root)
    side = {"path": str(root), "size": [100, 99]}
    initial = _input_digest(side)
    tile = root / "slide_files" / "7"
    tile.mkdir(parents=True)
    (tile / "0_0.jpg").write_bytes(b"generated tile cache")
    assert _input_digest(side) == initial
    descriptor["geometry"]["sourceSize"] = [100, 98]
    (root / "immutable-overview.json").write_text(json.dumps(descriptor))
    with pytest.raises(AlignmentRejected, match="actual input"):
        _input_digest(side)


def test_immutable_regional_original_binding_rejects_redirected_loader_pointer(tmp_path):
    from wsi_viewer.alignment_inputs import immutable_descriptor

    root = tmp_path / "snapshot"
    value = snapshot(root)
    (root / "original.svs").write_bytes(b"verified source")
    (root / "slide.dzi").write_text("frozen dzi")
    value["regionSource"] = {
        "available": True,
        "kind": "openslide-original",
        "file": "original.svs",
        "sha256": hashlib.sha256(b"verified source").hexdigest(),
        "descriptorSha256": hashlib.sha256(b"frozen dzi").hexdigest(),
        "rendering": {"tileSize": 1024, "quality": 92},
    }
    (root / "immutable-overview.json").write_text(json.dumps(value))
    (root / ".openslide-source.json").write_text(
        json.dumps(
            {"source": str(root / "different-original.svs"), "tileSize": 1024, "quality": 92}
        )
    )
    with pytest.raises(AlignmentRejected, match="regional.*binding"):
        immutable_descriptor(root)


def test_content_frame_dedup_retains_calibration_and_every_raw_request(tmp_path):
    import importlib.util
    from pathlib import Path

    path = (
        Path(__file__).resolve().parents[2]
        / "scripts"
        / "prepare_alignment_development_snapshots.py"
    )
    spec = importlib.util.spec_from_file_location("snapshot_preparation", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    sources = {
        "a": {"contentFrameDigest": "same", "manifestSide": {"path": "a"}},
        "b": {"contentFrameDigest": "same", "manifestSide": {"path": "b"}},
        "c": {"contentFrameDigest": "different-calibration", "manifestSide": {"path": "c"}},
    }
    captured = {
        "sourceMetadataDigest": "capture",
        "rawOrderedRequests": [
            {"ordinal": 0, "stackId": "s1", "referenceSlideId": "a", "movingSlideId": "c"},
            {"ordinal": 1, "stackId": "s2", "referenceSlideId": "b", "movingSlideId": "c"},
            {"ordinal": 2, "stackId": "s2", "referenceSlideId": "c", "movingSlideId": "a"},
            {"ordinal": 3, "stackId": "s3", "referenceSlideId": "a", "movingSlideId": "b"},
        ],
    }
    manifest = module.deduplicate(captured, sources)
    assert manifest["requestedOrderedPairs"] == 4
    assert manifest["deduplicatedOrderedPairs"] == 2
    assert [row["pairIndex"] for row in manifest["rawRequestMapping"]] == [0, 0, 1, None]
    assert manifest["qualificationEligible"] is False


def test_consistent_capture_materializes_workspace_only_and_normalizes_known_units(tmp_path):
    import importlib.util
    import sqlite3
    from pathlib import Path

    path = (
        Path(__file__).resolve().parents[2]
        / "scripts"
        / "prepare_alignment_development_snapshots.py"
    )
    spec = importlib.util.spec_from_file_location("snapshot_preparation", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    data = tmp_path / "data"
    database = tmp_path / "input.sqlite3"
    with sqlite3.connect(database) as connection:
        connection.execute(
            "create table slides(id text, sha256 text, slide_metadata text, original_filename text)"
        )
        connection.execute("create table comparison_sets(id text, member_slide_ids text)")
        for name, physical, unit, color in (
            ("a", 0.5, "um", (150, 80, 120)),
            ("b", 500, "nm", (150, 80, 120)),
            ("c", 0.5, "unknown", (130, 70, 110)),
        ):
            root = data / "private" / name
            tile = root / "slide_files" / "7"
            tile.mkdir(parents=True)
            (root / "slide.dzi").write_text(
                '<Image TileSize="256" Overlap="0" Format="jpg" '
                'xmlns="http://schemas.microsoft.com/deepzoom/2008">'
                '<Size Width="100" Height="99"/></Image>'
            )
            Image.new("RGB", (100, 99), color).save(tile / "0_0.jpg")
            metadata = {
                "width": 100,
                "height": 99,
                "physicalSizeX": physical,
                "physicalSizeY": physical,
                "physicalSizeUnit": unit,
            }
            connection.execute(
                "insert into slides values (?,?,?,?)",
                (name, name, json.dumps(metadata), name + ".svs"),
            )
        connection.execute(
            "insert into comparison_sets values (?,?)", ("stack", json.dumps(["a", "b", "c"]))
        )
    before = {
        str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in data.rglob("*") if p.is_file()
    }
    output = tmp_path / "snapshots"
    receipt = module.prepare(database, data, output, tile_cache_budget_bytes=0)
    manifest = json.loads((output / "manifest.json").read_text())
    assert receipt["originalVerifiedCount"] == 0 and receipt["missingOriginalCount"] == 3
    assert manifest["requestedOrderedPairs"] == 6 and manifest["deduplicatedOrderedPairs"] == 2
    assert manifest["contentIdenticalSelfRequestsExcluded"] == 2
    assert manifest["pairs"][0]["reference"]["micronsPerPixel"] == [0.5, 0.5]
    assert "micronsPerPixel" not in manifest["pairs"][0]["moving"]
    assert before == {
        str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in data.rglob("*") if p.is_file()
    }
    assert worker._load_alignment_overview(output / "sources" / "a").size == (100, 99)
    with pytest.raises(FileExistsError):
        module.prepare(database, data, output, tile_cache_budget_bytes=0)


def test_fallback_snapshot_geometry_uses_actual_post_thumbnail_pixels(tmp_path):
    import importlib.util
    from pathlib import Path

    path = (
        Path(__file__).resolve().parents[2]
        / "scripts"
        / "prepare_alignment_development_snapshots.py"
    )
    spec = importlib.util.spec_from_file_location("snapshot_fallback", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    Image.new("RGB", (4200, 100), (140, 90, 120)).save(tmp_path / "thumbnail.jpg")
    image, geometry = module._load_fallback_overview(tmp_path, (84000, 4000))
    assert max(image.size) == 4096
    assert geometry["analysisSize"] == list(image.size)
    assert geometry["samplingScale"] == [84000 / image.width, 4000 / image.height]
    assert geometry["coordinateFrameSize"] == [84000, 4000]
    assert "pyramidDivisor" not in geometry


@pytest.mark.parametrize(
    "unit,expected_mpp", [("UnitsLength.MICROMETER", [0.5, 0.75]), ("unknown", None)]
)
def test_storage_ome_candidates_keep_copied_dzi_and_unverified_original_stage(
    tmp_path, monkeypatch, unit, expected_mpp
):
    import importlib.util
    import sqlite3
    from pathlib import Path

    path = (
        Path(__file__).resolve().parents[2]
        / "scripts"
        / "prepare_alignment_development_snapshots.py"
    )
    spec = importlib.util.spec_from_file_location("snapshot_storage_candidate", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(
        module,
        "_original_calibration",
        lambda *args: pytest.fail("storage fallback is not an admitted OpenSlide source"),
    )
    data = tmp_path / "data"
    database = tmp_path / "input.sqlite3"
    with sqlite3.connect(database) as connection:
        connection.execute(
            "create table slides(id text, sha256 text, slide_metadata text, original_filename text)"
        )
        connection.execute("create table comparison_sets(id text, member_slide_ids text)")
        for name in ("a", "b"):
            root = data / "private" / name
            root.mkdir(parents=True)
            (root / "slide.dzi").write_text(
                '<Image TileSize="512" Overlap="1" Format="jpg" '
                'xmlns="http://schemas.microsoft.com/deepzoom/2008">'
                '<Size Width="100" Height="99"/></Image>'
            )
            for level in range(8):
                if name == "b" and (level == 0 or unit == "unknown"):
                    continue
                tile = root / "slide_files" / str(level)
                tile.mkdir(parents=True)
                divisor = 2 ** (7 - level)
                Image.new(
                    "RGB",
                    ((100 + divisor - 1) // divisor, (99 + divisor - 1) // divisor),
                    (140, 80, 120),
                ).save(tile / "0_0.jpg")
            Image.new("RGB", (100, 99), (140, 80, 120)).save(root / "thumbnail.jpg")
            candidate = data / "originals" / name / "source.ome.tif"
            candidate.parent.mkdir(parents=True)
            candidate.write_bytes(b"opaque storage conversion candidate")
            declared = (
                hashlib.sha256(candidate.read_bytes()).hexdigest() if name == "a" else "b" * 64
            )
            metadata = {
                "width": 100,
                "height": 99,
                "physicalSizeX": 0.5,
                "physicalSizeY": 0.75,
                "physicalSizeUnit": unit,
            }
            connection.execute(
                "insert into slides values(?,?,?,?)",
                (name, declared, json.dumps(metadata), "acquisition.svs"),
            )
        connection.execute(
            "insert into comparison_sets values(?,?)", ("stack", json.dumps(["a", "b"]))
        )
    output = tmp_path / "snapshots"
    receipt = module.prepare(database, data, output, tile_cache_budget_bytes=0)
    assert receipt["originalVerifiedCount"] == 0
    assert receipt["missingOriginalCount"] == 0
    assert receipt["storageCandidateCount"] == 2
    for name in ("a", "b"):
        root = output / "sources" / name
        value = json.loads((root / "immutable-overview.json").read_text())
        assert not (root / ".openslide-source.json").exists()
        assert 'TileSize="512"' in (root / "slide.dzi").read_text()
        assert value["originalSource"]["verified"] is False
        assert value["originalSource"]["kind"] == "storage-ome-candidate"
        assert value["originalSource"]["copiedBytesVerified"] is True
        assert value["originalSource"]["databaseChecksumMatch"] is (name == "a")
        assert value["calibration"]["micronsPerPixel"] == expected_mpp
        assert value["regionSource"]["available"] is (name == "a")
        if name == "a":
            assert value["regionSource"]["kind"] == "copied-dzi"
        if name == "b" and unit == "unknown":
            assert "pyramidDivisor" not in value["geometry"]
            assert value["overviewSourceKind"] == "thumbnail-fallback"
            assert worker._load_alignment_overview(root).getpixel((50, 50)) != (255, 255, 255)
        descriptor = root / "slide.dzi"
        original_descriptor = descriptor.read_bytes()
        descriptor.write_bytes(b"changed declared frame")
        with pytest.raises(AlignmentRejected, match="digest mismatch"):
            worker._load_alignment_overview(root)
        descriptor.write_bytes(original_descriptor)
        candidate = root / value["originalSource"]["file"]
        candidate.write_bytes(b"changed")
        with pytest.raises(AlignmentRejected, match="digest mismatch"):
            worker._load_alignment_overview(root)


@pytest.mark.parametrize("same_candidate_bytes", [False, True])
def test_snapshot_dedup_binds_candidate_content_when_only_overview_is_available(
    tmp_path, same_candidate_bytes
):
    import importlib.util
    import sqlite3
    from pathlib import Path

    path = (
        Path(__file__).resolve().parents[2]
        / "scripts"
        / "prepare_alignment_development_snapshots.py"
    )
    spec = importlib.util.spec_from_file_location("snapshot_candidate_identity", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    data = tmp_path / "data"
    database = tmp_path / "input.sqlite3"
    with sqlite3.connect(database) as connection:
        connection.execute(
            "create table slides(id text, sha256 text, slide_metadata text, original_filename text)"
        )
        connection.execute("create table comparison_sets(id text, member_slide_ids text)")
        for name in ("a", "b"):
            root = data / "private" / name
            root.mkdir(parents=True)
            (root / "slide.dzi").write_text(
                '<Image TileSize="512" Overlap="1" Format="jpg" '
                'xmlns="http://schemas.microsoft.com/deepzoom/2008">'
                '<Size Width="100" Height="99"/></Image>'
            )
            Image.new("RGB", (100, 99), (140, 80, 120)).save(root / "thumbnail.jpg")
            candidate = data / "originals" / name / "source.ome.tif"
            candidate.parent.mkdir(parents=True)
            candidate.write_bytes(b"same source bytes" if same_candidate_bytes else name.encode())
            metadata = {"width": 100, "height": 99}
            connection.execute(
                "insert into slides values(?,?,?,?)",
                (name, None, json.dumps(metadata), name + ".svs"),
            )
        connection.execute(
            "insert into comparison_sets values(?,?)", ("stack", json.dumps(["a", "b"]))
        )
    output = tmp_path / "snapshots"
    module.prepare(database, data, output, tile_cache_budget_bytes=0)
    manifest = json.loads((output / "manifest.json").read_text())
    assert manifest["requestedOrderedPairs"] == 2
    assert manifest["deduplicatedOrderedPairs"] == (0 if same_candidate_bytes else 2)
    assert manifest["contentIdenticalSelfRequestsExcluded"] == (2 if same_candidate_bytes else 0)


def _candidate_admission_fixture(tmp_path):
    import importlib.util
    from pathlib import Path

    path = (
        Path(__file__).resolve().parents[2]
        / "scripts"
        / "prepare_alignment_development_snapshots.py"
    )
    spec = importlib.util.spec_from_file_location("snapshot_admission", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    sha = hashlib.sha256(b"candidate").hexdigest()
    header = [
        {
            "sourceSha256": sha,
            "databaseChecksumMatch": True,
            "sourceStatUnchanged": True,
            "openslideFormat": "generic-tiff",
            "openslideDimensions": [100, 99],
            "openslideBoundedRead": {"size": [512, 512], "pixelSha256": "c" * 64},
            "header": {"isOme": True, "tileWidth": 240, "tileHeight": 240},
        }
    ]
    proof = {
        "status": "probe-complete",
        "processContainment": "windows-job-object",
        "committedMemoryLimitBytes": 7 * 1024**3,
        "peakMemoryBytes": 1000,
        "peakCommittedMemoryBytes": 1000,
        "wallSeconds": 1,
        "sourceHashesAtStart": {"probe": "a" * 64},
        "sourceHashesAtTerminal": {"probe": "a" * 64},
        "regionalProof": [
            {
                "sourceSha256EarlierVerified": sha,
                "trueSourceSize": [100, 99],
                "requestedSourceBounds": [0, 0, 100, 99],
                "returnedSize": [100, 99],
                "returnedFrame": [0, 0, 1],
                "tileSize": 512,
                "overlap": 1,
                "quality": 92,
                "executionBoundary": "diagnostic-heavy-contained-7GiB-not-foreground",
            }
        ],
    }
    heavy_path, header_path = tmp_path / "heavy.json", tmp_path / "headers.json"
    heavy_path.write_text(json.dumps(proof))
    header_path.write_text(json.dumps(header))
    return module, sha, proof, heavy_path, header_path


def test_candidate_admission_binds_two_probe_stages_and_rejects_changed_geometry(tmp_path):
    module, sha, proof, heavy, headers = _candidate_admission_fixture(tmp_path)
    admitted = module._candidate_admissions(heavy, headers)
    assert admitted[sha]["sourceSize"] == [100, 99]
    assert admitted[sha]["heavyProbeSha256"] == hashlib.sha256(heavy.read_bytes()).hexdigest()
    assert admitted[sha]["headerProbeSha256"] == hashlib.sha256(headers.read_bytes()).hexdigest()
    assert admitted[sha]["originalStageVerified"] is False
    proof["regionalProof"][0]["trueSourceSize"] = [101, 99]
    heavy.write_text(json.dumps(proof))
    with pytest.raises(ValueError, match="admission"):
        module._candidate_admissions(heavy, headers)


@pytest.mark.parametrize(
    "change", ["missing-headers", "uncontained", "over-budget", "changed-source"]
)
def test_candidate_admission_requires_complete_bounded_terminal_proof(tmp_path, change):
    module, _, proof, heavy, headers = _candidate_admission_fixture(tmp_path)
    if change == "missing-headers":
        headers = None
    elif change == "uncontained":
        proof["processContainment"] = "root-only"
    elif change == "over-budget":
        proof["peakCommittedMemoryBytes"] = 8 * 1024**3
    else:
        proof["sourceHashesAtTerminal"]["probe"] = "b" * 64
    heavy.write_text(json.dumps(proof))
    with pytest.raises(ValueError, match="admission"):
        module._candidate_admissions(heavy, headers)


@pytest.mark.parametrize(
    "fault", [None, "database-sha", "dzi-size", "dzi-profile", "native-pixels"]
)
def test_admitted_storage_candidate_keeps_thumbnail_and_bound_private_reader(
    tmp_path, monkeypatch, fault
):
    import sqlite3

    from wsi_viewer.alignment_inputs import immutable_descriptor, require_snapshot_region_limit

    module, sha, _, heavy, headers = _candidate_admission_fixture(tmp_path)
    data, database = tmp_path / "data", tmp_path / "input.sqlite3"
    monkeypatch.setattr(
        worker,
        "_load_dzi_overview",
        lambda *a, **k: pytest.fail("single-level candidate must never decode overview"),
    )
    calls = []

    def verify(path, size):
        calls.append((path, size))
        assert path.read_bytes() == b"candidate"
        return {
            "sourceSize": list(size),
            "nativeRoiSize": [512, 512],
            "nativeRoiPixelSha256": ("d" if fault == "native-pixels" else "c") * 64,
        }

    monkeypatch.setattr(module, "_verify_candidate_reader", verify)
    with sqlite3.connect(database) as connection:
        connection.execute(
            "create table slides(id text, sha256 text, slide_metadata text, "
            "original_filename text, render_mode text)"
        )
        connection.execute("create table comparison_sets(id text, member_slide_ids text)")
        for name in ("a", "b"):
            root = data / "private" / name
            root.mkdir(parents=True)
            (root / "slide.dzi").write_text(
                f'<Image TileSize="{256 if fault == "dzi-profile" else 512}" '
                'Overlap="1" Format="jpg">'
                f'<Size Width="{101 if fault == "dzi-size" else 100}" Height="99"/></Image>'
            )
            Image.new("RGB", (50, 49), (140, 80, 120)).save(root / "thumbnail.jpg")
            candidate = data / "originals" / name / "source.ome.tif"
            candidate.parent.mkdir(parents=True)
            candidate.write_bytes(b"candidate")
            connection.execute(
                "insert into slides values(?,?,?,?,?)",
                (
                    name,
                    "b" * 64 if fault == "database-sha" else sha,
                    json.dumps(
                        {
                            "width": 100,
                            "height": 99,
                            "physicalSizeX": 0.5,
                            "physicalSizeY": 0.75,
                            "physicalSizeUnit": "um",
                        }
                    ),
                    "acquisition.svs",
                    "static_dzi",
                ),
            )
        connection.execute(
            "insert into comparison_sets values(?,?)", ("stack", json.dumps(["a", "b"]))
        )
    output = tmp_path / "snapshots"
    if fault is not None:
        with pytest.raises(ValueError, match="candidate admission differs"):
            module.prepare(
                database,
                data,
                output,
                tile_cache_budget_bytes=8 * 1024**2,
                storage_candidate_admission=heavy,
                storage_candidate_headers=headers,
            )
        return
    result = module.prepare(
        database,
        data,
        output,
        tile_cache_budget_bytes=8 * 1024**2,
        storage_candidate_admission=heavy,
        storage_candidate_headers=headers,
    )
    assert len(calls) == 2 and result["originalVerifiedCount"] == 0
    assert result["storageCandidateCount"] == 2
    root = output / "sources" / "a"
    value = immutable_descriptor(root)
    assert value["overviewSourceKind"] == "thumbnail-fallback"
    assert value["capturedRenderMode"] == "static_dzi"
    assert value["regionSource"]["kind"] == "verified-openslide-candidate"
    assert value["originalSource"]["verified"] is False
    assert value["calibration"]["micronsPerPixel"] == [0.5, 0.75]
    assert value["geometry"]["samplingScale"] == [2, 99 / 49]
    pointer = json.loads((root / ".openslide-source.json").read_text())
    assert pointer["source"] == str((root / "stored-candidate.ome.tif").resolve())
    assert pointer["tileSize"] == 512
    assert worker._load_alignment_overview(root).size == (50, 49)
    require_snapshot_region_limit(root, 2048)
    with pytest.raises(AlignmentRejected, match="analysis bound"):
        require_snapshot_region_limit(root, 4096)
    admission = root / "candidate-admission.json"
    admission.write_bytes(b"changed")
    with pytest.raises(AlignmentRejected, match="digest mismatch"):
        immutable_descriptor(root)
