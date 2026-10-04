"""Candidate preview requires affirmative bindings beyond adapter currency."""

from copy import deepcopy
from datetime import timedelta

import pytest
from test_alignment_api import _client, _headers
from test_alignment_engine_routes import _hybrid_candidate
from test_alignment_regions import _stack
from wsi_viewer.alignment_calibration import metadata_frame_digest
from wsi_viewer.alignment_engines import ENGINE_NATIVE_OVERVIEW, settings_digest
from wsi_viewer.alignment_fast import PREPARATION_VERSION
from wsi_viewer.alignment_regions import slide_version
from wsi_viewer.database import session_factory
from wsi_viewer.models import (
    ComparisonRegistrationCandidate,
    ComparisonSet,
    ComparisonSetMember,
    Slide,
)


def _bound_candidate(client, stack, *, null_sha=False):
    with session_factory(client.app.state.settings)() as database:
        candidate_id, saved = _hybrid_candidate(database, stack, engine=ENGINE_NATIVE_OVERVIEW)
        row = database.get(ComparisonRegistrationCandidate, candidate_id)
        source, anchor = database.get(Slide, "slide-2"), database.get(Slide, "slide-1")
        if null_sha:
            source.sha256 = anchor.sha256 = None
            comparison = database.get(ComparisonSet, stack["id"])
            comparison.source_versions = {
                **comparison.source_versions,
                "slide-2": None,
                "slide-1": None,
            }
            row.source_version = row.anchor_version = None
            database.flush()
        row.registration = {
            **row.registration,
            "engine": row.engine,
            "engineVersion": row.engine_version,
            "engineSettings": {},
            "settingsDigest": row.settings_digest,
            "provenance": "automatic-candidate",
            "sourceFrameVersion": metadata_frame_digest(source.slide_metadata),
            "anchorFrameVersion": metadata_frame_digest(anchor.slide_metadata),
            **(
                {
                    "sourceSnapshotVersion": slide_version(source),
                    "anchorSnapshotVersion": slide_version(anchor),
                }
                if null_sha
                else {}
            ),
        }
        database.commit()
        return candidate_id, deepcopy(row.registration), saved


def _manifest(client, url):
    return client.get(url + "/candidates").json()["candidates"][0]


def test_fresh_candidate_projects_verified_tokens_without_mutating_rows_or_canonical(tmp_path):
    with _client(tmp_path, enabled=True) as client:
        headers = _headers(client)
        stack, url = _stack(client, headers)
        candidate_id, original, saved = _bound_candidate(client, stack)
        candidate = _manifest(client, url)
        assert candidate["currentSettings"] is True
        assert candidate.get("currentPair") is True
        members = {member["slideId"]: member for member in client.get(url).json()["members"]}
        assert candidate["sourceSnapshotVersion"] == members["slide-2"]["alignmentSourceVersion"]
        assert candidate["anchorSnapshotVersion"] == members["slide-1"]["alignmentSourceVersion"]
        with session_factory(client.app.state.settings)() as database:
            assert (
                database.get(ComparisonRegistrationCandidate, candidate_id).registration == original
            )
            assert database.get(ComparisonSet, stack["id"]).registrations == {"slide-2": saved}


@pytest.mark.parametrize("side", ["source", "anchor"])
def test_old_manifest_tokens_reject_real_case_change_without_comparison_revision(tmp_path, side):
    with _client(tmp_path, enabled=True) as client:
        headers = _headers(client)
        response = client.post(
            "/api/v2/admin/slides/batch-metadata", headers=headers,
            json={"slideIds": ["slide-1", "slide-2"], "caseId": "case-A"},
        )
        assert response.status_code == 200, response.text
        stack, url = _stack(client, headers)
        candidate_id, registration, _ = _bound_candidate(client, stack)
        with session_factory(client.app.state.settings)() as database:
            database.get(ComparisonSet, stack["id"]).registrations = {
                "slide-2": _native(registration),
            }
            regional_tokens = {
                name: slide_version(database.get(Slide, name)) for name in ("slide-1", "slide-2")
            }
            source_versions = dict(database.get(ComparisonSet, stack["id"]).source_versions)
            database.commit()
        old_manifest = _manifest(client, url)
        old_comparison = client.get(url).json()
        assert old_manifest["currentPair"] is True
        old_members = {member["slideId"]: member for member in old_comparison["members"]}
        assert old_members["slide-2"]["nativeOverviewFallback"] is not None
        changed_id = "slide-2" if side == "source" else "slide-1"
        response = client.post(
            "/api/v2/admin/slides/batch-metadata", headers=headers,
            json={"slideIds": [changed_id], "caseId": "case-B"},
        )
        assert response.status_code == 200, response.text
        fresh = client.get(url).json()
        members = {member["slideId"]: member for member in fresh["members"]}
        assert fresh["version"] == old_comparison["version"] == stack["version"]
        assert members["slide-2"]["nativeOverviewFallback"] is None
        assert members["slide-2"]["registration"]["status"] == "rejected"
        assert _manifest(client, url)["currentPair"] is False
        with session_factory(client.app.state.settings)() as database:
            assert database.get(ComparisonSet, stack["id"]).source_versions == source_versions
            assert database.get(Slide, "slide-1").sha256 == "sha-1"
            assert database.get(Slide, "slide-2").sha256 == "sha-2"
            row = database.get(ComparisonRegistrationCandidate, candidate_id)
            assert row.registration == registration
            assert {
                name: slide_version(database.get(Slide, name)) for name in regional_tokens
            } == regional_tokens
        token_field = "sourceSnapshotVersion" if side == "source" else "anchorSnapshotVersion"
        assert old_manifest[token_field] != members[changed_id]["alignmentSourceVersion"]


@pytest.mark.parametrize("side", ["source", "anchor"])
@pytest.mark.parametrize("change", ["unready", "trashed"])
def test_old_manifest_tokens_reject_changed_member_eligibility(tmp_path, side, change):
    from wsi_viewer.domain import SlideState

    with _client(tmp_path, enabled=True) as client:
        headers = _headers(client)
        stack, url = _stack(client, headers)
        candidate_id, original, _ = _bound_candidate(client, stack)
        old_manifest = _manifest(client, url)
        assert old_manifest["currentPair"] is True
        changed_id = "slide-2" if side == "source" else "slide-1"
        with session_factory(client.app.state.settings)() as database:
            slide = database.get(Slide, changed_id)
            regional_token = slide_version(slide)
            if change == "unready":
                slide.state = SlideState.FAILED
            else:
                slide.trashed_at = slide.updated_at
            database.commit()
        fresh = client.get(url).json()
        member = next(member for member in fresh["members"] if member["slideId"] == changed_id)
        assert fresh["version"] == stack["version"]
        assert member["tileSource"] is None
        assert member["availabilityReason"] is not None
        token_field = "sourceSnapshotVersion" if side == "source" else "anchorSnapshotVersion"
        assert old_manifest[token_field] != member["alignmentSourceVersion"]
        assert _manifest(client, url)["currentPair"] is False
        with session_factory(client.app.state.settings)() as database:
            assert slide_version(database.get(Slide, changed_id)) == regional_token
            assert (
                database.get(ComparisonRegistrationCandidate, candidate_id).registration == original
            )


def test_preview_snapshot_normalizes_case_and_preserves_sha_bound_cosmetic_changes(tmp_path):
    with _client(tmp_path, enabled=True) as client:
        headers = _headers(client)
        response = client.post(
            "/api/v2/admin/slides/batch-metadata", headers=headers,
            json={"slideIds": ["slide-1", "slide-2"], "caseId": " Case-A "},
        )
        assert response.status_code == 200
        stack, url = _stack(client, headers)
        _bound_candidate(client, stack)
        before = _manifest(client, url)
        response = client.post(
            "/api/v2/admin/slides/batch-metadata", headers=headers,
            json={"slideIds": ["slide-2"], "caseId": "case-a", "displayName": "Renamed"},
        )
        assert response.status_code == 200
        after = _manifest(client, url)
        assert before["currentPair"] is after["currentPair"] is True
        assert before["sourceSnapshotVersion"] == after["sourceSnapshotVersion"]
        assert before["anchorSnapshotVersion"] == after["anchorSnapshotVersion"]
        fresh = client.get(url).json()
        assert fresh["version"] == stack["version"]
        source = next(member for member in fresh["members"] if member["slideId"] == "slide-2")
        assert source["alignmentSourceVersion"] == before["sourceSnapshotVersion"]


@pytest.mark.parametrize(
    "change",
    [
        "source-sha",
        "anchor-sha",
        "version",
        "parent",
        "source-frame",
        "anchor-calibration",
        "source-missing-frame",
        "anchor-missing-frame",
        "source-missing-version",
        "coordinate-reference",
        "source-unready",
        "anchor-trashed",
        "case",
        "removed-parent",
    ],
)
def test_candidate_pair_proof_rejects_stale_or_missing_binding(tmp_path, change):
    with _client(tmp_path, enabled=True) as client:
        headers = _headers(client)
        stack, url = _stack(client, headers)
        candidate_id, _, _ = _bound_candidate(client, stack)
        with session_factory(client.app.state.settings)() as database:
            row = database.get(ComparisonRegistrationCandidate, candidate_id)
            source, anchor = database.get(Slide, "slide-2"), database.get(Slide, "slide-1")
            comparison = database.get(ComparisonSet, stack["id"])
            if change == "source-sha":
                source.sha256 = "new-moving-pixels"
                comparison.source_versions = {
                    **comparison.source_versions,
                    source.id: source.sha256,
                }
            elif change == "anchor-sha":
                anchor.sha256 = "new-reference-pixels"
                comparison.source_versions = {
                    **comparison.source_versions,
                    anchor.id: anchor.sha256,
                }
            elif change == "version":
                comparison.version += 1
            elif change == "parent":
                for member in database.query(ComparisonSetMember).filter_by(
                    comparison_set_id=stack["id"]
                ):
                    if member.slide_id == "slide-2":
                        member.anchor_slide_id = "slide-3"
            elif change == "source-frame":
                source.slide_metadata = {**source.slide_metadata, "width": 1100}
            elif change == "anchor-calibration":
                anchor.slide_metadata = {
                    **anchor.slide_metadata,
                    "physicalSizeY": 0.5,
                    "physicalSizeYUnit": "nm",
                }
            elif change in {"source-missing-frame", "anchor-missing-frame"}:
                registration = dict(row.registration)
                registration.pop(
                    "sourceFrameVersion" if change.startswith("source") else "anchorFrameVersion"
                )
                row.registration = registration
            elif change == "source-missing-version":
                row.source_version = None
            elif change == "coordinate-reference":
                row.registration = {**row.registration, "coordinateReferenceId": "slide-3"}
            elif change == "source-unready":
                from wsi_viewer.domain import SlideState

                source.state = SlideState.FAILED
            elif change == "anchor-trashed":
                anchor.trashed_at = anchor.updated_at
            elif change == "case":
                source.case_id, anchor.case_id = "case-A", "case-B"
            elif change == "removed-parent":
                database.query(ComparisonSetMember).filter_by(
                    comparison_set_id=stack["id"], slide_id="slide-1"
                ).delete()
            database.commit()
        candidate = _manifest(client, url)
        # Falls back to the old admission field to prove the pre-contract defect.
        assert candidate.get("currentPair", candidate["currentSettings"]) is False, change
        assert candidate.get("sourceSnapshotVersion") is None
        assert candidate.get("anchorSnapshotVersion") is None


@pytest.mark.parametrize(
    "change", ["unchanged", "source-update", "anchor-update", "missing-snapshot"]
)
def test_null_sha_candidate_requires_current_explicit_snapshots(tmp_path, change):
    with _client(tmp_path, enabled=True) as client:
        headers = _headers(client)
        stack, url = _stack(client, headers)
        candidate_id, _, _ = _bound_candidate(client, stack, null_sha=True)
        with session_factory(client.app.state.settings)() as database:
            if change in {"source-update", "anchor-update"}:
                slide = database.get(Slide, "slide-2" if change.startswith("source") else "slide-1")
                slide.updated_at += timedelta(seconds=1)
            elif change == "missing-snapshot":
                row = database.get(ComparisonRegistrationCandidate, candidate_id)
                registration = dict(row.registration)
                registration.pop("sourceSnapshotVersion")
                row.registration = registration
            database.commit()
        candidate = _manifest(client, url)
        assert candidate.get("currentPair") is (change == "unchanged")


def _native(registration):
    return {
        **registration,
        "status": "approximate",
        "provenance": "automatic",
        "sourceVersion": "sha-2",
        "anchorVersion": "sha-1",
        "evidence": {"phase": "preview", "preparationVersion": PREPARATION_VERSION},
    }


@pytest.mark.parametrize("nested", [False, True])
@pytest.mark.parametrize(
    "change",
    [
        "unchanged",
        "missing-frame",
        "wrong-sha",
        "wrong-parent",
        "missing-phase",
        "wrong-phase",
        "missing-preparation",
        "wrong-preparation",
    ],
)
def test_only_bound_current_native_overview_is_projected_for_fallback(tmp_path, nested, change):
    with _client(tmp_path, enabled=True) as client:
        headers = _headers(client)
        stack, url = _stack(client, headers)
        _, registration, _ = _bound_candidate(client, stack)
        native = _native(registration)
        if change == "missing-frame":
            native.pop("sourceFrameVersion")
        elif change == "wrong-sha":
            native["sourceVersion"] = "old-pixels"
        elif change == "wrong-parent":
            native["coordinateReferenceId"] = "slide-3"
        elif change in {"missing-phase", "wrong-phase", "missing-preparation", "wrong-preparation"}:
            evidence = dict(native["evidence"])
            if change == "missing-phase":
                evidence.pop("phase")
            elif change == "wrong-phase":
                evidence["phase"] = "candidate"
            elif change == "missing-preparation":
                evidence.pop("preparationVersion")
                evidence.pop("phase")
            else:
                evidence["preparationVersion"] = "old-preparation"
                evidence.pop("phase")
            native["evidence"] = evidence
        with session_factory(client.app.state.settings)() as database:
            canonical = (
                {"status": "approximate", "provenance": "manual", "overviewFallback": native}
                if nested
                else native
            )
            database.get(ComparisonSet, stack["id"]).registrations = {"slide-2": canonical}
            database.commit()
        member = next(
            member for member in client.get(url).json()["members"] if member["slideId"] == "slide-2"
        )
        if change == "unchanged":
            assert member.get("nativeOverviewFallback") == native
        else:
            assert member.get("nativeOverviewFallback") is None


@pytest.mark.parametrize(
    "change",
    [
        "current",
        "missing-applied",
        "wrong-digest",
        "native-missing-applied",
        "native-wrong-digest",
        "changed-descriptor",
    ],
)
def test_original_frame_proof_allows_different_bounded_sampling_but_rejects_missing_application(
    tmp_path, change, monkeypatch
):
    from wsi_viewer.alignment_geometry import (
        derivative_sampling_geometry,
        original_frame_registration,
    )
    from wsi_viewer.storage import StorageLayout

    with _client(tmp_path, enabled=True) as client:
        headers = _headers(client)
        stack, url = _stack(client, headers)
        candidate_id, registration, _ = _bound_candidate(client, stack)
        layout = StorageLayout(client.app.state.settings.data_root)
        with session_factory(client.app.state.settings)() as database:
            for name in ("slide-1", "slide-2"):
                slide = database.get(Slide, name)
                slide.slide_metadata = {**slide.slide_metadata, "width": 5003, "height": 4009}
                derivative = layout.for_slide(name).private_derivative
                derivative.mkdir(parents=True, exist_ok=True)
                (derivative / "slide.dzi").write_text(
                    '<Image TileSize="256" Overlap="0" Format="jpg">'
                    '<Size Width="5003" Height="4009"/></Image>'
                )
            source, anchor = database.get(Slide, "slide-2"), database.get(Slide, "slide-1")
            registration = {
                **registration,
                "sourceFrameVersion": metadata_frame_digest(source.slide_metadata),
                "anchorFrameVersion": metadata_frame_digest(anchor.slide_metadata),
            }
            native_settings, candidate_settings = {}, {}
            for side, name in (("reference", "slide-1"), ("moving", "slide-2")):
                path = layout.for_slide(name).private_derivative
                native_settings[f"{side}Geometry"] = derivative_sampling_geometry(
                    path, (5003, 4009), maximum=1024
                )
                candidate_settings[f"{side}Geometry"] = derivative_sampling_geometry(
                    path, (5003, 4009), maximum=4096
                )
            native = original_frame_registration(_native(registration), native_settings)
            native["settingsDigest"] = settings_digest(ENGINE_NATIVE_OVERVIEW, native_settings)
            candidate = original_frame_registration(registration, candidate_settings)
            candidate["settingsDigest"] = settings_digest(
                ENGINE_NATIVE_OVERVIEW, candidate_settings
            )
            if change == "missing-applied":
                candidate.pop("samplingGeometryApplied")
            elif change == "wrong-digest":
                candidate["samplingGeometryDigest"] = "0" * 64
            elif change == "native-missing-applied":
                native.pop("samplingGeometryApplied")
            elif change == "native-wrong-digest":
                native["samplingGeometryDigest"] = "0" * 64
            row = database.get(ComparisonRegistrationCandidate, candidate_id)
            row.registration, row.settings_digest = candidate, candidate["settingsDigest"]
            database.get(ComparisonSet, stack["id"]).registrations = {"slide-2": native}
            database.commit()
        if change == "changed-descriptor":
            (layout.for_slide("slide-2").private_derivative / "slide.dzi").write_text(
                '<Image TileSize="256" Overlap="0" Format="jpg">'
                '<Size Width="5004" Height="4009"/></Image>'
            )
        import json
        import time

        import wsi_viewer.alignment_routes as routes

        reader = routes.derivative_sampling_geometry
        reads = []

        def count_read(*args, **kwargs):
            reads.append(kwargs.get("maximum"))
            return reader(*args, **kwargs)

        monkeypatch.setattr(routes, "derivative_sampling_geometry", count_read)
        started = time.perf_counter()
        candidate = _manifest(client, url)
        assert candidate["currentPair"] is (
            change not in {"missing-applied", "wrong-digest", "changed-descriptor"}
        )
        candidate_reads = len(reads)
        candidate_seconds = time.perf_counter() - started
        reads.clear()
        started = time.perf_counter()
        member = next(
            member for member in client.get(url).json()["members"] if member["slideId"] == "slide-2"
        )
        canonical_seconds = time.perf_counter() - started
        assert candidate_reads <= 4 and len(reads) <= 4
        if change == "current":
            receipt = {
                "scope": "disposable-endpoint-DZI-descriptor-reads",
                "candidateFrameReads": candidate_reads,
                "canonicalFrameReads": len(reads),
                "candidateGetSeconds": candidate_seconds,
                "canonicalGetSeconds": canonical_seconds,
            }
            (tmp_path / "frame-read-receipt.json").write_text(json.dumps(receipt))
            print(json.dumps(receipt))
        if change in {"native-missing-applied", "native-wrong-digest", "changed-descriptor"}:
            assert member["nativeOverviewFallback"] is None
        else:
            assert member["nativeOverviewFallback"] == native
        if change == "current":
            assert candidate["registration"]["engineSettings"]["movingGeometry"][
                "analysisSize"
            ] == [2502, 2005]
            assert member["nativeOverviewFallback"]["engineSettings"]["movingGeometry"][
                "analysisSize"
            ] == [626, 502]
            assert member["nativeOverviewFallback"]["engineSettings"]["movingGeometry"][
                "coordinateFrameSize"
            ] == [5008, 4016]


def test_real_parent_change_invalidates_candidate_without_mutating_its_receipt(tmp_path):
    with _client(tmp_path, enabled=True) as client:
        headers = _headers(client)
        stack, url = _stack(client, headers)
        candidate_id, original, _ = _bound_candidate(client, stack)
        changed = client.patch(
            url,
            headers=headers,
            json={"version": stack["version"], "anchors": {"slide-2": "slide-3"}},
        )
        assert changed.status_code == 200, changed.text[:300]
        assert _manifest(client, url)["currentPair"] is False
        with session_factory(client.app.state.settings)() as database:
            assert (
                database.get(ComparisonRegistrationCandidate, candidate_id).registration == original
            )


def test_shared_live_tokens_and_native_projection_keep_private_paths_hidden(tmp_path):
    from wsi_viewer.models import LibraryShare, ShareSlide

    with _client(tmp_path, enabled=True) as client:
        headers = _headers(client)
        stack, url = _stack(client, headers)
        _, registration, _ = _bound_candidate(client, stack)
        native = _native(registration)
        settings = {"resourcePath": "C:/private-resource/model.bin", "resourceSha256": "e" * 64}
        native.update(
            engineSettings=settings,
            settingsDigest=settings_digest(ENGINE_NATIVE_OVERVIEW, settings),
        )
        with session_factory(client.app.state.settings)() as database:
            database.get(ComparisonSet, stack["id"]).registrations = {"slide-2": native}
            source = database.get(Slide, "slide-2")
            source.slide_metadata = {
                **source.slide_metadata,
                "sourcePath": "C:/private-source/input.ome.tif",
            }
            share = LibraryShare(
                public_id="binding-share",
                target_type="collection",
                target_id="collection",
                privacy_status="passed",
            )
            database.add(share)
            database.flush()
            database.add_all(
                [
                    ShareSlide(share_id=share.id, slide_id=name, sort_order=index)
                    for index, name in enumerate(("slide-1", "slide-2", "slide-3"))
                ]
            )
            database.commit()
        shared = client.get(f"/api/v2/public/collections/binding-share/comparisons/{stack['id']}")
        assert shared.status_code == 200, shared.text[:300]
        assert "private-resource" not in shared.text and "private-source" not in shared.text
        member = next(
            member for member in shared.json()["members"] if member["slideId"] == "slide-2"
        )
        assert member["alignmentSourceVersion"] == _manifest(client, url)["sourceSnapshotVersion"]
        assert member["nativeOverviewFallback"]["engineSettings"] == {"resourceSha256": "e" * 64}


@pytest.mark.parametrize(
    "change",
    [
        "current",
        "wrong-source",
        "wrong-frame",
        "wrong-anchor",
        "missing-frame",
        "missing-preparation",
    ],
)
def test_candidate_embedded_fallback_is_independently_bound_before_public_projection(
    tmp_path, change
):
    with _client(tmp_path, enabled=True) as client:
        headers = _headers(client)
        stack, url = _stack(client, headers)
        candidate_id, original, _ = _bound_candidate(client, stack)
        fallback = _native(original)
        if change == "wrong-source":
            fallback["sourceVersion"] = "old-source-pixels"
        elif change == "wrong-frame":
            fallback["sourceFrameVersion"] = "obsolete-frame"
        elif change == "wrong-anchor":
            fallback["anchorSlideId"] = "slide-3"
        elif change == "missing-frame":
            fallback.pop("anchorFrameVersion")
        elif change == "missing-preparation":
            fallback["evidence"] = {}
        with session_factory(client.app.state.settings)() as database:
            row = database.get(ComparisonRegistrationCandidate, candidate_id)
            stored = {**row.registration, "overviewFallback": fallback}
            row.registration = stored
            database.commit()
        candidate = _manifest(client, url)
        assert candidate["currentPair"] is True
        if change == "current":
            assert candidate["registration"]["overviewFallback"] == fallback
        else:
            assert "overviewFallback" not in candidate["registration"]
        with session_factory(client.app.state.settings)() as database:
            assert (
                database.get(ComparisonRegistrationCandidate, candidate_id).registration == stored
            )
