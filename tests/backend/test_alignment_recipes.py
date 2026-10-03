import numpy as np
import pytest
from PIL import Image
from wsi_viewer import alignment_engines as engines
from wsi_viewer.alignment import AlignmentRejected, map_registration_point


def test_native_adapter_retains_accepted_map_compatibility_version():
    from wsi_viewer.alignment_fast import PREPARATION_VERSION

    assert engines.ADAPTER_VERSIONS[engines.ENGINE_NATIVE] == (
        "pathlab-adapter-v2-high-resolution-components"
    )
    assert PREPARATION_VERSION == "overview-orb1536-v6-component-fallback"


def test_recipe_registry_exposes_real_engines_and_hybrids():
    for recipe in (
        "native",
        "valis",
        "wsireg",
        "hisalign",
        "deeperhistreg-classical",
        "deeperhistreg-learned",
        "native-wsireg",
        "valis-rigid-wsireg",
        "native-valis",
    ):
        assert engines.get_engine(recipe).name in engines.SUPPORTED_ENGINES


def test_hybrid_composes_residual_in_initial_warp_frame(tmp_path, monkeypatch):
    from wsi_viewer.alignment_recipes import RecipeEngine

    initializer = [[2, 0, 10], [0, 3, 20]]
    seed = {"status": "approximate", "movingToReference": initializer}
    residual = {
        "status": "approximate",
        "movingToReference": [[1, 0, 5], [0, 1, -2]],
        "overviewTriangles": [
            {
                "moving": [[10, 20], [210, 20], [10, 320]],
                "reference": [[15, 18], [215, 18], [15, 318]],
            }
        ],
    }
    calls = []

    class Stage:
        def available(self):
            return True, None

        def register(self, inputs, progress):
            calls.append(inputs)
            return engines.EngineRun(seed if len(calls) == 1 else residual, None, None, 0.01)

    monkeypatch.setattr(engines, "get_engine", lambda name: Stage())
    image = Image.new("RGB", (400, 400), "white")
    run = RecipeEngine("native-wsireg").register(
        engines.EngineInput(
            image,
            image,
            image.size,
            image.size,
            tmp_path,
            {
                "referenceMicronsPerPixel": [0.25, 0.5],
                "movingMicronsPerPixel": [0.5, 1],
                "stages": {engines.ENGINE_WSIREG: {"movingMicronsPerPixel": [3, 4]}},
            },
        ),
        lambda _: None,
    )
    assert np.asarray(run.registration["movingToReference"]) == pytest.approx(
        np.asarray([[2, 0, 15], [0, 3, 18]])
    )
    cell = run.registration["overviewTriangles"][0]
    assert map_registration_point({"triangles": [cell]}, 20, 30) == pytest.approx((55, 108))
    assert run.registration["status"] == "approximate"
    assert len(run.registration["recipeStages"]) == 2
    assert calls[1].moving_full_size == image.size
    assert calls[0].settings["movingMicronsPerPixel"] == [0.5, 1]
    assert calls[0].settings["referenceMicronsPerPixel"] == [0.25, 0.5]
    assert calls[1].settings["movingMicronsPerPixel"] == [0.25, 0.5]
    assert calls[1].settings["referenceMicronsPerPixel"] == [0.25, 0.5]
    assert run.registration["movingSupport"] == pytest.approx([0, 0, 100, 100])
    assert run.registration["referenceSupport"] == pytest.approx([15, 18, 215, 318])


def test_missing_wsireg_never_runs_native(tmp_path, monkeypatch):
    monkeypatch.setattr(engines.importlib.util, "find_spec", lambda name: None)
    monkeypatch.setattr(
        engines.NativeEngine, "register", lambda *_: pytest.fail("native substitution")
    )
    available, reason = engines.get_engine("wsireg").available()
    assert not available and "wsireg" in reason.lower()
    with pytest.raises(AlignmentRejected, match="unavailable|installed"):
        engines.run_engine(
            "wsireg",
            reference=Image.new("RGB", (10, 10)),
            moving=Image.new("RGB", (10, 10)),
            reference_full_size=(10, 10),
            moving_full_size=(10, 10),
            workspace_root=tmp_path,
        )


def test_dhr_normalized_pull_direction_handles_non_square_pixel_centers():
    from wsi_viewer.alignment_optional import theta_pull_to_pixel

    # A target pixel samples a source five pixels to the right and seven down.
    pull = theta_pull_to_pixel(np.asarray([[1, 0, 10 / 400], [0, 1, 14 / 300]]), (400, 300))
    assert pull @ [100, 50, 1] == pytest.approx([105, 57, 1])
    assert np.linalg.inv(pull) @ [105, 57, 1] == pytest.approx([100, 50, 1])


def test_recipe_total_budget_does_not_reset_between_stages(tmp_path, monkeypatch):
    from wsi_viewer import alignment_recipes

    clock = [0.0]
    calls = []

    class SlowStage:
        def register(self, inputs, progress):
            calls.append(inputs.settings["timeoutSeconds"])
            clock[0] += 7
            return engines.EngineRun(
                {
                    "status": "approximate",
                    "movingToReference": [[1, 0, 0], [0, 1, 0]],
                    "overviewTriangles": [
                        {"moving": [[0, 0], [5, 0], [0, 5]], "reference": [[0, 0], [5, 0], [0, 5]]}
                    ],
                },
                None,
                None,
                7,
            )

    monkeypatch.setattr(engines, "get_engine", lambda name: SlowStage())
    monkeypatch.setattr(alignment_recipes.time, "monotonic", lambda: clock[0])
    image = Image.new("RGB", (10, 10))
    with pytest.raises(AlignmentRejected, match="pair timeout"):
        alignment_recipes.RecipeEngine("native-wsireg").register(
            engines.EngineInput(
                image, image, image.size, image.size, tmp_path, {"timeoutSeconds": 10}
            ),
            lambda _: None,
        )
    assert calls == [10, 3]


def test_wsireg_one_elastix_chain_composes_noncommuting_transforms():
    pytest.importorskip("wsireg")
    from wsi_viewer.alignment_optional import wsireg_pull_transform

    geometry = {
        "Spacing": ["1", "1"],
        "Size": ["100", "100"],
        "Origin": ["0", "0"],
        "Direction": ["1", "0", "0", "1"],
        "ResampleInterpolator": ["FinalLinearInterpolator"],
        "CenterOfRotationPoint": ["0", "0"],
    }
    translation = {
        **geometry,
        "Transform": ["TranslationTransform"],
        "TransformParameters": ["10", "0"],
    }
    scaling = {
        **geometry,
        "Transform": ["AffineTransform"],
        "TransformParameters": ["2", "0", "0", "2", "0", "0"],
    }
    pull = wsireg_pull_transform([translation, scaling])
    assert pull.TransformPoint((0, 0)) == pytest.approx((20, 0))
    assert pull.GetInverse().TransformPoint((20, 0)) == pytest.approx((0, 0))


def test_bounded_nonlinear_inverse_recovers_curved_coupled_map():
    from wsi_viewer.alignment_optional import invert_coordinate_pull

    def pull(points):
        x, y = points.T
        return np.column_stack((x + 4 * np.sin(y / 30), y + 2 * np.sin(x / 40)))

    reference = np.asarray([[30, 40], [200, 150], [60, 220]], dtype=float)
    recovered = invert_coordinate_pull(pull, pull(reference), initial=reference + [1, 2])
    assert recovered == pytest.approx(reference, abs=0.025)


def test_bounded_nonlinear_inverse_rejects_fold_and_sample_budget():
    from wsi_viewer.alignment_optional import invert_coordinate_pull

    with pytest.raises(AlignmentRejected, match="fold|Jacobian"):
        invert_coordinate_pull(lambda points: points * [-1, 1], np.asarray([[10.0, 20.0]]))
    with pytest.raises(AlignmentRejected, match="sample budget"):
        invert_coordinate_pull(lambda points: points, np.zeros((2402, 2)))


@pytest.mark.parametrize("residual_fails", [False, True])
def test_initializer_provenance_survives_temporary_cleanup_and_residual_failure(
    tmp_path, monkeypatch, residual_fails
):
    import hashlib
    import json

    from wsi_viewer.alignment_recipes import RecipeEngine

    workspaces = []
    calls = []
    seed = {
        "status": "approximate",
        "movingToReference": [[1, 0, 0], [0, 1, 0]],
        "overviewTriangles": [
            {"moving": [[0, 0], [5, 0], [0, 5]], "reference": [[0, 0], [5, 0], [0, 5]]}
        ],
    }

    class Stage:
        def register(self, inputs, progress):
            workspaces.append(inputs.workspace)
            calls.append(True)
            if len(calls) == 2:
                # Already durable before residual execution, including a hard
                # timeout/termination that cannot run Python finally blocks.
                assert (artifact_dir / "initializer-coordinate-map.json").is_file()
            if len(calls) == 2 and residual_fails:
                raise AlignmentRejected("residual failed")
            return engines.EngineRun(seed, None, None, 0.1)

    monkeypatch.setattr(
        engines,
        "get_engine",
        lambda name: RecipeEngine(name) if name == "native-wsireg" else Stage(),
    )
    image = Image.new("RGB", (10, 10))
    artifact_dir = tmp_path / "private-artifacts"
    kwargs = dict(
        reference=image,
        moving=image,
        reference_full_size=image.size,
        moving_full_size=image.size,
        workspace_root=tmp_path,
        artifact_dir=artifact_dir,
    )
    if residual_fails:
        with pytest.raises(AlignmentRejected, match="residual failed"):
            engines.run_engine("native-wsireg", **kwargs)
    else:
        result = engines.run_engine("native-wsireg", **kwargs)
        descriptor = result.registration["initializerArtifact"]
        assert set(descriptor) == {"name", "sha256"}
        assert descriptor["name"] == "initializer-coordinate-map.json"
        assert (
            descriptor["sha256"]
            == hashlib.sha256((artifact_dir / descriptor["name"]).read_bytes()).hexdigest()
        )
        assert result.registration["recipeFrames"]["initializerSupportAppliedToWarp"] is False
    assert json.loads((artifact_dir / "initializer-coordinate-map.json").read_text()) == seed
    assert all(not path.exists() for path in workspaces)


def test_initializer_provenance_copy_rejects_unsafe_name_digest_and_size(tmp_path, monkeypatch):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "initializer-coordinate-map.json").write_text('{"status":"approximate"}')
    destination = tmp_path / "output"
    with pytest.raises(AlignmentRejected, match="basename"):
        engines._copy_initializer_provenance(
            workspace, destination, {"name": "../secret", "sha256": "bad"}
        )
    with pytest.raises(AlignmentRejected, match="digest"):
        engines._copy_initializer_provenance(
            workspace, destination, {"name": "initializer-coordinate-map.json", "sha256": "bad"}
        )
    monkeypatch.setattr(engines, "MAX_INITIALIZER_ARTIFACT_BYTES", 8)
    with pytest.raises(AlignmentRejected, match="size ceiling"):
        engines._copy_initializer_provenance(workspace, destination, None)
    assert not destination.exists()
