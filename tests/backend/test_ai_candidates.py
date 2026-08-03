from __future__ import annotations

from pathlib import Path

from test_annotations import _client, _login, _slide


def _payload() -> dict:
    return {
        "sourceFingerprintSha256": "a" * 64,
        "resultManifestSha256": "b" * 64,
        "adapter": "wsinfer",
        "modelId": "breast-research-baseline",
        "researchOnly": True,
        "notDiagnostic": True,
        "reviewRequired": True,
        "regions": [
            {
                "id": "26c64cce-9bc4-4eba-9d7c-82ef4c34f38b",
                "geometry": {
                    "type": "rectangle",
                    "x": 10.0,
                    "y": 20.0,
                    "width": 100.0,
                    "height": 80.0,
                },
                "probability": 0.72,
                "uncertainty": 0.28,
                "metadata": {
                    "title": "Evidence region",
                    "classification": "model evidence",
                    "tags": ["research-only"],
                    "notes": "Not a confirmed lesion.",
                },
            }
        ],
    }


def test_ai_candidate_is_private_temporary_and_discardable(tmp_path: Path) -> None:
    with _client(tmp_path, enabled=True) as client:
        headers = _login(client)
        slide = _slide(client)
        created = client.post(
            f"/api/v2/admin/ai-candidates/slides/{slide.id}",
            headers=headers,
            json=_payload(),
        )
        assert created.status_code == 201
        value = created.json()
        assert value["temporary"] is True
        assert value["notDiagnostic"] is True
        assert value["regions"][0]["metadata"]["notes"] == "Not a confirmed lesion."
        route = f"/api/v2/admin/ai-candidates/slides/{slide.id}/{value['id']}"
        assert client.get(route).status_code == 200
        assert client.delete(route, headers=headers).status_code == 204
        assert client.get(route).status_code == 404


def test_ai_candidate_rejects_out_of_bounds_region(tmp_path: Path) -> None:
    with _client(tmp_path, enabled=True) as client:
        headers = _login(client)
        slide = _slide(client)
        payload = _payload()
        payload["regions"][0]["geometry"]["x"] = 1_001.0
        response = client.post(
            f"/api/v2/admin/ai-candidates/slides/{slide.id}",
            headers=headers,
            json=payload,
        )
        assert response.status_code == 422
        assert response.json()["detail"]["code"] == "AI_CANDIDATE_COORDINATES_INVALID"


def test_morphology_candidate_preserves_source_coordinates_and_review_evidence(
    tmp_path: Path,
) -> None:
    with _client(tmp_path, enabled=True) as client:
        headers = _login(client)
        slide = _slide(client)
        payload = _payload()
        payload["adapter"] = "morphology"
        payload["modelId"] = "kaiko-pinned"
        payload["containsDiagnosis"] = False
        region = payload["regions"][0]
        region.pop("probability")
        region.pop("uncertainty")
        region.update(
            {
                "evidenceKind": "similar",
                "similarity": 0.91,
                "rank": 1,
                "crossStain": False,
                "morphologyTags": ["glandular-architecture"],
            }
        )
        created = client.post(
            f"/api/v2/admin/ai-candidates/slides/{slide.id}",
            headers=headers,
            json=payload,
        )
        assert created.status_code == 201
        value = created.json()
        assert value["regions"][0]["geometry"] == region["geometry"]
        assert value["regions"][0]["evidenceKind"] == "similar"
        assert value["regions"][0]["rank"] == 1
        assert value["containsDiagnosis"] is False


def test_morphology_candidate_rejects_missing_rank_or_more_than_five(tmp_path: Path) -> None:
    with _client(tmp_path, enabled=True) as client:
        headers = _login(client)
        slide = _slide(client)
        payload = _payload()
        payload["adapter"] = "morphology"
        payload["regions"][0].update({"evidenceKind": "contrast", "similarity": 0.4})
        response = client.post(
            f"/api/v2/admin/ai-candidates/slides/{slide.id}",
            headers=headers,
            json=payload,
        )
        assert response.status_code == 422
        payload["regions"] = [payload["regions"][0] | {"rank": index + 1} for index in range(6)]
        response = client.post(
            f"/api/v2/admin/ai-candidates/slides/{slide.id}",
            headers=headers,
            json=payload,
        )
        assert response.status_code == 422
