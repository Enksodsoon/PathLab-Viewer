import base64
import hashlib
import re
from collections.abc import Mapping
from typing import Any

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from .study_pack_contract import canonical_json

SCHEMA = "pathlab.evidence-set/1"
SHA256 = re.compile(r"[a-f0-9]{64}")
IDENTIFIER = re.compile(r"[A-Za-z0-9._-]{1,160}")


def validate_evidence_set(
    value: dict[str, Any], *, slide_sha256: str, slide_revision: str,
    trusted_signers: Mapping[str, bytes], known_bundle_hashes: set[str],
) -> str:
    expected = {
        "schema", "setId", "source", "bundles", "fusion", "status", "researchOnly",
        "notDiagnostic", "reviewRequired", "createdAt", "manifestSha256", "signature",
    }
    if set(value) != expected or value.get("schema") != SCHEMA:
        raise ValueError("AI_EVIDENCE_SET_SCHEMA_INVALID")
    if not isinstance(value.get("setId"), str) or not IDENTIFIER.fullmatch(value["setId"]):
        raise ValueError("AI_EVIDENCE_SET_ID_INVALID")
    source = value.get("source")
    if not isinstance(source, dict) or set(source) != {"slideSha256", "revision"}:
        raise ValueError("AI_EVIDENCE_SET_SOURCE_INVALID")
    if source.get("slideSha256") != slide_sha256 or source.get("revision") != slide_revision:
        raise ValueError("AI_EVIDENCE_SET_SLIDE_IDENTITY_MISMATCH")
    bundles = value.get("bundles")
    if not isinstance(bundles, list) or not 1 <= len(bundles) <= 16:
        raise ValueError("AI_EVIDENCE_SET_BUNDLES_INVALID")
    seen: set[str] = set()
    for item in bundles:
        if not isinstance(item, dict) or set(item) != {"manifestSha256", "packId", "capability"}:
            raise ValueError("AI_EVIDENCE_SET_BUNDLES_INVALID")
        digest = item.get("manifestSha256")
        if not isinstance(digest, str) or not SHA256.fullmatch(digest):
            raise ValueError("AI_EVIDENCE_SET_BUNDLES_INVALID")
        if digest in seen or digest not in known_bundle_hashes:
            raise ValueError("AI_EVIDENCE_SET_BUNDLE_NOT_FOUND")
        seen.add(digest)
        for field in ("packId", "capability"):
            if not isinstance(item.get(field), str) or not IDENTIFIER.fullmatch(item[field]):
                raise ValueError("AI_EVIDENCE_SET_BUNDLES_INVALID")
    fusion = value.get("fusion")
    if not isinstance(fusion, dict) or set(fusion) != {
        "method", "coordinateBound", "qcBound", "provenanceBound", "uncertaintyBound",
        "serialSectionCellMatching",
    }:
        raise ValueError("AI_EVIDENCE_SET_FUSION_INVALID")
    if fusion != {
        "method": "evidence-coordinate-v1", "coordinateBound": True, "qcBound": True,
        "provenanceBound": True, "uncertaintyBound": True, "serialSectionCellMatching": False,
    }:
        raise ValueError("AI_EVIDENCE_SET_FUSION_INVALID")
    if value.get("status") not in {"completed", "partial", "abstained"}:
        raise ValueError("AI_EVIDENCE_SET_STATUS_INVALID")
    if value.get("researchOnly") is not True or value.get("notDiagnostic") is not True \
            or value.get("reviewRequired") is not True:
        raise ValueError("AI_EVIDENCE_SET_RESEARCH_BOUNDARY_REQUIRED")
    supplied = value.get("manifestSha256")
    if not isinstance(supplied, str) or not SHA256.fullmatch(supplied):
        raise ValueError("AI_EVIDENCE_SET_HASH_INVALID")
    unsigned = {
        key: item for key, item in value.items()
        if key not in {"manifestSha256", "signature"}
    }
    calculated = hashlib.sha256(canonical_json(unsigned).encode()).hexdigest()
    if supplied != calculated:
        raise ValueError("AI_EVIDENCE_SET_HASH_MISMATCH")
    signature = value.get("signature")
    if not isinstance(signature, dict) or set(signature) != {"algorithm", "keyId", "value"} \
            or signature.get("algorithm") != "Ed25519":
        raise ValueError("AI_EVIDENCE_SET_SIGNATURE_INVALID")
    key_id = signature.get("keyId")
    key_bytes = trusted_signers.get(key_id) if isinstance(key_id, str) else None
    if key_bytes is None or hashlib.sha256(key_bytes).hexdigest() != key_id:
        raise ValueError("AI_EVIDENCE_SET_SIGNER_NOT_TRUSTED")
    try:
        key = serialization.load_der_public_key(key_bytes)
        if not isinstance(key, Ed25519PublicKey):
            raise ValueError("AI_EVIDENCE_SET_SIGNATURE_INVALID")
        encoded = str(signature.get("value"))
        key.verify(base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4)),
                   f"{SCHEMA}\n{supplied}".encode())
    except ValueError:
        raise
    except Exception as error:
        raise ValueError("AI_EVIDENCE_SET_SIGNATURE_INVALID") from error
    return calculated
