from __future__ import annotations

import json
import re
import sys
from datetime import date
from pathlib import Path
from typing import Any

DEFAULT_REGISTRY = Path("docs/evidence/capability-registry.json")
EVIDENCE_STATES = (
    "NOT_IMPLEMENTED",
    "BUILT",
    "SYNTHETICALLY_VERIFIED",
    "EXTERNALLY_CONFORMANT",
    "PILOT_VALIDATED",
    "PRODUCTION_CERTIFIED",
    "CLINICALLY_QUALIFIED",
)


def _string_list(value: object, name: str) -> list[str]:
    if not isinstance(value, list) or not value or not all(
        isinstance(item, str) and item.strip() for item in value
    ):
        raise ValueError(f"{name} must be a non-empty string list")
    return value


def _repository_path(value: str) -> None:
    path = Path(value)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError(f"repository path must be relative: {value}")
    if not path.is_file():
        raise ValueError(f"repository path does not exist: {value}")


def validate_registry(path: Path) -> int:
    loaded: Any = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise ValueError("registry must be an object")
    registry: dict[str, Any] = loaded
    if registry.get("schemaVersion") != 1:
        raise ValueError("schemaVersion must be 1")
    baseline_sha = registry.get("baselineReleaseSha")
    if not isinstance(baseline_sha, str) or re.fullmatch(r"[0-9a-f]{40}", baseline_sha) is None:
        raise ValueError("baselineReleaseSha must be a lowercase 40-character Git SHA")
    generated_at = registry.get("generatedAt")
    if not isinstance(generated_at, str):
        raise ValueError("generatedAt must be an ISO date")
    date.fromisoformat(generated_at)
    if registry.get("evidenceStates") != list(EVIDENCE_STATES):
        raise ValueError("evidenceStates must match the ordered evidence contract")
    capabilities = registry["capabilities"]
    if not isinstance(capabilities, list) or not capabilities:
        raise ValueError("capabilities must be a non-empty list")
    identifiers: set[str] = set()
    for capability in capabilities:
        if not isinstance(capability, dict):
            raise ValueError("capability entries must be objects")
        identifier = capability.get("id")
        if not isinstance(identifier, str) or re.fullmatch(
            r"[a-z0-9]+(?:-[a-z0-9]+)*", identifier
        ) is None:
            raise ValueError("capability id must use lowercase kebab-case")
        if identifier in identifiers:
            raise ValueError(f"duplicate capability id: {identifier}")
        identifiers.add(identifier)
        state = capability.get("evidenceState")
        if state not in EVIDENCE_STATES:
            raise ValueError(f"unknown evidence state: {state}")
        release_sha = capability.get("releaseSha")
        if (
            not isinstance(release_sha, str)
            or re.fullmatch(r"[0-9a-f]{40}", release_sha) is None
        ):
            raise ValueError(f"{identifier}.releaseSha must be a lowercase 40-character SHA")
        for field in ("displayName", "domain"):
            value = capability.get(field)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{identifier}.{field} must be a non-empty string")
        feature_flag = capability.get("featureFlag")
        if feature_flag is not None and (
            not isinstance(feature_flag, str)
            or re.fullmatch(r"PATHLAB_[A-Z0-9_]+", feature_flag) is None
        ):
            raise ValueError(f"{identifier}.featureFlag must be null or a PATHLAB_ variable")
        for field in ("supportingEvidence", "requiredTests"):
            for repository_path in _string_list(capability.get(field), f"{identifier}.{field}"):
                _repository_path(repository_path)
        _string_list(capability.get("claimRestrictions"), f"{identifier}.claimRestrictions")
    print(f"Capability registry valid: {len(capabilities)} entries")
    return len(capabilities)


def main() -> int:
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_REGISTRY
    try:
        validate_registry(path)
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as error:
        print(f"Capability registry invalid: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
