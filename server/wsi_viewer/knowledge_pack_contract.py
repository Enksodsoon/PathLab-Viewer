import hashlib
import re
from typing import Any
from urllib.parse import urlparse

from .study_pack_contract import canonical_json, parse_json

SCHEMA = "pathlab.knowledge-pack/1"
MAX_KNOWLEDGE_BYTES = 2 * 1024 * 1024
ALLOWED_HOSTS = {"cancer.gov", "www.cancer.gov", "ncbi.nlm.nih.gov", "www.ncbi.nlm.nih.gov"}


def parse_knowledge_pack(raw: bytes) -> dict[str, Any]:
    if not raw or len(raw) > MAX_KNOWLEDGE_BYTES:
        raise ValueError("KNOWLEDGE_PACK_SIZE_INVALID")
    return parse_json(raw)


def validate_knowledge_pack(value: dict[str, Any]) -> str:
    if set(value) != {"schema", "packId", "version", "language", "claims", "checksum"}:
        raise ValueError("KNOWLEDGE_PACK_FIELDS_INVALID")
    if value.get("schema") != SCHEMA or value.get("language") != "en":
        raise ValueError("KNOWLEDGE_PACK_SCHEMA_UNSUPPORTED")
    _identifier(value.get("packId"), 120)
    _text(value.get("version"), 64)
    claims = value.get("claims")
    if not isinstance(claims, list) or not 1 <= len(claims) <= 10_000:
        raise ValueError("KNOWLEDGE_PACK_CLAIMS_INVALID")
    seen: set[str] = set()
    for claim in claims:
        if not isinstance(claim, dict) or set(claim) != {
            "id",
            "text",
            "retrievalText",
            "source",
            "license",
            "allowedUse",
            "reviewedAt",
            "tags",
        }:
            raise ValueError("KNOWLEDGE_PACK_CLAIM_INVALID")
        claim_id = _identifier(claim.get("id"), 160)
        if claim_id in seen:
            raise ValueError("KNOWLEDGE_PACK_CLAIM_DUPLICATED")
        seen.add(claim_id)
        _text(claim.get("text"), 1000)
        _text(claim.get("retrievalText"), 4000)
        source = claim.get("source")
        if not isinstance(source, dict) or set(source) != {"title", "url", "revision"}:
            raise ValueError("KNOWLEDGE_PACK_SOURCE_INVALID")
        _text(source.get("title"), 500)
        url = _text(source.get("url"), 1000)
        parsed = urlparse(url)
        if parsed.scheme != "https" or parsed.hostname not in ALLOWED_HOSTS:
            raise ValueError("KNOWLEDGE_PACK_SOURCE_NOT_ALLOWLISTED")
        _text(source.get("revision"), 160)
        license_name = _text(claim.get("license"), 200)
        if license_name.casefold() in {"unknown", "unspecified", "free online"}:
            raise ValueError("KNOWLEDGE_PACK_LICENSE_UNVERIFIED")
        if claim.get("allowedUse") != "private-research-education":
            raise ValueError("KNOWLEDGE_PACK_RIGHTS_BLOCKED")
        _text(claim.get("reviewedAt"), 40)
        tags = claim.get("tags")
        if not isinstance(tags, list) or len(tags) > 32 or len(set(tags)) != len(tags):
            raise ValueError("KNOWLEDGE_PACK_TAGS_INVALID")
        for tag in tags:
            _text(tag, 80)
    core = {key: item for key, item in value.items() if key != "checksum"}
    checksum = hashlib.sha256(canonical_json(core).encode()).hexdigest()
    if value.get("checksum") != checksum:
        raise ValueError("KNOWLEDGE_PACK_CHECKSUM_INVALID")
    return checksum


def retrieve_claims(
    value: dict[str, Any], question: str, *, limit: int = 5
) -> list[dict[str, Any]]:
    tokens = _tokens(question)
    if not tokens:
        return []
    scored: list[tuple[int, str, dict[str, Any]]] = []
    for claim in value["claims"]:
        haystack = _tokens(" ".join([claim["retrievalText"], claim["text"], *claim["tags"]]))
        score = len(tokens.intersection(haystack))
        if score:
            scored.append((score, claim["id"], claim))
    scored.sort(key=lambda item: (-item[0], item[1]))
    return [item[2] for item in scored[: max(1, min(limit, 5))]]


def _tokens(value: str) -> set[str]:
    return {item for item in re.findall(r"[a-z0-9]+", value.casefold()) if len(item) >= 3}


def _identifier(value: Any, maximum: int) -> str:
    text = _text(value, maximum)
    if not re.fullmatch(r"[A-Za-z0-9._-]+", text):
        raise ValueError("KNOWLEDGE_PACK_ID_INVALID")
    return text


def _text(value: Any, maximum: int) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise ValueError("KNOWLEDGE_PACK_TEXT_INVALID")
    return value.strip()
