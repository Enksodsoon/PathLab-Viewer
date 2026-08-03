from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from test_annotations import _client, _login, _slide


def _desktop_authorization(client) -> dict[str, str]:
    csrf = _login(client)
    pairing = client.post(
        "/api/v1/desktop/pairings", json={"deviceName": "Forge morphology"}
    ).json()
    assert (
        client.post(
            "/api/v1/desktop/pairings/approve", headers=csrf, json={"userCode": pairing["userCode"]}
        ).status_code
        == 204
    )
    exchanged = client.post(
        "/api/v1/desktop/pairings/exchange",
        json={"deviceCode": pairing["deviceCode"], "deviceSecret": pairing["deviceSecret"]},
    )
    assert exchanged.status_code == 200
    assert "slides:evidence:write" in exchanged.json()["scopes"]
    return {"Authorization": f"Bearer {exchanged.json()['accessToken']}"}


def _signed_morphology_manifest() -> dict:
    value = {
        "ai_lab_schema": "pathlab-ai-result/v2",
        "job_id": "job-1",
        "adapter": "morphology",
        "research_only": True,
        "not_diagnostic": True,
        "review_required": True,
        "official_score_impact": False,
        "contains_diagnosis": False,
        "source_fingerprint_sha256": "a" * 64,
        "artifact": {"sha256": "b" * 64},
        "model": {"config_sha256": "c" * 64},
        "code": {"revision": "test"},
    }
    private_key = Ed25519PrivateKey.generate()
    public_der = private_key.public_key().public_bytes(
        serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo
    )
    message = "\n".join(
        ("pathlab-ai-result/v2", "job-1", "morphology", "a" * 64, "b" * 64, "c" * 64, "test")
    ).encode()
    value["signature"] = {
        "algorithm": "Ed25519",
        "key_id": hashlib.sha256(public_der).hexdigest(),
        "public_key_der": base64.urlsafe_b64encode(public_der).decode().rstrip("="),
        "value": base64.urlsafe_b64encode(private_key.sign(message)).decode().rstrip("="),
    }
    return value


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


def test_paired_forge_submits_signed_temporary_morphology_evidence(tmp_path: Path) -> None:
    with _client(tmp_path, enabled=True) as client:
        authorization = _desktop_authorization(client)
        slide = _slide(client, slide_id="desktop-evidence")
        payload = _payload()
        payload.update(
            {"adapter": "morphology", "modelId": "dino-baseline", "containsDiagnosis": False}
        )
        region = payload["regions"][0]
        region.pop("probability")
        region.pop("uncertainty")
        region.update(
            {
                "evidenceKind": "similar",
                "similarity": 0.88,
                "rank": 1,
                "crossStain": False,
                "morphologyTags": ["architecture"],
            }
        )
        manifest = _signed_morphology_manifest()
        payload["resultManifest"] = manifest
        payload["resultManifestSha256"] = hashlib.sha256(
            json.dumps(manifest, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
        ).hexdigest()
        created = client.post(
            f"/api/v1/desktop/slides/{slide.id}/ai-candidates", headers=authorization, json=payload
        )
        assert created.status_code == 201
        assert created.json()["temporary"] is True
        tampered = dict(payload)
        tampered["resultManifest"] = {**manifest, "contains_diagnosis": True}
        rejected = client.post(
            f"/api/v1/desktop/slides/{slide.id}/ai-candidates", headers=authorization, json=tampered
        )
        assert rejected.status_code == 422
