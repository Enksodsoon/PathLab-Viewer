from __future__ import annotations

from typing import Any

from .assessment_contract import AssessmentContractError
from .assessment_contract_v2 import compile_assessment_v2, flatten_v2_items


def _issue(code: str, path: str, message: str, *, level: str = "error") -> dict[str, str]:
    return {"code": code, "path": path, "message": message, "level": level}


def preflight_v2(document: dict[str, Any]) -> dict[str, Any]:
    errors: list[dict[str, str]] = []
    warnings: list[dict[str, str]] = []
    sections = document.get("sections") if isinstance(document.get("sections"), list) else []
    items = flatten_v2_items(document)
    for section_index, section in enumerate(sections):
        section_items = section.get("items", []) if isinstance(section, dict) else []
        if len(section_items) > 25:
            warnings.append(
                _issue(
                    "ASSESSMENT_SECTION_LONG",
                    f"/sections/{section_index}",
                    "This section has more than 25 questions.",
                    level="warning",
                )
            )
        for item_index, item in enumerate(section_items):
            path = f"/sections/{section_index}/items/{item_index}"
            if not isinstance(item, dict):
                continue
            options = item.get("options", [])
            if item.get("type") in {"multiple-choice", "checkboxes", "dropdown"}:
                normalized = [
                    " ".join(str(option.get("label", "")).split()).casefold()
                    for option in options
                    if isinstance(option, dict)
                ]
                if len(normalized) != len(set(normalized)):
                    warnings.append(
                        _issue(
                            "ASSESSMENT_DUPLICATE_OPTION_LABEL",
                            f"{path}/options",
                            "Option labels should be unique.",
                            level="warning",
                        )
                    )
            if (
                item.get("type") == "diagnostic-field"
                and len(str(item.get("prompt", ""))) > 200
                and not str(item.get("helpText", "")).strip()
            ):
                warnings.append(
                    _issue(
                        "ASSESSMENT_DIAGNOSTIC_HELP_RECOMMENDED",
                        f"{path}/helpText",
                        "Long diagnostic prompts should include help text.",
                        level="warning",
                    )
                )
    try:
        compiled = compile_assessment_v2(document)
    except AssessmentContractError as error:
        errors.append(_issue(str(error), "/", "The assessment contract is not publishable."))
        compiled = None
    manual_items = [
        item for item in items if item.get("manual") is True or item.get("type") == "paragraph"
    ]
    release = document.get("release", {})
    effective_release = "immediate" if release.get("timing") == "immediate" else "manual"
    if manual_items and effective_release == "immediate":
        effective_release = "manual"
        warnings.append(
            _issue(
                "ASSESSMENT_MANUAL_RELEASE_REQUIRED",
                "/release/timing",
                "Immediate release was changed to manual because grading is required.",
                level="warning",
            )
        )
    return {
        "valid": not errors,
        "errors": errors,
        "warnings": warnings,
        "metrics": {
            "sections": len(sections),
            "items": len(items),
            "points": str(
                sum(
                    float(item.get("points", 0) or 0)
                    for item in items
                    if item.get("type") != "section-information"
                )
            ),
            "manualItems": len(manual_items),
            "encodedBytes": len(repr(compiled.definition).encode()) if compiled else None,
        },
        "effectiveRelease": effective_release,
    }
