import hashlib
import json
from pathlib import Path

import pytest
from test_alignment_api import _client, _headers
from test_alignment_engine_routes import _hybrid_candidate, _stack
from wsi_viewer.alignment_calibration import metadata_frame_digest, normalized_microns_per_pixel
from wsi_viewer.alignment_engines import ENGINE_VERSIONS, settings_digest
from wsi_viewer.database import session_factory
from wsi_viewer.models import (
    ComparisonRegistrationCandidate,
    ComparisonSet,
    Job,
    LibraryShare,
    ShareSlide,
    Slide,
)
from wsi_viewer.storage import StorageLayout


def _geometry():
    return {
        "schema": "pathlab-sampling-frame/1",
        "kind": "dzi-pyramid",
        "sourceSize": [1000, 800],
        "analysisSize": [1000, 800],
        "coordinateFrameSize": [1000, 800],
        "samplingScale": [1, 1],
        "cropOrigin": [0, 0],
        "pyramidDivisor": 1,
        "selectedLevel": 10,
    }


def _candidate(client, stack, settings):
    with session_factory(client.app.state.settings)() as database:
        candidate_id, saved = _hybrid_candidate(database, stack, engine="native-overview-v6")
        row = database.get(ComparisonRegistrationCandidate, candidate_id)
        digest = settings_digest(row.engine, settings)
        row.settings_digest = digest
        row.registration = {
            **row.registration,
            "engineSettings": settings,
            "engine": row.engine,
            "engineVersion": ENGINE_VERSIONS[row.engine],
            "settingsDigest": digest,
            "sourceVersion": "sha-2",
            "anchorVersion": "sha-1",
            "provenance": "automatic",
        }
        database.get(ComparisonSet, stack["id"]).registrations = {"slide-2": row.registration}
        database.commit()
    return candidate_id


def _descriptors(client):
    layout = StorageLayout(client.app.state.settings.data_root)
    for name in ("slide-1", "slide-2"):
        derivative = layout.for_slide(name).private_derivative
        derivative.mkdir(parents=True, exist_ok=True)
        (derivative / "slide.dzi").write_text(
            '<Image xmlns="http://schemas.microsoft.com/deepzoom/2008" '
            'TileSize="256" Overlap="0" Format="jpg">'
            '<Size Width="1000" Height="800"/></Image>'
        )
    return layout


@pytest.mark.parametrize(
    "change",
    ["width", "height", "physicalSizeX", "physicalSizeY", "physicalSizeUnit", "descriptor"],
)
def test_effective_frame_candidate_and_canonical_map_reject_same_sha_live_changes(tmp_path, change):
    with _client(tmp_path, enabled=True) as client:
        headers = _headers(client)
        stack = _stack(client, headers)
        url = f"/api/v1/admin/comparison-sets/{stack['id']}"
        layout = _descriptors(client)
        settings = {
            "referenceGeometry": _geometry(),
            "movingGeometry": _geometry(),
            "referenceMicronsPerPixel": [0.25, 0.25],
            "movingMicronsPerPixel": [0.25, 0.25],
        }
        candidate_id = _candidate(client, stack, settings)
        assert client.get(url + "/candidates").json()["candidates"][0]["currentSettings"] is True
        assert client.get(url).json()["members"][1]["registration"]["status"] == "ready"
        if change == "descriptor":
            descriptor = layout.for_slide("slide-2").private_derivative / "slide.dzi"
            descriptor.write_text(descriptor.read_text().replace('Width="1000"', 'Width="1001"'))
        else:
            with session_factory(client.app.state.settings)() as database:
                slide = database.get(Slide, "slide-2")
                slide.slide_metadata = {
                    **slide.slide_metadata,
                    change: {
                        "width": 1100,
                        "height": 900,
                        "physicalSizeX": 0.5,
                        "physicalSizeY": 0.5,
                        "physicalSizeUnit": "nm",
                    }[change],
                }
                database.commit()
        assert client.get(url + "/candidates").json()["candidates"][0]["currentSettings"] is False
        response = client.post(
            url + f"/candidates/{candidate_id}/promote",
            headers=headers,
            json={"version": stack["version"]},
        )
        assert response.status_code == 409
        registration = client.get(url).json()["members"][1]["registration"]
        assert registration["status"] == "stale"
        assert registration["triangles"] == []
        with session_factory(client.app.state.settings)() as database:
            assert (
                database.get(ComparisonSet, stack["id"]).registrations["slide-2"]["status"]
                == "ready"
            )


def test_effective_settings_digest_is_preserved_while_api_and_shared_views_hide_resource_paths(
    tmp_path,
):
    with _client(tmp_path, enabled=True) as client:
        headers = _headers(client)
        stack = _stack(client, headers)
        url = f"/api/v1/admin/comparison-sets/{stack['id']}"
        settings = {
            "valisDiskWeightsPath": "C:/private-user/private-weights.pth",
            "valisDiskWeightsSha256": "d" * 64,
            "stageEffectiveSettings": {
                "residual": {
                    "resourcePath": "C:/private-stage/model.bin",
                    "resourceSha256": "e" * 64,
                }
            },
        }
        candidate_id = _candidate(client, stack, settings)
        digest = settings_digest("native-overview-v6", settings)
        with session_factory(client.app.state.settings)() as database:
            share = LibraryShare(
                public_id="frame-share",
                target_type="collection",
                target_id="collection",
                privacy_status="passed",
            )
            database.add(share)
            database.flush()
            database.add_all(
                [
                    ShareSlide(share_id=share.id, slide_id=name, sort_order=index)
                    for index, name in enumerate(("slide-1", "slide-2"))
                ]
            )
            database.commit()
        responses = [
            client.get(url).json(),
            client.get(url + "/candidates").json(),
            client.get(f"/api/v2/public/collections/frame-share/comparisons/{stack['id']}").json(),
        ]
        for response in responses:
            serialized = json.dumps(response)
            assert "private-user" not in serialized
            assert "private-stage" not in serialized
            assert digest in serialized
            assert "d" * 64 in serialized and "e" * 64 in serialized
        assert responses[1]["candidates"][0]["currentSettings"] is True
        result = client.post(
            url + f"/candidates/{candidate_id}/promote",
            headers=headers,
            json={"version": stack["version"]},
        )
        assert result.status_code == 200, result.text
        with session_factory(client.app.state.settings)() as database:
            stored = database.get(ComparisonSet, stack["id"]).registrations["slide-2"]
            assert stored["engineSettings"] == settings
            assert stored["settingsDigest"] == digest
            assert stored["triangles"][0]["reference"][0] == [10, 5]


@pytest.mark.parametrize("engine", ["valis-1.2.0", "native-valis"])
def test_valis_queue_and_availability_require_declared_verified_resources(tmp_path, engine):
    with _client(tmp_path, enabled=True, valis=True) as client:
        headers = _headers(client)
        stack = _stack(client, headers)
        url = f"/api/v1/admin/comparison-sets/{stack['id']}"
        availability = client.get(url + "/candidates").json()["engineAvailability"]
        assert availability[engine]["available"] is False
        response = client.post(
            url + "/benchmark",
            headers=headers,
            json={"version": stack["version"], "engines": [engine]},
        )
        assert response.status_code == 409
        assert response.json()["detail"]["code"] == "ALIGNMENT_ENGINE_RESOURCE_UNAVAILABLE"
        with session_factory(client.app.state.settings)() as database:
            assert database.query(Job).filter_by(kind="align_benchmark").count() == 0


def test_admitted_local_resources_bind_queue_digest_and_are_idempotent(tmp_path):
    with _client(tmp_path, enabled=True, valis=True) as client:
        settings = client.app.state.settings
        declared = {}
        for name, field in (("Disk", "disk"), ("LightGlue", "lightglue")):
            path = tmp_path / (field + "-weights.pth")
            path.write_bytes((field + "-fixture-content").encode())
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            setattr(settings, f"alignment_valis_{field}_weights_path", path)
            setattr(settings, f"alignment_valis_{field}_weights_sha256", digest)
            declared[f"valis{name}WeightsPath"] = str(path)
            declared[f"valis{name}WeightsSha256"] = digest
        headers = _headers(client)
        stack = _stack(client, headers)
        url = f"/api/v1/admin/comparison-sets/{stack['id']}"
        for index in range(2):
            response = client.post(
                url + "/benchmark",
                headers=headers,
                json={"version": stack["version"], "engines": ["valis-1.2.0"]},
            )
            assert response.status_code == 202, response.text
            assert response.json()["queuedCandidates"] == (1 if index == 0 else 0)
        with session_factory(settings)() as database:
            job = database.query(Job).filter_by(kind="align_benchmark").one()
            assert job.checkpoint["engineSettings"] == declared
            assert job.checkpoint["requestedSettingsDigest"] == settings_digest(
                "valis-1.2.0", declared
            )
        Path(declared["valisDiskWeightsPath"]).write_bytes(b"changed-after-admission")
        response = client.post(
            url + "/benchmark",
            headers=headers,
            json={"version": stack["version"], "engines": ["valis-1.2.0"], "rerun": True},
        )
        assert response.status_code == 409


def test_metadata_token_binds_maps_without_explicit_geometry_or_calibration(tmp_path):
    with _client(tmp_path, enabled=True) as client:
        headers = _headers(client)
        stack = _stack(client, headers)
        url = f"/api/v1/admin/comparison-sets/{stack['id']}"
        candidate_id = _candidate(client, stack, {})
        with session_factory(client.app.state.settings)() as database:
            row = database.get(ComparisonRegistrationCandidate, candidate_id)
            token = metadata_frame_digest(database.get(Slide, "slide-2").slide_metadata)
            row.registration = {**row.registration, "sourceFrameVersion": token}
            database.get(ComparisonSet, stack["id"]).registrations = {"slide-2": row.registration}
            database.commit()
        assert client.get(url + "/candidates").json()["candidates"][0]["currentSettings"] is True
        with session_factory(client.app.state.settings)() as database:
            slide = database.get(Slide, "slide-2")
            slide.slide_metadata = {**slide.slide_metadata, "physicalSizeUnit": "nm"}
            database.commit()
        assert client.get(url + "/candidates").json()["candidates"][0]["currentSettings"] is False
        assert client.get(url).json()["members"][1]["registration"]["status"] == "stale"


@pytest.mark.parametrize(
    "x,y,units,expected",
    [
        (500, 1000, {"physicalSizeUnit": "nm"}, (0.5, 1)),
        (0.0005, 0.001, {"physicalSizeUnit": "mm"}, (0.5, 1)),
        (
            0.5,
            1000,
            {"physicalSizeXUnit": "UnitsLength.MICROMETER", "physicalSizeYUnit": "nm"},
            (0.5, 1),
        ),
        (0.5, 1, {"physicalSizeUnit": "µm", "physicalSizeXUnit": None}, (0.5, 1)),
        (0.5, 1, {}, None),
        (0.5, 1, {"physicalSizeUnit": "pixel"}, None),
        (0.5, float("nan"), {"physicalSizeUnit": "um"}, None),
    ],
)
def test_physical_calibration_converts_declared_units_and_rejects_unknown(x, y, units, expected):
    assert (
        normalized_microns_per_pixel({"physicalSizeX": x, "physicalSizeY": y, **units}) == expected
    )
