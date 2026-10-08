"""Source-content admission and serving exercised through real database/API paths."""

from datetime import timedelta

import pytest
from PIL import Image
from test_alignment_api import _client, _correction_tiles, _headers
from test_alignment_engine_routes import _stack
from wsi_viewer import alignment_routes
from wsi_viewer.database import session_factory
from wsi_viewer.models import ComparisonRegistrationRevision, ComparisonSet, Job, Slide
from wsi_viewer.storage import StorageLayout
from wsi_viewer.worker import _best_compatible_registration, process_next


@pytest.mark.parametrize("changed_id", ["slide-2", "slide-1"])
def test_null_sha_manual_map_becomes_stale_when_source_pixels_change(
    tmp_path, monkeypatch, changed_id
):
    _correction_tiles(tmp_path)
    with _client(tmp_path, enabled=True) as client:
        headers = _headers(client)
        with session_factory(client.app.state.settings)() as database:
            database.get(Slide, changed_id).sha256 = None
            database.commit()
        stack = _stack(client, headers)
        url = f"/api/v1/admin/comparison-sets/{stack['id']}"
        saved = client.put(
            url + "/corrections/slide-2",
            headers=headers,
            json={
                "version": stack["version"],
                "referenceSlideId": "slide-1",
                "referencePoints": [[100, 100], [500, 100], [100, 500]],
                "movingPoints": [[120, 110], [520, 110], [120, 510]],
                "previewOnly": False,
            },
        )
        assert saved.status_code == 200, saved.text
        assert client.get(url).json()["members"][1]["registration"]["status"] == "ready"
        with session_factory(client.app.state.settings)() as database:
            assert (
                _best_compatible_registration(
                    database,
                    comparison=database.get(ComparisonSet, stack["id"]),
                    slide=database.get(Slide, "slide-2"),
                    reference=database.get(Slide, "slide-1"),
                )["status"]
                == "ready"
            )
        tile = (
            StorageLayout(client.app.state.settings.data_root)
            .for_slide(changed_id)
            .private_derivative
            / "slide_files"
            / "10"
            / "0_0.jpeg"
        )
        Image.new("RGB", (1000, 800), (110, 150, 180)).save(tile)
        with session_factory(client.app.state.settings)() as database:
            moving = database.get(Slide, changed_id)
            moving.updated_at += timedelta(seconds=10)
            database.commit()
        response = client.get(url).json()["members"][1]["registration"]
        assert response["status"] == "stale"
        assert response["triangles"] == []
        observed = []
        build = alignment_routes.build_region_registration

        def observe_initializer(*args, **kwargs):
            observed.append(kwargs.get("previous"))
            return build(*args, **kwargs)

        monkeypatch.setattr(alignment_routes, "build_region_registration", observe_initializer)
        regional = client.post(
            url + "/region-corrections",
            headers=headers,
            json={
                "version": saved.json()["version"],
                "operation": "preview",
                "sourceSlideId": "slide-2",
                "targetSlideId": "slide-1",
                "sourceBounds": [100, 100, 200, 200],
                "movingPoints": [[240, 240]],
                "referencePoints": [[240, 240]],
            },
        )
        assert regional.status_code == 200, regional.text
        assert observed[0]["status"] == "stale"
        assert observed[0]["triangles"] == []
        with session_factory(client.app.state.settings)() as database:
            assert (
                _best_compatible_registration(
                    database,
                    comparison=database.get(ComparisonSet, stack["id"]),
                    slide=database.get(Slide, "slide-2"),
                    reference=database.get(Slide, "slide-1"),
                )
                is None
            )
            assert (
                database.get(ComparisonSet, stack["id"]).registrations["slide-2"]["status"]
                == "ready"
            )


@pytest.mark.parametrize("null_sha", [True, False])
def test_missing_null_sha_snapshot_stales_legacy_map_but_valid_sha_cosmetic_edit_remains_current(
    tmp_path, null_sha
):
    _correction_tiles(tmp_path)
    with _client(tmp_path, enabled=True) as client:
        headers = _headers(client)
        if null_sha:
            with session_factory(client.app.state.settings)() as database:
                database.get(Slide, "slide-2").sha256 = None
                database.commit()
        stack = _stack(client, headers)
        url = f"/api/v1/admin/comparison-sets/{stack['id']}"
        saved = client.put(
            url + "/corrections/slide-2",
            headers=headers,
            json={
                "version": stack["version"],
                "referenceSlideId": "slide-1",
                "referencePoints": [[100, 100], [500, 100], [100, 500]],
                "movingPoints": [[120, 110], [520, 110], [120, 510]],
            },
        )
        assert saved.status_code == 200, saved.text
        with session_factory(client.app.state.settings)() as database:
            comparison = database.get(ComparisonSet, stack["id"])
            legacy = dict(comparison.registrations["slide-2"])
            legacy.pop("sourceSnapshotVersion", None)
            comparison.registrations = {"slide-2": legacy}
            revision = database.query(ComparisonRegistrationRevision).one()
            revision.registration = legacy
            moving = database.get(Slide, "slide-2")
            moving.display_name = "Cosmetic name edit"
            moving.updated_at += timedelta(seconds=10)
            database.commit()
            selected = _best_compatible_registration(
                database,
                comparison=comparison,
                slide=moving,
                reference=database.get(Slide, "slide-1"),
            )
            assert (selected is None) is null_sha
        served = client.get(url).json()["members"][1]["registration"]
        assert served["status"] == ("stale" if null_sha else "ready")


def test_null_sha_automatic_job_never_enters_registration(tmp_path, monkeypatch):
    with _client(tmp_path, enabled=True) as client:
        headers = _headers(client)
        stack = _stack(client, headers)
        with session_factory(client.app.state.settings)() as database:
            database.get(Slide, "slide-2").sha256 = None
            database.commit()
        calls = []
        monkeypatch.setattr(
            "wsi_viewer.worker._run_alignment_bounded", lambda *a, **k: calls.append(1)
        )
        monkeypatch.setattr("wsi_viewer.worker._preview_alignment", lambda *a, **k: calls.append(1))
        settings = client.app.state.settings
        assert process_next(session_factory(settings), StorageLayout(settings.data_root))
        assert calls == []
        with session_factory(settings)() as database:
            job = database.query(Job).filter_by(slide_id="slide-2", kind="align").one()
            assert job.status == "failed_terminal"
            assert job.failure_code == "ALIGNMENT_SOURCE_CHANGED"
            assert database.get(ComparisonSet, stack["id"]).registrations == {}
