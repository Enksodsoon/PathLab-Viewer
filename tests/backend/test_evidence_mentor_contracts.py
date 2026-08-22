import base64
import hashlib
from copy import deepcopy
from datetime import UTC, datetime

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from wsi_viewer.evidence_contract import SCHEMA as EVIDENCE_SCHEMA
from wsi_viewer.evidence_contract import validate_evidence
from wsi_viewer.knowledge_pack_contract import retrieve_claims, validate_knowledge_pack
from wsi_viewer.study_pack_contract import canonical_json

_TRUSTED_SIGNERS: dict[str, bytes] = {}


def _signed_evidence(
    *, aggregate_region_id: str = "region-1", ihc_descriptor: dict[str, object] | None = None
) -> dict[str, object]:
    private = Ed25519PrivateKey.generate()
    public_bytes = private.public_key().public_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    value: dict[str, object] = {
        "schema": EVIDENCE_SCHEMA,
        "bundleId": "bundle-1",
        "source": {"slideSha256": "a" * 64, "revision": "slide-revision-1"},
        "pack": {
            "id": "cell-ihc-v1",
            "version": "1",
            "manifestSha256": "b" * 64,
            "preprocessing": "od-v1",
            "artifacts": [],
            "allowedUse": "private-research",
            "validationStatus": "experimental",
        },
        "status": "completed",
        "researchOnly": True,
        "notDiagnostic": True,
        "reviewRequired": True,
        "coordinates": {
            "space": "source-pixel",
            "originX": 0,
            "originY": 0,
            "scaleX": 1,
            "scaleY": 1,
        },
        "evidence": [
            {
                "id": "region-1",
                "stage": "refined",
                "kind": "support",
                "x": 10,
                "y": 20,
                "width": 200,
                "height": 100,
                "score": 0.8,
            }
        ],
        "cellAggregates": [
            {
                "regionId": aggregate_region_id,
                "algorithm": "od-watershed",
                "count": 42,
                "densityPerMm2": None,
                "meanNucleusAreaPx2": 35.2,
            }
        ],
        "ihcDescriptors": [
            ihc_descriptor
            or {
                "regionId": aggregate_region_id,
                "marker": "ki-67",
                "compartment": "nuclear",
                "dabAreaFraction": 0.21,
                "meanDabOd": 0.34,
                "researchEstimate": True,
            }
        ],
        "citations": [{"claimId": "nci.ki67.1", "sourceUrl": "https://www.cancer.gov/example"}],
        "qc": {"focus": 0.9, "tissueFraction": 0.7, "uncertainty": 0.2, "abstentionReasons": []},
        "provenance": {
            "createdAt": datetime.now(UTC).isoformat(),
            "codeRevision": "test",
            "offlineAnalysis": True,
        },
    }
    digest = hashlib.sha256(canonical_json(value).encode()).hexdigest()
    value["manifestSha256"] = digest
    value["signature"] = {
        "algorithm": "Ed25519",
        "keyId": hashlib.sha256(public_bytes).hexdigest(),
        "publicKeyDer": base64.urlsafe_b64encode(public_bytes).decode().rstrip("="),
        "value": base64.urlsafe_b64encode(private.sign(f"{EVIDENCE_SCHEMA}\n{digest}".encode()))
        .decode()
        .rstrip("="),
    }
    _TRUSTED_SIGNERS[hashlib.sha256(public_bytes).hexdigest()] = public_bytes
    return value


def test_evidence_signature_identity_and_slide_binding() -> None:
    value = _signed_evidence()
    assert (
        validate_evidence(value, slide_sha256="a" * 64, slide_revision="slide-revision-1",
                          trusted_signers=_TRUSTED_SIGNERS)
        == value["manifestSha256"]
    )
    with pytest.raises(ValueError, match="SLIDE_IDENTITY_MISMATCH"):
        validate_evidence(value, slide_sha256="c" * 64, slide_revision="slide-revision-1",
                          trusted_signers=_TRUSTED_SIGNERS)


def test_evidence_rejects_tamper_benchmark_rights_and_clinical_fields() -> None:
    value = _signed_evidence()
    tampered = deepcopy(value)
    tampered["qc"]["focus"] = 0.1  # type: ignore[index]
    with pytest.raises(ValueError, match="MANIFEST_HASH_MISMATCH"):
        validate_evidence(tampered, slide_sha256="a" * 64, slide_revision="slide-revision-1",
                          trusted_signers=_TRUSTED_SIGNERS)
    benchmark = deepcopy(value)
    benchmark["pack"]["allowedUse"] = "benchmark-only"  # type: ignore[index]
    with pytest.raises(ValueError, match="RIGHTS_BLOCKED"):
        validate_evidence(benchmark, slide_sha256="a" * 64, slide_revision="slide-revision-1",
                          trusted_signers=_TRUSTED_SIGNERS)
    clinical = deepcopy(value)
    clinical["clinicalScore"] = "positive"
    with pytest.raises(ValueError, match="FIELDS_INVALID|PROHIBITED"):
        validate_evidence(clinical, slide_sha256="a" * 64, slide_revision="slide-revision-1",
                          trusted_signers=_TRUSTED_SIGNERS)


def test_evidence_rejects_aggregates_outside_signed_regions() -> None:
    value = _signed_evidence(aggregate_region_id="missing-region")
    with pytest.raises(ValueError, match="REGION_REFERENCE_INVALID"):
        validate_evidence(value, slide_sha256="a" * 64, slide_revision="slide-revision-1",
                          trusted_signers=_TRUSTED_SIGNERS)


def test_pd_l1_compartment_requires_faculty_review_and_generic_fallback() -> None:
    base = {
        "regionId": "region-1",
        "markerId": "pd-l1",
        "marker": "pd-l1",
        "analysisMode": "marker-aware",
        "cellMaskSource": "od-watershed",
        "compartmentSource": "model-suggested",
        "calibrationStatus": "relative_only",
        "compartment": "tumor-immune-region",
        "dabAreaFraction": 0.21,
        "meanDabOd": 0.34,
        "uncertainty": 0.2,
        "abstentionReason": None,
        "researchEstimate": True,
    }
    with pytest.raises(ValueError, match="COMPARTMENT_REVIEW_REQUIRED"):
        value = _signed_evidence(ihc_descriptor=base)
        validate_evidence(value, slide_sha256="a" * 64, slide_revision="slide-revision-1",
                          trusted_signers=_TRUSTED_SIGNERS)

    fallback = {
        **base,
        "analysisMode": "generic-fallback",
        "compartment": "generic-region",
        "abstentionReason": "COMPARTMENT_REVIEW_REQUIRED",
    }
    value = _signed_evidence(ihc_descriptor=fallback)
    assert validate_evidence(
        value, slide_sha256="a" * 64, slide_revision="slide-revision-1",
        trusted_signers=_TRUSTED_SIGNERS,
    ) == value["manifestSha256"]


def test_knowledge_pack_retrieves_only_reviewed_atomic_claims() -> None:
    core: dict[str, object] = {
        "schema": "pathlab.knowledge-pack/1",
        "packId": "general-pathology-en",
        "version": "1",
        "language": "en",
        "claims": [
            {
                "id": "nci.ki67.1",
                "text": "Ki-67 is used as a marker of cell proliferation.",
                "retrievalText": "Ki-67 proliferation dividing cells nuclear marker",
                "source": {
                    "title": "NCI Dictionary",
                    "url": "https://www.cancer.gov/publications/dictionaries/cancer-terms/def/ki-67",
                    "revision": "2026-08-22",
                },
                "license": "US Government public-domain text; reuse reviewed",
                "allowedUse": "private-research-education",
                "reviewedAt": "2026-08-22T00:00:00Z",
                "tags": ["ihc", "proliferation", "ki-67"],
            }
        ],
    }
    core["checksum"] = hashlib.sha256(canonical_json(core).encode()).hexdigest()
    assert validate_knowledge_pack(core) == core["checksum"]
    claims = retrieve_claims(core, "What does the Ki-67 proliferation marker indicate?")
    assert [claim["id"] for claim in claims] == ["nci.ki67.1"]
    assert retrieve_claims(core, "unsupported unrelated question") == []
