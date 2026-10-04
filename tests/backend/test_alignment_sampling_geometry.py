"""Deferred fixture regressions: run only after frozen public screening finishes."""

import pytest
from PIL import Image
from wsi_viewer import worker
from wsi_viewer.alignment_engines import EngineRun

RECIPES = [
    "native-overview-v6",
    "hisalign-0.2.1",
    "valis-1.2.0",
    "wsireg-0.3.10",
    "deeperhistreg-classical",
    "deeperhistreg-learned",
    "native-wsireg",
    "valis-rigid-wsireg",
    "native-valis",
]


def dzi(root, size):
    root.mkdir()
    (root / "slide.dzi").write_text(
        '<Image TileSize="256" Overlap="0" Format="jpg" '
        'xmlns="http://schemas.microsoft.com/deepzoom/2008"><Size Width="'
        + str(size[0])
        + '" Height="'
        + str(size[1])
        + '"/></Image>'
    )


class Output:
    def __init__(self):
        self.values = []

    def put(self, value):
        self.values.append(value)


@pytest.mark.parametrize("recipe", RECIPES)
def test_dzi_optional_recipe_uses_exact_pyramid_frame_before_thumbnailing(
    tmp_path, monkeypatch, recipe
):
    ref = tmp_path / "reference"
    mov = tmp_path / "moving"
    dzi(ref, (21912, 19876))
    dzi(mov, (11003, 9013))
    captured = []

    def register(name, **kwargs):
        captured.append(kwargs)
        refsize = kwargs["reference_full_size"]
        movsize = kwargs["moving_full_size"]
        return EngineRun(
            {
                "status": "approximate",
                "controlPoints": [
                    {
                        "reference": [0.75 * refsize[0], 0.75 * refsize[1]],
                        "moving": [0.75 * movsize[0], 0.75 * movsize[1]],
                    }
                ],
            },
            None,
            None,
            0.01,
        )

    monkeypatch.setattr(worker, "run_engine", register)
    # Avoid tissue matching: this fixture exercises loader -> engine coordinate
    # contract, independent of any model or annotation-fitted registration.
    monkeypatch.setattr(worker, "component_bounds", lambda *_: [])
    output = Output()
    settings = {"referenceMicronsPerPixel": [0.25, 0.5], "movingMicronsPerPixel": [0.5, 1]}
    worker._alignment_child(
        str(ref), str(mov), (21912, 19876), (11003, 9013), recipe, settings, None, output
    )
    assert captured and captured[0]["reference"].size == (2739, 2485)
    assert captured[0]["moving"].size == (2751, 2254)
    result = output.values[-1]["result"]
    control = result["controlPoints"][0]
    assert control["reference"] == pytest.approx([16434, 14910])
    assert control["moving"] == pytest.approx([8253, 6762])
    assert captured[0]["settings"]["referenceMicronsPerPixel"] == [0.25, 0.5]
    assert captured[0]["settings"]["movingMicronsPerPixel"] == [0.5, 1]


@pytest.mark.parametrize("recipe", RECIPES)
def test_jpg_recipe_keeps_declared_geometry_and_settings_exactly(tmp_path, monkeypatch, recipe):
    ref = tmp_path / "reference"
    mov = tmp_path / "moving"
    for root in (ref, mov):
        root.mkdir()
        Image.new("RGB", (40, 30), "white").save(root / "thumbnail.jpg")
    captured = []
    settings = {
        "referenceCropped": True,
        "movingCropped": True,
        "referenceMicronsPerPixel": [0.25, 0.5],
        "movingMicronsPerPixel": [0.5, 1],
    }

    def register(name, **kwargs):
        captured.append(kwargs)
        return EngineRun({"status": "approximate"}, None, None, 0.01)

    monkeypatch.setattr(worker, "run_engine", register)
    output = Output()
    worker._alignment_child(
        str(ref), str(mov), (400, 300), (800, 600), recipe, settings, None, output
    )
    assert captured[0]["reference_full_size"] == (400, 300)
    assert captured[0]["moving_full_size"] == (800, 600)
    assert captured[0]["settings"] == settings


def test_engine_clips_padded_support_and_composes_component_origin_once(tmp_path, monkeypatch):
    from types import SimpleNamespace

    from wsi_viewer import alignment_engines as engines

    geometry = {
        "schema": "pathlab-sampling-frame/1",
        "kind": "component-region",
        "sourceSize": [101, 99],
        "analysisSize": [13, 12],
        "coordinateFrameSize": [104, 96],
        "samplingScale": [8, 8],
        "cropOrigin": [10, 20],
    }
    payload = {
        "status": "approximate",
        "movingToReference": [[1, 0, 0], [0, 1, 0]],
        "overviewTriangles": [
            {"moving": [[0, 0], [40, 0], [0, 40]], "reference": [[0, 0], [40, 0], [0, 40]]},
            {
                "moving": [[88, 72], [100, 72], [88, 84]],
                "reference": [[88, 72], [100, 72], [88, 84]],
            },
        ],
        "triangles": [],
        "controlPoints": [],
    }
    monkeypatch.setattr(
        engines,
        "get_engine",
        lambda name: SimpleNamespace(
            register=lambda inputs, progress: EngineRun(payload, None, None, 0.01)
        ),
    )
    image = Image.new("RGB", (13, 12))
    result = engines.run_engine(
        "native-overview-v6",
        reference=image,
        moving=image,
        reference_full_size=(104, 96),
        moving_full_size=(104, 96),
        workspace_root=tmp_path,
        settings={"referenceGeometry": geometry, "movingGeometry": geometry},
    ).registration
    assert len(result["overviewTriangles"]) == 3
    assert result["overviewTriangles"][0]["moving"] == [[10, 20], [50, 20], [10, 60]]
    assert result["movingSupport"] == pytest.approx([10, 20, 101, 99])
    assert all(
        0 <= x < 101 and 0 <= y < 99
        for cell in result["overviewTriangles"]
        for x, y in cell["moving"]
    )
    from wsi_viewer.alignment import map_registration_point

    assert map_registration_point(
        {"triangles": result["overviewTriangles"]}, 100, 98
    ) == pytest.approx((100, 98))
    from wsi_viewer.alignment import AlignmentRejected

    with pytest.raises(AlignmentRejected, match="outside accepted"):
        map_registration_point({"triangles": result["overviewTriangles"]}, 102, 98)
    assert result["movingToReference"] == [[1, 0, 0], [0, 1, 0]]
    assert result["engineSettings"]["movingGeometry"] == geometry


def test_engine_refuses_inconsistent_sampling_frame_before_upstream_runs(tmp_path, monkeypatch):
    from wsi_viewer import alignment_engines as engines
    from wsi_viewer.alignment import AlignmentRejected

    geometry = {
        "schema": "pathlab-sampling-frame/1",
        "kind": "dzi-pyramid",
        "sourceSize": [101, 99],
        "analysisSize": [13, 13],
        "coordinateFrameSize": [104, 101],
        "samplingScale": [8, 8],
        "cropOrigin": [0, 0],
    }
    monkeypatch.setattr(
        engines, "get_engine", lambda _: pytest.fail("invalid frame reached upstream")
    )
    image = Image.new("RGB", (13, 13))
    with pytest.raises(AlignmentRejected, match="sampling"):
        engines.run_engine(
            "native-overview-v6",
            reference=image,
            moving=image,
            reference_full_size=(104, 101),
            moving_full_size=(104, 101),
            workspace_root=tmp_path,
            settings={"referenceGeometry": geometry, "movingGeometry": geometry},
        )


def test_live_derivative_geometry_binds_true_dimensions_and_sampling_before_load(tmp_path):
    from wsi_viewer.alignment_geometry import derivative_sampling_geometry

    root = tmp_path / "reference"
    dzi(root, (21912, 19876))
    value = derivative_sampling_geometry(root, (21912, 19876))
    assert value["coordinateFrameSize"] == [21912, 19880]
    assert value["samplingScale"] == [8, 8]
    assert value["analysisSize"] == [2739, 2485]
    assert value["sourceSize"] == [21912, 19876]
    from wsi_viewer.alignment import AlignmentRejected

    with pytest.raises(AlignmentRejected, match="actual input"):
        derivative_sampling_geometry(root, (21912, 19877))


@pytest.mark.parametrize("change_metadata", [False, True])
def test_worker_publishes_child_effective_settings_without_replacing_them(
    tmp_path, monkeypatch, change_metadata
):
    from wsi_viewer.alignment_engines import ENGINE_NATIVE_OVERVIEW, settings_digest
    from wsi_viewer.config import Settings
    from wsi_viewer.database import create_schema, session_factory
    from wsi_viewer.domain import SlideState
    from wsi_viewer.models import ComparisonRegistrationCandidate, ComparisonSet, Job, Slide
    from wsi_viewer.storage import StorageLayout

    current = Settings(
        database_url=f"sqlite:///{tmp_path / 'settings.sqlite3'}", data_root=tmp_path / "data"
    )
    create_schema(current)
    factory = session_factory(current)
    layout = StorageLayout(current.data_root)
    geometry = {
        "schema": "pathlab-sampling-frame/1",
        "kind": "dzi-pyramid",
        "sourceSize": [100, 100],
        "analysisSize": [13, 13],
        "coordinateFrameSize": [104, 104],
        "samplingScale": [8, 8],
        "cropOrigin": [0, 0],
    }
    effective = {"referenceGeometry": geometry, "movingGeometry": geometry, "inputBlurRadius": 0.6}
    with factory() as db:
        for name in ("reference", "moving"):
            db.add(
                Slide(
                    id=name,
                    public_id="p-" + name,
                    display_name=name,
                    original_filename=name + ".tif",
                    source_bytes=1,
                    state=SlideState.READY_PRIVATE,
                    sha256=name + "1",
                    slide_metadata={"width": 100, "height": 100},
                )
            )
        db.flush()
        comparison = ComparisonSet(
            name="settings",
            reference_slide_id="reference",
            member_slide_ids=["reference", "moving"],
            source_versions={"reference": "reference1", "moving": "moving1"},
            registrations={},
            status="queued",
        )
        db.add(comparison)
        db.flush()
        db.add(
            Job(
                slide_id="moving",
                kind="align_benchmark",
                resource_class="isolated",
                checkpoint={
                    "comparisonSetId": comparison.id,
                    "memberId": "moving",
                    "anchorSlideId": "reference",
                    "setVersion": comparison.version,
                    "engine": ENGINE_NATIVE_OVERVIEW,
                },
                resource_limits={},
            )
        )
        db.commit()

    def run(*a, **kw):
        if change_metadata:
            with factory() as database:
                source = database.get(Slide, "moving")
                source.slide_metadata = {**source.slide_metadata, "width": 101}
                database.commit()
        return {
            "status": "approximate",
            "confidence": 0.49,
            "inlierCount": 0,
            "movingToReference": [[1, 0, 0], [0, 1, 0]],
            "triangles": [],
            "overviewTriangles": [
                {"moving": [[0, 0], [20, 0], [0, 20]], "reference": [[0, 0], [20, 0], [0, 20]]}
            ],
            "engineSettings": effective,
            "evidence": {},
            "runtimeSeconds": 0.1,
        }

    monkeypatch.setattr(worker, "_run_alignment_bounded", run)
    assert worker.process_next(factory, layout) is True
    with factory() as db:
        if change_metadata:
            assert db.query(ComparisonRegistrationCandidate).count() == 0
            assert db.query(Job).one().status == "cancelled"
            return
        candidate = db.query(ComparisonRegistrationCandidate).one()
        assert candidate.registration["engineSettings"] == effective
        assert candidate.settings_digest == settings_digest(ENGINE_NATIVE_OVERVIEW, effective)
        assert candidate.registration["settingsDigest"] == candidate.settings_digest
        assert candidate.registration["requestedSettings"] == {}
