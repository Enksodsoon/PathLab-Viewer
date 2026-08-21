import base64
import hashlib
import json
import math
import re
from typing import Any, NoReturn

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from .study_pack_contract import canonical_json

SCHEMA = "pathlab.ai-evidence/1"
MAX_EVIDENCE_BYTES = 2 * 1024 * 1024
SHA256 = re.compile(r"[a-f0-9]{64}")
IDENTIFIER = re.compile(r"[A-Za-z0-9._-]{1,160}")
TERMINAL_STATUSES = {"completed", "partial", "abstained", "unsupported", "failed"}
MARKERS = {"generic", "er", "pr", "ki-67", "her2", "pd-l1"}
PROHIBITED_KEYS = {
    "embedding",
    "embeddings",
    "rawPixels",
    "diagnosis",
    "clinicalScore",
    "tps",
    "cps",
    "ascoCap",
    "treatment",
}


def parse_evidence(raw: bytes) -> dict[str, Any]:
    if not raw or len(raw) > MAX_EVIDENCE_BYTES:
        raise ValueError("AI_EVIDENCE_SIZE_INVALID")

    def unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("AI_EVIDENCE_DUPLICATE_FIELD")
            result[key] = value
        return result

    def reject_constant(_: str) -> NoReturn:
        raise ValueError("AI_EVIDENCE_NUMBER_INVALID")

    value: Any = json.loads(raw, object_pairs_hook=unique_object, parse_constant=reject_constant)
    if not isinstance(value, dict):
        raise ValueError("AI_EVIDENCE_OBJECT_REQUIRED")
    return value


def validate_evidence(value: dict[str, Any], *, slide_sha256: str, slide_revision: str) -> str:
    _exact_keys(
        value,
        {
            "schema",
            "bundleId",
            "source",
            "pack",
            "status",
            "researchOnly",
            "notDiagnostic",
            "reviewRequired",
            "coordinates",
            "evidence",
            "cellAggregates",
            "ihcDescriptors",
            "citations",
            "qc",
            "provenance",
            "manifestSha256",
            "signature",
        },
    )
    _reject_prohibited(value)
    if value.get("schema") != SCHEMA:
        raise ValueError("AI_EVIDENCE_SCHEMA_UNSUPPORTED")
    _identifier(value.get("bundleId"), maximum=120)
    source = _object(value, "source", {"slideSha256", "revision"})
    if source.get("slideSha256") != slide_sha256 or source.get("revision") != slide_revision:
        raise ValueError("AI_EVIDENCE_SLIDE_IDENTITY_MISMATCH")
    pack = _object(
        value,
        "pack",
        {
            "id",
            "version",
            "manifestSha256",
            "preprocessing",
            "artifacts",
            "allowedUse",
            "validationStatus",
        },
    )
    _identifier(pack.get("id"), maximum=120)
    _text(pack.get("version"), maximum=64)
    _sha(pack.get("manifestSha256"))
    _text(pack.get("preprocessing"), maximum=120)
    artifacts = pack.get("artifacts")
    if not isinstance(artifacts, list) or len(artifacts) > 16:
        raise ValueError("AI_EVIDENCE_PACK_INVALID")
    for artifact in artifacts:
        _sha(artifact)
    if pack.get("allowedUse") != "private-research":
        raise ValueError("AI_EVIDENCE_RIGHTS_BLOCKED")
    if pack.get("validationStatus") not in {"experimental", "qualified"}:
        raise ValueError("AI_EVIDENCE_PACK_BLOCKED")
    if value.get("status") not in TERMINAL_STATUSES:
        raise ValueError("AI_EVIDENCE_STATUS_INVALID")
    if value.get("researchOnly") is not True or value.get("notDiagnostic") is not True:
        raise ValueError("AI_EVIDENCE_RESEARCH_BOUNDARY_REQUIRED")
    if value.get("reviewRequired") is not True:
        raise ValueError("AI_EVIDENCE_REVIEW_REQUIRED")
    _coordinates(value.get("coordinates"))
    region_ids = _regions(value.get("evidence"))
    _cell_aggregates(value.get("cellAggregates"), region_ids)
    _ihc_descriptors(value.get("ihcDescriptors"), region_ids)
    _citations(value.get("citations"))
    _qc(value.get("qc"))
    provenance = _object(value, "provenance", {"createdAt", "codeRevision", "offlineAnalysis"})
    _text(provenance.get("createdAt"), maximum=40)
    _text(provenance.get("codeRevision"), maximum=160)
    if provenance.get("offlineAnalysis") is not True:
        raise ValueError("AI_EVIDENCE_OFFLINE_REQUIRED")
    supplied_hash = value.get("manifestSha256")
    _sha(supplied_hash)
    unsigned = {
        key: item for key, item in value.items() if key not in {"manifestSha256", "signature"}
    }
    calculated = hashlib.sha256(canonical_json(unsigned).encode("utf-8")).hexdigest()
    if supplied_hash != calculated:
        raise ValueError("AI_EVIDENCE_MANIFEST_HASH_MISMATCH")
    _verify_signature(value.get("signature"), supplied_hash)
    return calculated


def _coordinates(value: Any) -> None:
    if not isinstance(value, dict):
        raise ValueError("AI_EVIDENCE_COORDINATES_INVALID")
    _exact_keys(value, {"space", "originX", "originY", "scaleX", "scaleY"})
    if value.get("space") != "source-pixel":
        raise ValueError("AI_EVIDENCE_COORDINATES_INVALID")
    for key in ("originX", "originY"):
        _number(value.get(key), minimum=0)
    for key in ("scaleX", "scaleY"):
        _number(value.get(key), minimum=0, positive=True)


def _regions(value: Any) -> set[str]:
    if not isinstance(value, list) or len(value) > 1000:
        raise ValueError("AI_EVIDENCE_REGIONS_INVALID")
    seen: set[str] = set()
    for region in value:
        allowed = {"id", "stage", "kind", "x", "y", "width", "height", "score", "thumbnail"}
        if (
            not isinstance(region, dict)
            or not set(region).issubset(allowed)
            or not allowed - {"thumbnail"} <= set(region)
        ):
            raise ValueError("AI_EVIDENCE_REGION_INVALID")
        region_id = _identifier(region.get("id"), maximum=120)
        if region_id in seen:
            raise ValueError("AI_EVIDENCE_REGION_INVALID")
        seen.add(region_id)
        if region.get("stage") not in {"coarse", "refined"} or region.get("kind") not in {
            "support",
            "similar",
            "contrast",
        }:
            raise ValueError("AI_EVIDENCE_REGION_INVALID")
        for key in ("x", "y"):
            _number(region.get(key), minimum=0)
        for key in ("width", "height"):
            _number(region.get(key), minimum=0, positive=True)
        _number(region.get("score"), minimum=0, maximum=1)
        thumbnail = region.get("thumbnail")
        if thumbnail is not None and not re.fullmatch(
            r"thumbnails/[A-Za-z0-9._-]+\.(png|jpg|webp)", thumbnail
        ):
            raise ValueError("AI_EVIDENCE_THUMBNAIL_INVALID")
    return seen


def _cell_aggregates(value: Any, region_ids: set[str]) -> None:
    if not isinstance(value, list) or len(value) > 1000:
        raise ValueError("AI_EVIDENCE_CELL_AGGREGATES_INVALID")
    for item in value:
        required = {"regionId", "algorithm", "count", "densityPerMm2", "meanNucleusAreaPx2"}
        if not isinstance(item, dict) or set(item) != required:
            raise ValueError("AI_EVIDENCE_CELL_AGGREGATE_INVALID")
        if _identifier(item.get("regionId"), maximum=120) not in region_ids:
            raise ValueError("AI_EVIDENCE_REGION_REFERENCE_INVALID")
        if item.get("algorithm") not in {"hovernet-fast", "od-watershed"}:
            raise ValueError("AI_EVIDENCE_CELL_ALGORITHM_INVALID")
        if (
            isinstance(item.get("count"), bool)
            or not isinstance(item.get("count"), int)
            or item["count"] < 0
        ):
            raise ValueError("AI_EVIDENCE_CELL_COUNT_INVALID")
        for key in ("densityPerMm2", "meanNucleusAreaPx2"):
            if item.get(key) is not None:
                _number(item[key], minimum=0)


def _ihc_descriptors(value: Any, region_ids: set[str]) -> None:
    if not isinstance(value, list) or len(value) > 1000:
        raise ValueError("AI_EVIDENCE_IHC_INVALID")
    compartments = {"nuclear", "membrane", "tumor-immune-region", "generic-region"}
    for item in value:
        required = {
            "regionId",
            "marker",
            "compartment",
            "dabAreaFraction",
            "meanDabOd",
            "researchEstimate",
        }
        if not isinstance(item, dict) or set(item) != required:
            raise ValueError("AI_EVIDENCE_IHC_INVALID")
        if _identifier(item.get("regionId"), maximum=120) not in region_ids:
            raise ValueError("AI_EVIDENCE_REGION_REFERENCE_INVALID")
        if item.get("marker") not in MARKERS or item.get("compartment") not in compartments:
            raise ValueError("AI_EVIDENCE_IHC_INVALID")
        _number(item.get("dabAreaFraction"), minimum=0, maximum=1)
        _number(item.get("meanDabOd"), minimum=0)
        if item.get("researchEstimate") is not True:
            raise ValueError("AI_EVIDENCE_IHC_RESEARCH_BOUNDARY_REQUIRED")


def _citations(value: Any) -> None:
    if not isinstance(value, list) or len(value) > 100:
        raise ValueError("AI_EVIDENCE_CITATIONS_INVALID")
    for item in value:
        if not isinstance(item, dict) or set(item) != {"claimId", "sourceUrl"}:
            raise ValueError("AI_EVIDENCE_CITATION_INVALID")
        _identifier(item.get("claimId"), maximum=160)
        url = _text(item.get("sourceUrl"), maximum=1000)
        if not url.startswith("https://"):
            raise ValueError("AI_EVIDENCE_CITATION_INVALID")


def _qc(value: Any) -> None:
    if not isinstance(value, dict) or set(value) != {
        "focus",
        "tissueFraction",
        "uncertainty",
        "abstentionReasons",
    }:
        raise ValueError("AI_EVIDENCE_QC_INVALID")
    for key in ("focus", "tissueFraction", "uncertainty"):
        _number(value.get(key), minimum=0, maximum=1)
    reasons = value.get("abstentionReasons")
    if not isinstance(reasons, list) or len(reasons) > 20:
        raise ValueError("AI_EVIDENCE_QC_INVALID")
    for reason in reasons:
        _text(reason, maximum=500)


def _verify_signature(value: Any, manifest_hash: str) -> None:
    if not isinstance(value, dict) or set(value) != {"algorithm", "keyId", "publicKeyDer", "value"}:
        raise ValueError("AI_EVIDENCE_SIGNATURE_INVALID")
    if value.get("algorithm") != "Ed25519":
        raise ValueError("AI_EVIDENCE_SIGNATURE_INVALID")
    _sha(value.get("keyId"))
    try:
        public_bytes = _decode_urlsafe(value.get("publicKeyDer"))
        signature = _decode_urlsafe(value.get("value"))
        if hashlib.sha256(public_bytes).hexdigest() != value["keyId"]:
            raise ValueError("AI_EVIDENCE_SIGNER_IDENTITY_MISMATCH")
        key = serialization.load_der_public_key(public_bytes)
        if not isinstance(key, Ed25519PublicKey):
            raise ValueError("AI_EVIDENCE_SIGNATURE_INVALID")
        key.verify(signature, f"{SCHEMA}\n{manifest_hash}".encode())
    except ValueError:
        raise
    except Exception as error:
        raise ValueError("AI_EVIDENCE_SIGNATURE_INVALID") from error


def _decode_urlsafe(value: Any) -> bytes:
    text = _text(value, maximum=1000)
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def _object(root: dict[str, Any], name: str, keys: set[str]) -> dict[str, Any]:
    value = root.get(name)
    if not isinstance(value, dict):
        raise ValueError("AI_EVIDENCE_OBJECT_INVALID")
    _exact_keys(value, keys)
    return value


def _exact_keys(value: dict[str, Any], expected: set[str]) -> None:
    if set(value) != expected:
        raise ValueError("AI_EVIDENCE_FIELDS_INVALID")


def _identifier(value: Any, *, maximum: int) -> str:
    text = _text(value, maximum=maximum)
    if not IDENTIFIER.fullmatch(text):
        raise ValueError("AI_EVIDENCE_ID_INVALID")
    return text


def _text(value: Any, *, maximum: int) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise ValueError("AI_EVIDENCE_TEXT_INVALID")
    return value.strip()


def _sha(value: Any) -> str:
    if not isinstance(value, str) or not SHA256.fullmatch(value):
        raise ValueError("AI_EVIDENCE_SHA256_INVALID")
    return value


def _number(
    value: Any, *, minimum: float, maximum: float | None = None, positive: bool = False
) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("AI_EVIDENCE_NUMBER_INVALID")
    number = float(value)
    if not math.isfinite(number) or number < minimum or (positive and number <= minimum):
        raise ValueError("AI_EVIDENCE_NUMBER_INVALID")
    if maximum is not None and number > maximum:
        raise ValueError("AI_EVIDENCE_NUMBER_INVALID")
    return number


def _reject_prohibited(value: Any) -> None:
    if isinstance(value, dict):
        if PROHIBITED_KEYS.intersection(value):
            raise ValueError("AI_EVIDENCE_PROHIBITED_CLINICAL_OR_RAW_FIELD")
        for item in value.values():
            _reject_prohibited(item)
    elif isinstance(value, list):
        for item in value:
            _reject_prohibited(item)
