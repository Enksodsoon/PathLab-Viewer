"""Same-version background publication must not change an inspected correction."""

import pytest
from test_alignment_api import _client, _correction_tiles, _headers
from test_alignment_regions import _request, _stack
from wsi_viewer.database import session_factory
from wsi_viewer.models import ComparisonRegionCorrection, ComparisonSet


def _canonical(scale):
    return {
        "status": "approximate",
        "provenance": "manual",
        "sourceVersion": "sha-2",
        "anchorVersion": "sha-1",
        "anchorSlideId": "slide-1",
        "movingToReference": [[scale, 0, 0], [0, scale, 0]],
        "overviewTriangles": [
            {
                "moving": [[0, 0], [600, 0], [0, 600]],
                "reference": [[0, 0], [600 * scale, 0], [0, 600 * scale]],
            }
        ],
    }


def test_one_point_save_cannot_silently_change_after_same_version_canonical_publication(tmp_path):
    _correction_tiles(tmp_path)
    with _client(tmp_path, enabled=True) as client:
        headers = _headers(client)
        stack, url = _stack(client, headers)
        with session_factory(client.app.state.settings)() as database:
            database.get(ComparisonSet, stack["id"]).registrations = {"slide-2": _canonical(1)}
            database.commit()
        preview = client.post(
            url + "/region-corrections", headers=headers, json=_request(stack["version"])
        )
        assert preview.status_code == 200, preview.text[:300]
        inspected = preview.json()["regionalCorrections"][0]
        assert inspected["registration"]["movingToReference"] == [[1, 0, 20], [0, 1, 30]]
        with session_factory(client.app.state.settings)() as database:
            comparison = database.get(ComparisonSet, stack["id"])
            comparison.registrations = {"slide-2": _canonical(1.2)}
            assert comparison.version == stack["version"]
            database.commit()
        saved = client.post(
            url + "/region-corrections",
            headers=headers,
            json=_request(
                stack["version"],
                operation="save",
                regionId=inspected["regionId"],
                sourceVersion=inspected["sourceVersion"],
                targetVersion=inspected["targetVersion"],
                basisVersion=inspected.get("basisVersion"),
            ),
        )
        assert saved.status_code == 409, saved.text[:300]
        assert saved.json()["detail"]["code"] == "REGION_PREVIEW_CHANGED"
        with session_factory(client.app.state.settings)() as database:
            assert database.query(ComparisonRegionCorrection).count() == 0
            assert database.get(ComparisonSet, stack["id"]).version == stack["version"]
        refreshed = client.post(
            url + "/region-corrections",
            headers=headers,
            json=_request(stack["version"], basisVersion=inspected.get("basisVersion")),
        ).json()["regionalCorrections"][0]
        assert refreshed["basisVersion"] != inspected["basisVersion"]
        saved = client.post(
            url + "/region-corrections",
            headers=headers,
            json=_request(
                stack["version"],
                operation="save",
                regionId=refreshed["regionId"],
                sourceVersion=refreshed["sourceVersion"],
                targetVersion=refreshed["targetVersion"],
                basisVersion=refreshed["basisVersion"],
            ),
        )
        assert saved.status_code == 200, saved.text[:300]
        persisted = saved.json()["regionalCorrections"][0]
        assert (
            persisted["registration"]["movingToReference"]
            == refreshed["registration"]["movingToReference"]
        )
        assert persisted["registration"]["triangles"] == refreshed["registration"]["triangles"]
        assert persisted["sourceBounds"] == refreshed["sourceBounds"]
        with session_factory(client.app.state.settings)() as database:
            assert database.query(ComparisonRegionCorrection).count() == 1
            database.get(ComparisonSet, stack["id"]).registrations = {"slide-2": _canonical(0.9)}
            database.commit()
        assert client.get(url).json()["regionalCorrections"][0] == persisted


def test_one_point_save_requires_an_explicit_preview_basis(tmp_path):
    _correction_tiles(tmp_path)
    with _client(tmp_path, enabled=True) as client:
        headers = _headers(client)
        stack, url = _stack(client, headers)
        request = _request(stack["version"], operation="save")
        request.pop("basisVersion", None)
        result = client.post(url + "/region-corrections", headers=headers, json=request)
        assert result.status_code == 422, result.text[:300]
        assert result.json()["detail"]["code"] == "REGION_PREVIEW_REQUIRED"
        with session_factory(client.app.state.settings)() as database:
            assert database.query(ComparisonRegionCorrection).count() == 0


@pytest.mark.parametrize("count", [1, 2])
def test_same_basis_or_independent_two_point_fit_saves_exact_preview(tmp_path, count):
    _correction_tiles(tmp_path)
    with _client(tmp_path, enabled=True) as client:
        headers = _headers(client)
        stack, url = _stack(client, headers)
        with session_factory(client.app.state.settings)() as database:
            database.get(ComparisonSet, stack["id"]).registrations = {"slide-2": _canonical(1)}
            database.commit()
        points = {"movingPoints": [[150, 150]], "referencePoints": [[170, 180]]}
        if count == 2:
            points = {
                "movingPoints": [[150, 150], [250, 150]],
                "referencePoints": [[170, 180], [290, 180]],
            }
        preview = client.post(
            url + "/region-corrections", headers=headers, json=_request(stack["version"], **points)
        ).json()["regionalCorrections"][0]
        with session_factory(client.app.state.settings)() as database:
            current = _canonical(1.2 if count == 2 else 1)
            current["confidence"] = 0.8  # Harmless receipt updates do not change a one-point basis.
            database.get(ComparisonSet, stack["id"]).registrations = {"slide-2": current}
            database.commit()
        saved = client.post(
            url + "/region-corrections",
            headers=headers,
            json=_request(
                stack["version"],
                operation="save",
                **points,
                sourceVersion=preview["sourceVersion"],
                targetVersion=preview["targetVersion"],
                basisVersion=preview.get("basisVersion"),
            ),
        )
        assert saved.status_code == 200, saved.text[:300]
        assert saved.json()["regionalCorrections"][0]["registration"] == preview["registration"]


@pytest.mark.parametrize("reverse", [False, True])
def test_one_point_offset_preserves_active_regional_scale_and_rotation(tmp_path, reverse):
    _correction_tiles(tmp_path)
    with _client(tmp_path, enabled=True) as client:
        headers = _headers(client)
        stack, url = _stack(client, headers)
        points = {
            "movingPoints": [[150, 150], [250, 150]],
            "referencePoints": [[170, 180], [290, 200]],
        }
        preview = client.post(
            url + "/region-corrections",
            headers=headers,
            json=_request(stack["version"], **points),
        ).json()["regionalCorrections"][0]
        saved = client.post(
            url + "/region-corrections",
            headers=headers,
            json=_request(
                stack["version"],
                operation="save",
                **points,
                sourceVersion=preview["sourceVersion"],
                targetVersion=preview["targetVersion"],
            ),
        )
        assert saved.status_code == 200, saved.text[:300]
        next_points = {"movingPoints": [[180, 180]], "referencePoints": [[210, 227]]}
        expected = [[1.2, -0.2], [0.2, 1.2]]
        if reverse:
            next_points = {
                "sourceSlideId": "slide-1",
                "targetSlideId": "slide-2",
                "sourceBounds": [120, 120, 200, 200],
                "movingPoints": [[200, 222]],
                "referencePoints": [[185, 185]],
            }
            expected = [[1.2 / 1.48, 0.2 / 1.48], [-0.2 / 1.48, 1.2 / 1.48]]
        adjusted = client.post(
            url + "/region-corrections",
            headers=headers,
            json=_request(saved.json()["version"], **next_points),
        )
        assert adjusted.status_code == 200, adjusted.text[:300]
        transform = adjusted.json()["regionalCorrections"][0]["registration"]["movingToReference"]
        for actual, desired in zip(transform, expected, strict=True):
            assert actual[:2] == pytest.approx(desired)


@pytest.mark.parametrize("newer_supported", [False, True])
def test_offset_uses_newest_supported_region_and_skips_unrelated_support(tmp_path, newer_supported):
    _correction_tiles(tmp_path)
    with _client(tmp_path, enabled=True) as client:
        headers = _headers(client)
        stack, url = _stack(client, headers)
        version = stack["version"]
        for points in (
            {"movingPoints": [[150, 150], [250, 150]], "referencePoints": [[170, 180], [290, 200]]},
            {"movingPoints": [[150, 150], [250, 150]], "referencePoints": [[170, 180], [250, 180]]}
            if newer_supported
            else {
                "sourceBounds": [500, 300, 150, 150],
                "movingPoints": [[550, 350], [600, 350]],
                "referencePoints": [[560, 360], [600, 360]],
            },
        ):
            preview = client.post(
                url + "/region-corrections", headers=headers, json=_request(version, **points)
            ).json()["regionalCorrections"][0]
            saved = client.post(
                url + "/region-corrections",
                headers=headers,
                json=_request(
                    version,
                    operation="save",
                    **points,
                    sourceVersion=preview["sourceVersion"],
                    targetVersion=preview["targetVersion"],
                ),
            )
            assert saved.status_code == 200, saved.text[:300]
            version = saved.json()["version"]
        adjusted = client.post(
            url + "/region-corrections",
            headers=headers,
            json=_request(version, movingPoints=[[180, 180]], referencePoints=[[210, 227]]),
        )
        assert adjusted.status_code == 200, adjusted.text[:300]
        transform = adjusted.json()["regionalCorrections"][0]["registration"]["movingToReference"]
        expected = [[0.8, 0], [0, 0.8]] if newer_supported else [[1.2, -0.2], [0.2, 1.2]]
        for actual, desired in zip(transform, expected, strict=True):
            assert actual[:2] == pytest.approx(desired)
