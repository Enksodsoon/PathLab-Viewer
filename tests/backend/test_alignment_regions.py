import hashlib
import json
from pathlib import Path

import pytest
from PIL import Image, ImageDraw
from sqlalchemy import text
from test_alignment_api import _client, _correction_tiles, _headers
from wsi_viewer.alignment import AlignmentRejected, map_registration_point
from wsi_viewer.alignment_regions import content_geometry_version
from wsi_viewer.database import session_factory
from wsi_viewer.domain import SlideState
from wsi_viewer.models import ComparisonRegionCorrection, ComparisonSet, Slide, User
from wsi_viewer.security import hash_password


def _stack(client, headers):
    response = client.post(
        "/api/v1/admin/comparison-sets",
        headers=headers,
        json={
            "name": "Regional tissue",
            "slideIds": ["slide-1", "slide-2", "slide-3"],
            "referenceSlideId": "slide-1",
        },
    )
    assert response.status_code == 201, response.text
    stack = response.json()
    return stack, f"/api/v1/admin/comparison-sets/{stack['id']}"


def _request(version, **overrides):
    frame_metadata = {
        "width": 1000, "height": 800, "physicalSizeX": 0.25,
        "physicalSizeY": 0.25, "physicalSizeUnit": "um",
    }
    return {
        "version": version,
        "operation": "preview",
        "sourceSlideId": "slide-2",
        "targetSlideId": "slide-1",
        "sourceBounds": [100, 100, 200, 200],
        "movingPoints": [[150, 150]],
        "referencePoints": [[170, 180]],
        **(
            {
                "sourceVersion": content_geometry_version("sha-2", frame_metadata),
                "targetVersion": content_geometry_version("sha-1", frame_metadata),
                "basisVersion": "alignment-basis:"
                + hashlib.sha256(
                    json.dumps(
                        {
                            "schema": "alignment-basis/1",
                            "basis": "physical-calibration",
                            "linear": [[1.0, 0.0], [0.0, 1.0]],
                        },
                        sort_keys=True,
                        separators=(",", ":"),
                    ).encode()
                ).hexdigest(),
            }
            if overrides.get("operation") == "save"
            else {}
        ),
        **overrides,
    }


def test_region_offset_preview_is_bounded_and_has_no_durable_side_effect(tmp_path: Path):
    _correction_tiles(tmp_path)
    with _client(tmp_path, enabled=True) as client:
        headers = _headers(client)
        stack, url = _stack(client, headers)
        response = client.post(
            url + "/region-corrections", headers=headers, json=_request(stack["version"])
        )
        assert response.status_code == 200, response.text
        result = response.json()
        overlay = result["regionalCorrections"][0]
        assert overlay["sourceBounds"] == [100, 100, 200, 200]
        assert overlay["sourceVersion"].startswith("alignment:")
        assert overlay["targetVersion"].startswith("alignment:")
        assert overlay["registration"]["status"] == "approximate"
        assert map_registration_point(overlay["registration"], 200, 200) == pytest.approx(
            (220, 230)
        )
        with pytest.raises(AlignmentRejected):
            map_registration_point(overlay["registration"], 310, 150)
        with pytest.raises(AlignmentRejected):
            map_registration_point(overlay["registration"], 400, 150, inverse=True)
        assert result["version"] == stack["version"]
        assert client.get(url).json()["regionalCorrections"] == []


def test_region_two_points_solve_similarity_in_anisotropic_physical_frame(tmp_path: Path):
    _correction_tiles(tmp_path)
    with _client(tmp_path, enabled=True) as client:
        with session_factory(client.app.state.settings)() as database:
            database.get(Slide, "slide-2").slide_metadata = {
                "width": 1000,
                "height": 800,
                "physicalSizeX": 0.5,
                "physicalSizeY": 1,
                "physicalSizeUnit": "um",
            }
            database.get(Slide, "slide-1").slide_metadata = {
                "width": 1000,
                "height": 800,
                "physicalSizeX": 1,
                "physicalSizeY": 0.5,
                "physicalSizeUnit": "um",
            }
            database.commit()
        headers = _headers(client)
        stack, url = _stack(client, headers)
        response = client.post(
            url + "/region-corrections",
            headers=headers,
            json=_request(
                stack["version"],
                movingPoints=[[150, 150], [250, 150]],
                referencePoints=[[600, 200], [600, 400]],
            ),
        )
        assert response.status_code == 200, response.text
        registration = response.json()["regionalCorrections"][0]["registration"]
        assert registration["movingToReference"] == [[0, -2, 900], [2, 0, -100]]
        assert map_registration_point(registration, 200, 200) == pytest.approx((500, 300))


def test_region_save_revision_clear_and_background_maps_are_independent(tmp_path: Path):
    _correction_tiles(tmp_path)
    with _client(tmp_path, enabled=True) as client:
        headers = _headers(client)
        stack, url = _stack(client, headers)
        first = client.post(
            url + "/region-corrections",
            headers=headers,
            json=_request(stack["version"], operation="save"),
        ).json()
        assert first.get("version") == stack["version"] + 1
        first_overlay = first["regionalCorrections"][0]
        second = client.post(
            url + "/region-corrections",
            headers=headers,
            json=_request(
                first["version"],
                operation="save",
                regionId=first_overlay["regionId"],
                referencePoints=[[160, 170]],
            ),
        ).json()
        assert second["version"] == first["version"] + 1
        assert len(second["regionalCorrections"]) == 1
        assert second["regionalCorrections"][0]["id"] != first_overlay["id"]
        with session_factory(client.app.state.settings)() as database:
            item = database.get(ComparisonSet, stack["id"])
            item.registrations = {"slide-2": {"status": "approximate"}}
            database.commit()
        assert client.get(url).json()["regionalCorrections"] == second["regionalCorrections"]
        clear = client.post(
            url + "/region-corrections",
            headers=headers,
            json={
                "version": second["version"],
                "operation": "clear",
                "sourceSlideId": "slide-2",
                "targetSlideId": "slide-1",
                "regionId": first_overlay["regionId"],
            },
        )
        assert clear.status_code == 200, clear.text
        assert clear.json()["regionalCorrections"] == []
        with session_factory(client.app.state.settings)() as database:
            rows = database.execute(
                text(
                    "SELECT operation, registration FROM comparison_region_corrections "
                    "WHERE comparison_set_id=:id ORDER BY set_version"
                ),
                {"id": stack["id"]},
            ).all()
            assert [row.operation for row in rows] == ["save", "save", "clear"]
            assert "170.0" in rows[0].registration


@pytest.mark.parametrize(
    "change",
    [
        {"sourceBounds": [100, 100, -1, 20]},
        {"movingPoints": [[99, 150]]},
        {"referencePoints": [[1001, 150]]},
        {"movingPoints": [[150, 150], [150, 150]], "referencePoints": [[170, 180], [200, 180]]},
        {"movingPoints": [[150, 150], [200, 150]]},
        {"sourceSlideId": "slide-1"},
        {"sourceSlideId": "missing"},
        {"operation": "clear"},
    ],
)
def test_region_invalid_geometry_and_members_are_rejected(tmp_path: Path, change):
    _correction_tiles(tmp_path)
    with _client(tmp_path, enabled=True) as client:
        headers = _headers(client)
        stack, url = _stack(client, headers)
        response = client.post(
            url + "/region-corrections",
            headers=headers,
            json=_request(stack["version"], **{"operation": "save", **change}),
        )
        assert response.status_code in {404, 422}, response.text
        assert client.get(url).json()["version"] == stack["version"]
        assert client.get(url).json()["regionalCorrections"] == []


def test_region_rejects_stale_cross_case_and_unauthorized_writes(tmp_path: Path):
    _correction_tiles(tmp_path)
    with _client(tmp_path, enabled=True) as client:
        headers = _headers(client)
        stack, url = _stack(client, headers)
        payload = _request(stack["version"], operation="save")
        assert client.post(url + "/region-corrections", json=payload).status_code == 403
        stale = client.post(
            url + "/region-corrections",
            headers=headers,
            json={**payload, "version": stack["version"] + 1},
        )
        assert stale.status_code == 409, stale.text
        with session_factory(client.app.state.settings)() as database:
            database.get(Slide, "slide-1").case_id = "specimen-a"
            database.get(Slide, "slide-2").case_id = "specimen-b"
            database.commit()
        response = client.post(url + "/region-corrections", headers=headers, json=payload)
        assert response.status_code == 422, response.text
        assert response.json()["detail"]["code"] == "REGION_CASE_MISMATCH"
        client.cookies.clear()
        assert (
            client.post(url + "/region-corrections", headers=headers, json=payload).status_code
            == 401
        )


@pytest.mark.parametrize("slide_id", ["slide-1", "slide-2"])
def test_region_support_excludes_glass_inside_bounds_on_either_slide(tmp_path: Path, slide_id):
    _correction_tiles(tmp_path)
    tile = tmp_path / "data" / "private" / slide_id / "slide_files" / "10" / "0_0.jpeg"
    with Image.open(tile) as image:
        image = image.copy()
    ImageDraw.Draw(image).rectangle((220, 220, 260, 260), fill="white")
    image.save(tile)
    with _client(tmp_path, enabled=True) as client:
        headers = _headers(client)
        stack, url = _stack(client, headers)
        response = client.post(
            url + "/region-corrections",
            headers=headers,
            json=_request(stack["version"], referencePoints=[[150, 150]]),
        )
        assert response.status_code == 200, response.text
        registration = response.json()["regionalCorrections"][0]["registration"]
        with pytest.raises(AlignmentRejected):
            map_registration_point(registration, 240, 240)
        rejected = client.post(
            url + "/region-corrections",
            headers=headers,
            json=_request(
                stack["version"], movingPoints=[[240, 240]], referencePoints=[[240, 240]]
            ),
        )
        assert rejected.status_code == 422, rejected.text


@pytest.mark.parametrize("missing_digest", [False, True])
def test_saved_region_is_hidden_after_source_replacement(tmp_path: Path, missing_digest):
    _correction_tiles(tmp_path)
    with _client(tmp_path, enabled=True) as client:
        if missing_digest:
            with session_factory(client.app.state.settings)() as database:
                database.get(Slide, "slide-2").sha256 = None
                database.commit()
        headers = _headers(client)
        stack, url = _stack(client, headers)
        preview = client.post(
            url + "/region-corrections", headers=headers, json=_request(stack["version"])
        ).json()["regionalCorrections"][0]
        response = client.post(
            url + "/region-corrections",
            headers=headers,
            json=_request(
                stack["version"],
                operation="save",
                sourceVersion=preview["sourceVersion"],
                targetVersion=preview["targetVersion"],
            ),
        )
        assert response.status_code == 200, response.text
        assert response.json()["regionalCorrections"][0]["sourceVersion"]
        with session_factory(client.app.state.settings)() as database:
            slide = database.get(Slide, "slide-2")
            if missing_digest:
                slide.display_name = "Replacement without digest"
            else:
                slide.sha256 = "replacement-sha"
            database.commit()
        assert client.get(url).json()["regionalCorrections"] == []


@pytest.mark.parametrize("operation", ["preview", "save"])
@pytest.mark.parametrize(
    "slide_id,version_key", [("slide-2", "sourceVersion"), ("slide-1", "targetVersion")]
)
def test_region_rejects_preview_snapshot_after_digestless_source_changes(
    tmp_path: Path, operation, slide_id, version_key
):
    _correction_tiles(tmp_path)
    with _client(tmp_path, enabled=True) as client:
        factory = session_factory(client.app.state.settings)
        with factory() as database:
            database.get(Slide, slide_id).sha256 = None
            database.commit()
        headers = _headers(client)
        stack, url = _stack(client, headers)
        preview = client.post(
            url + "/region-corrections", headers=headers, json=_request(stack["version"])
        ).json()["regionalCorrections"][0]
        assert preview[version_key].startswith("alignment:")
        with factory() as database:
            database.get(Slide, slide_id).display_name = "Source replaced after preview"
            database.commit()
        response = client.post(
            url + "/region-corrections",
            headers=headers,
            json=_request(
                stack["version"],
                operation=operation,
                regionId=preview["regionId"],
                sourceVersion=preview["sourceVersion"],
                targetVersion=preview["targetVersion"],
            ),
        )
        assert response.status_code == 409, response.text
        assert response.json()["detail"]["code"] == "COMPARISON_SOURCE_CHANGED"
        assert client.get(url).json()["version"] == stack["version"]
        assert client.get(url).json()["regionalCorrections"] == []
        with factory() as database:
            assert database.query(ComparisonRegionCorrection).count() == 0


@pytest.mark.parametrize("missing", ["sourceVersion", "targetVersion", "both"])
def test_region_save_requires_explicit_source_snapshots(tmp_path: Path, missing):
    _correction_tiles(tmp_path)
    with _client(tmp_path, enabled=True) as client:
        headers = _headers(client)
        stack, url = _stack(client, headers)
        payload = _request(stack["version"], operation="save")
        for key in ("sourceVersion", "targetVersion"):
            if missing in (key, "both"):
                payload.pop(key)
        response = client.post(url + "/region-corrections", headers=headers, json=payload)
        assert response.status_code == 422, response.text
        assert response.json()["detail"]["code"] == "REGION_SOURCE_VERSIONS_REQUIRED"
        assert client.get(url).json()["regionalCorrections"] == []


@pytest.mark.parametrize("change", [
    {"width": 1100}, {"height": 900}, {"physicalSizeX": .5},
    {"physicalSizeY": .5}, {"physicalSizeUnit": "nm"},
])
def test_region_same_sha_geometry_change_hides_revision_and_rejects_old_preview(tmp_path, change):
    _correction_tiles(tmp_path)
    with _client(tmp_path, enabled=True) as client:
        headers = _headers(client)
        stack, url = _stack(client, headers)
        preview = client.post(url + "/region-corrections", headers=headers,
                              json=_request(stack["version"])).json()["regionalCorrections"][0]
        saved = client.post(url + "/region-corrections", headers=headers,
                            json=_request(stack["version"], operation="save",
                                          sourceVersion=preview["sourceVersion"],
                                          targetVersion=preview["targetVersion"],
                                          regionId=preview["regionId"]))
        assert saved.status_code == 200
        with session_factory(client.app.state.settings)() as database:
            source = database.get(Slide, "slide-2")
            source.slide_metadata = {**source.slide_metadata, **change}
            database.commit()
        reloaded = client.get(url).json()
        assert reloaded["regionalCorrections"] == []
        response = client.post(url + "/region-corrections", headers=headers,
                               json=_request(saved.json()["version"], operation="save",
                                             sourceVersion=preview["sourceVersion"],
                                             targetVersion=preview["targetVersion"],
                                             regionId=preview["regionId"]))
        assert response.status_code == 409
        with session_factory(client.app.state.settings)() as database:
            assert database.query(ComparisonRegionCorrection).count() == 1


def test_region_calibration_normalizes_declared_units_and_missing_units_is_uncalibrated():
    from wsi_viewer.alignment_regions import _calibration
    assert _calibration({"physicalSizeX": 500, "physicalSizeY": 1000,
                         "physicalSizeUnit": "UnitsLength.NANOMETER"}).tolist() == [.5, 1]
    assert _calibration({"physicalSizeX": .25, "physicalSizeY": .25}) is None
    assert _calibration({"physicalSizeX": .25, "physicalSizeY": .25,
                         "physicalSizeUnit": "pixel"}) is None


@pytest.mark.parametrize("endpoint", ["", "/members"])
@pytest.mark.parametrize(
    "anchors",
    [
        {"slide-2": "slide-2"},
        {"slide-2": "slide-3", "slide-3": "slide-2"},
        {"slide-1": "slide-2"},
    ],
)
def test_anchor_self_cycles_and_primary_outgoing_edges_rejected(tmp_path: Path, endpoint, anchors):
    with _client(tmp_path, enabled=True) as client:
        headers = _headers(client)
        stack, url = _stack(client, headers)
        payload = (
            {"version": stack["version"], "anchors": anchors}
            if not endpoint
            else {
                "version": stack["version"],
                "add": [
                    {"slideId": source, "anchorSlideId": target}
                    for source, target in anchors.items()
                ],
            }
        )
        response = client.patch(url + endpoint, headers=headers, json=payload)
        assert response.status_code == 422, response.text
        assert client.get(url).json()["version"] == stack["version"]


def test_explicit_empty_anchors_clears_prior_overrides(tmp_path: Path):
    with _client(tmp_path, enabled=True) as client:
        headers = _headers(client)
        stack, url = _stack(client, headers)
        changed = client.patch(
            url,
            headers=headers,
            json={
                "version": stack["version"],
                "anchors": {"slide-3": "slide-2"},
            },
        ).json()
        response = client.patch(
            url, headers=headers, json={"version": changed["version"], "anchors": {}}
        )
        assert response.status_code == 200, response.text
        assert response.json()["alignmentConfig"]["anchors"] == {}
        assert response.json()["version"] == changed["version"] + 1
        assert response.json()["members"][2]["anchorSlideId"] == "slide-1"


def test_preview_region_identity_can_be_repreviewed_and_saved(tmp_path: Path):
    _correction_tiles(tmp_path)
    with _client(tmp_path, enabled=True) as client:
        headers = _headers(client)
        stack, url = _stack(client, headers)
        first = client.post(
            url + "/region-corrections", headers=headers, json=_request(stack["version"])
        ).json()
        region_id = first["regionalCorrections"][0]["regionId"]
        for operation in ("preview", "save"):
            response = client.post(
                url + "/region-corrections",
                headers=headers,
                json=_request(stack["version"], operation=operation, regionId=region_id),
            )
            assert response.status_code == 200, response.text
            assert response.json()["regionalCorrections"][0]["regionId"] == region_id


def test_one_point_uses_reverse_coarse_map_for_primary_as_source(tmp_path: Path):
    _correction_tiles(tmp_path)
    with _client(tmp_path, enabled=True) as client:
        headers = _headers(client)
        stack, url = _stack(client, headers)
        with session_factory(client.app.state.settings)() as database:
            database.get(ComparisonSet, stack["id"]).registrations = {
                "slide-2": {
                    "status": "approximate",
                    "provenance": "manual",
                    "sourceVersion": "sha-2",
                    "anchorVersion": "sha-1",
                    "anchorSlideId": "slide-1",
                    "overviewTriangles": [
                        {
                            "moving": [[0, 0], [500, 0], [0, 800]],
                            "reference": [[0, 0], [1000, 0], [0, 800]],
                        }
                    ],
                }
            }
            database.commit()
        response = client.post(
            url + "/region-corrections",
            headers=headers,
            json=_request(
                stack["version"],
                sourceSlideId="slide-1",
                targetSlideId="slide-2",
                referencePoints=[[300, 300]],
            ),
        )
        assert response.status_code == 200, response.text
        registration = response.json()["regionalCorrections"][0]["registration"]
        assert map_registration_point(registration, 200, 200) == pytest.approx((325, 350))
        assert registration["evidence"]["basis"] == "compatible-local-map"


@pytest.mark.parametrize("calibrated", [False, True])
def test_one_point_scale_uses_both_axes_or_truthful_pixel_identity(tmp_path: Path, calibrated):
    _correction_tiles(tmp_path)
    with _client(tmp_path, enabled=True) as client:
        with session_factory(client.app.state.settings)() as database:
            metadata = {"width": 1000, "height": 800}
            if calibrated:
                metadata.update(physicalSizeX=0.5, physicalSizeY=0.125, physicalSizeUnit="um")
            database.get(Slide, "slide-2").slide_metadata = metadata
            database.commit()
        headers = _headers(client)
        stack, url = _stack(client, headers)
        response = client.post(
            url + "/region-corrections", headers=headers, json=_request(stack["version"])
        )
        assert response.status_code == 200, response.text
        registration = response.json()["regionalCorrections"][0]["registration"]
        assert map_registration_point(registration, 200, 200) == pytest.approx(
            (270, 205) if calibrated else (220, 230)
        )
        assert registration["evidence"]["calibrated"] == calibrated
        assert registration["evidence"]["basis"] == (
            "physical-calibration" if calibrated else "pixel-identity"
        )


def test_region_rejects_source_version_changed_since_stack_snapshot(tmp_path: Path):
    _correction_tiles(tmp_path)
    with _client(tmp_path, enabled=True) as client:
        headers = _headers(client)
        stack, url = _stack(client, headers)
        with session_factory(client.app.state.settings)() as database:
            database.get(Slide, "slide-2").sha256 = "changed-after-create"
            database.commit()
        response = client.post(
            url + "/region-corrections",
            headers=headers,
            json=_request(stack["version"], operation="save"),
        )
        assert response.status_code == 409, response.text
        assert response.json()["detail"]["code"] == "COMPARISON_SOURCE_CHANGED"
        assert client.get(url).json()["regionalCorrections"] == []


def test_region_nonfinite_points_do_not_persist(tmp_path: Path):
    _correction_tiles(tmp_path)
    with _client(tmp_path, enabled=True) as client:
        headers = _headers(client)
        stack, url = _stack(client, headers)
        for value in ("NaN", "Infinity", "-Infinity"):
            response = client.post(
                url + "/region-corrections",
                headers=headers,
                json=_request(stack["version"], operation="save", movingPoints=[[value, 150]]),
            )
            assert response.status_code == 422, response.text
        assert client.get(url).json()["regionalCorrections"] == []


def test_region_landmark_images_unavailable_is_fail_closed(tmp_path: Path):
    with _client(tmp_path, enabled=True) as client:
        headers = _headers(client)
        stack, url = _stack(client, headers)
        response = client.post(
            url + "/region-corrections",
            headers=headers,
            json=_request(stack["version"], operation="save"),
        )
        assert response.status_code == 503, response.text
        assert response.json()["detail"]["code"] == "LANDMARK_IMAGE_UNAVAILABLE"
        assert client.get(url).json()["regionalCorrections"] == []


def test_region_save_rejects_non_admin_even_with_valid_csrf(tmp_path: Path):
    _correction_tiles(tmp_path)
    with _client(tmp_path, enabled=True) as client:
        headers = _headers(client)
        stack, url = _stack(client, headers)
        with session_factory(client.app.state.settings)() as database:
            database.add(User(username="viewer", password_hash=hash_password("viewer password")))
            database.commit()
        client.cookies.clear()
        logged_in = client.post(
            "/api/v1/auth/session",
            json={
                "username": "viewer",
                "password": "viewer password",
            },
        )
        assert logged_in.status_code == 201, logged_in.text
        response = client.post(
            url + "/region-corrections",
            headers={"X-CSRF-Token": logged_in.json()["csrfToken"]},
            json=_request(stack["version"], operation="save"),
        )
        assert response.status_code == 403, response.text
        assert response.json()["detail"]["code"] == "LEGACY_ADMIN_FORBIDDEN"


def test_region_migration_preserves_existing_sets_and_stores_revisions(tmp_path: Path, monkeypatch):
    from test_readiness import _settings, _upgrade

    settings = _settings(tmp_path, "regions-migration.sqlite3")
    _upgrade(settings, "20260921_0042", monkeypatch)
    with session_factory(settings)() as database:
        for slide_id in ("slide-1", "slide-2"):
            database.add(
                Slide(
                    id=slide_id,
                    public_id=slide_id,
                    display_name=slide_id,
                    original_filename="synthetic.tiff",
                    source_bytes=100,
                    state=SlideState.READY_PRIVATE,
                )
            )
        database.flush()
        database.add(
            ComparisonSet(
                id="set-1",
                name="Existing set",
                reference_slide_id="slide-1",
                member_slide_ids=["slide-1", "slide-2"],
                source_versions={"slide-1": None, "slide-2": None},
            )
        )
        database.commit()
    _upgrade(settings, "20261003_0043", monkeypatch)
    with session_factory(settings)() as database:
        assert database.get(ComparisonSet, "set-1").name == "Existing set"
        database.add(
            ComparisonRegionCorrection(
                comparison_set_id="set-1",
                region_id="region-1",
                source_slide_id="slide-2",
                target_slide_id="slide-1",
                source_version="source-v1",
                target_version="target-v1",
                set_version=2,
                operation="save",
                source_bounds=[100, 100, 200, 200],
                registration={"status": "approximate"},
            )
        )
        database.commit()
        assert database.query(ComparisonRegionCorrection).one().source_version == "source-v1"
