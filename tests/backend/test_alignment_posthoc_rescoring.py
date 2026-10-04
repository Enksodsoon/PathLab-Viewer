"""Artifact-bound rescoring must not execute registration or rewrite cold evidence."""

import hashlib
import importlib.util
import json
from pathlib import Path

import pytest


@pytest.fixture
def posthoc(monkeypatch):
    scripts = Path(__file__).resolve().parents[2] / "scripts"
    monkeypatch.syspath_prepend(str(scripts))
    spec = importlib.util.spec_from_file_location(
        "alignment_posthoc", scripts / "rescore_alignment_saved_maps.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _frozen(tmp_path):
    digest = "a" * 64
    registration = {
        "status": "ready",
        "triangles": [{"moving": [[0, 0], [2, 0], [0, 2]], "reference": [[0, 0], [2, 0], [0, 2]]}],
        "overviewTriangles": [
            {"moving": [[0, 0], [20, 0], [0, 20]], "reference": [[1, 0], [21, 0], [1, 20]]}
        ],
    }
    row = {
        "digest": digest,
        "recipe": "native-overview-v6",
        "pairIndex": 0,
        "kind": "positive",
        "outcome": "ok",
        "settingsDigest": "b" * 64,
        "inputDigests": ["c" * 64, "d" * 64],
        "engineBuild": "frozen-build",
        "runtimeVersions": {"numpy": "frozen"},
        "landmarkMetrics": {"observedLandmarks": 1},
    }
    manifest = {
        "pairs": [
            {
                "reference": {"size": [100, 100]},
                "moving": {"size": [100, 100]},
                "independentlyReviewed": True,
                "landmarksFitFree": True,
                "landmarks": [
                    {
                        "eligible": True,
                        "movingPoint": point,
                        "referencePoint": point,
                        "wrongStructure": False,
                    }
                    for point in [[0.5, 0.5], [5, 5]]
                ],
            }
        ]
    }
    (tmp_path / "cache").mkdir()
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(manifest))
    (tmp_path / "report.json").write_text(json.dumps({"rows": [row]}))
    receipt_path = tmp_path / "cache" / f"{digest}.json"
    receipt_path.write_text(json.dumps({**row, "registration": registration}))
    return manifest_path, hashlib.sha256(manifest_path.read_bytes()).hexdigest(), receipt_path


def test_posthoc_scores_both_tiers_and_preserves_original_evidence(posthoc, tmp_path):
    manifest, digest, receipt = _frozen(tmp_path)
    originals = {path: path.read_bytes() for path in [manifest, receipt, tmp_path / "report.json"]}
    result = posthoc.rescore(tmp_path, manifest, digest)
    row = result["rows"][0]
    assert row["originalLandmarkMetrics"]["observedLandmarks"] == 1
    assert row["pointwiseMetrics"]["observedLandmarks"] == 2
    assert row["pointwiseMetrics"]["supportTierCounts"] == {"ready-local": 1, "own-overview": 1}
    assert row["mapStatusUnchanged"] == "ready"
    assert result["registrationReruns"] == 0
    assert result["qualificationEvidence"] is False
    assert result["originalArtifactsUnchanged"] is True
    assert all(path.read_bytes() == content for path, content in originals.items())
    public = json.dumps(result, allow_nan=False)
    assert "movingPoint" not in public and "overviewTriangles" not in public
    assert str(tmp_path) not in public


@pytest.mark.parametrize("key", ["digest", "settingsDigest", "inputDigests", "runtimeVersions"])
def test_receipt_metadata_must_match_frozen_row(posthoc, tmp_path, key):
    manifest, digest, receipt = _frozen(tmp_path)
    value = json.loads(receipt.read_text())
    value[key] = "tampered"
    receipt.write_text(json.dumps(value))
    with pytest.raises(ValueError, match="receipt binding differs"):
        posthoc.rescore(tmp_path, manifest, digest)


def test_changed_manifest_is_not_admitted(posthoc, tmp_path):
    manifest, digest, _ = _frozen(tmp_path)
    manifest.write_text(manifest.read_text() + " ")
    with pytest.raises(ValueError, match="frozen bytes"):
        posthoc.rescore(tmp_path, manifest, digest)


def test_analysis_detects_original_artifact_mutation(posthoc, tmp_path, monkeypatch):
    manifest, digest, receipt = _frozen(tmp_path)
    original = posthoc.evaluate_landmarks

    def mutate(*args, **kwargs):
        receipt.write_text(receipt.read_text() + " ")
        return original(*args, **kwargs)

    monkeypatch.setattr(posthoc, "evaluate_landmarks", mutate)
    with pytest.raises(ValueError, match="changed during"):
        posthoc.rescore(tmp_path, manifest, digest)
