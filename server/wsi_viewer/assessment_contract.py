import hashlib
import json
import math
import unicodedata
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

SCHEMA = "pathlab.assessment/1"
MAX_DEFINITION_BYTES = 4 * 1024 * 1024
MAX_ITEMS = 100
MAX_SLIDES = 50
MAX_OPTIONS = 10
PRECISION = Decimal("0.001")
ITEM_TYPES = {
    "multiple-choice",
    "checkboxes",
    "short-answer",
    "paragraph",
    "diagnostic-field",
    "information",
}
ANSWER_KEYS = {"answerKey", "acceptedAnswers", "regions", "diagnoses"}


class AssessmentContractError(ValueError):
    pass


@dataclass(frozen=True)
class CompiledAssessment:
    definition: dict[str, Any]
    learner_manifest: dict[str, Any]
    checksum: str


def _canonical_json(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _strip_answers(value: Any, *, inside_answer: bool = False) -> Any:
    if isinstance(value, dict):
        return {
            key: _strip_answers(item)
            for key, item in value.items()
            if not inside_answer and key not in ANSWER_KEYS and key != "scoring"
        }
    if isinstance(value, list):
        return [_strip_answers(item, inside_answer=inside_answer) for item in value]
    return value


def _require(condition: bool, code: str) -> None:
    if not condition:
        raise AssessmentContractError(code)


def compile_assessment(draft: dict[str, Any]) -> CompiledAssessment:
    _require(isinstance(draft, dict), "ASSESSMENT_INVALID_DOCUMENT")
    items = draft.get("items")
    if not isinstance(items, list) or not items:
        raise AssessmentContractError("ASSESSMENT_ITEMS_REQUIRED")
    _require(len(items) <= MAX_ITEMS, "ASSESSMENT_ITEM_LIMIT")
    ids: set[str] = set()
    slide_ids: set[str] = set()
    normalized_items: list[dict[str, Any]] = []
    for position, raw in enumerate(items):
        _require(isinstance(raw, dict), "ASSESSMENT_INVALID_ITEM")
        item = dict(raw)
        item_id = item.get("id")
        if not isinstance(item_id, str) or not item_id:
            raise AssessmentContractError("ASSESSMENT_ITEM_ID_REQUIRED")
        _require(item_id not in ids, "ASSESSMENT_DUPLICATE_ID")
        ids.add(item_id)
        item_type = item.get("type")
        _require(item_type in ITEM_TYPES, "ASSESSMENT_ITEM_TYPE_INVALID")
        _require(isinstance(item.get("prompt"), str), "ASSESSMENT_PROMPT_REQUIRED")
        if item_type != "information":
            points = Decimal(str(item.get("points", "0")))
            _require(points >= 0, "ASSESSMENT_POINTS_INVALID")
        if item_type in {"multiple-choice", "checkboxes", "diagnostic-field"} or (
            item_type == "short-answer" and not item.get("manual", False)
        ):
            _require("answerKey" in item, "ASSESSMENT_ANSWER_KEY_REQUIRED")
        options = item.get("options", [])
        _require(isinstance(options, list), "ASSESSMENT_OPTIONS_INVALID")
        _require(len(options) <= MAX_OPTIONS, "ASSESSMENT_OPTION_LIMIT")
        option_ids = [option.get("id") for option in options if isinstance(option, dict)]
        _require(len(option_ids) == len(set(option_ids)), "ASSESSMENT_DUPLICATE_ID")
        slide_id = item.get("slideId")
        if slide_id is not None:
            _require(isinstance(slide_id, str) and bool(slide_id), "ASSESSMENT_SLIDE_INVALID")
            slide_ids.add(slide_id)
        item["position"] = position
        normalized_items.append(item)
    _require(len(slide_ids) <= MAX_SLIDES, "ASSESSMENT_SLIDE_LIMIT")
    definition = {**draft, "schema": SCHEMA, "items": normalized_items}
    encoded = _canonical_json(definition)
    _require(len(encoded) <= MAX_DEFINITION_BYTES, "ASSESSMENT_DEFINITION_LIMIT")
    checksum = hashlib.sha256(encoded).hexdigest()
    learner = _strip_answers(definition)
    return CompiledAssessment(definition=definition, learner_manifest=learner, checksum=checksum)


def normalize_short_answer(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value)
    return " ".join(normalized.strip().split()).casefold()


def _decimal(value: object) -> Decimal:
    return Decimal(str(value))


def _quantize(value: Decimal) -> Decimal:
    return value.quantize(PRECISION, rounding=ROUND_HALF_UP)


def _rectangle_iou(first: dict[str, Any], second: dict[str, Any]) -> float:
    left = max(float(first["x"]), float(second["x"]))
    top = max(float(first["y"]), float(second["y"]))
    right = min(
        float(first["x"]) + float(first["width"]), float(second["x"]) + float(second["width"])
    )
    bottom = min(
        float(first["y"]) + float(first["height"]), float(second["y"]) + float(second["height"])
    )
    intersection = max(0.0, right - left) * max(0.0, bottom - top)
    union = (
        float(first["width"]) * float(first["height"])
        + float(second["width"]) * float(second["height"])
        - intersection
    )
    return intersection / union if union else 0.0


def _point_in_rectangle(point: dict[str, Any], rectangle: dict[str, Any]) -> bool:
    return float(rectangle["x"]) <= float(point["x"]) <= float(rectangle["x"]) + float(
        rectangle["width"]
    ) and float(rectangle["y"]) <= float(point["y"]) <= float(rectangle["y"]) + float(
        rectangle["height"]
    )


def _region_matches(
    selection: dict[str, Any], accepted: dict[str, Any], scoring: dict[str, Any]
) -> bool:
    if selection.get("kind") == "point" and accepted.get("kind") == "point":
        return math.dist(
            (float(selection["x"]), float(selection["y"])),
            (float(accepted["x"]), float(accepted["y"])),
        ) <= float(scoring.get("pointTolerance", 0.03))
    if selection.get("kind") == "point" and accepted.get("kind") == "rectangle":
        return _point_in_rectangle(selection, accepted)
    if selection.get("kind") == "rectangle":
        center = {
            "kind": "point",
            "x": float(selection["x"]) + float(selection["width"]) / 2,
            "y": float(selection["y"]) + float(selection["height"]) / 2,
        }
        if accepted.get("kind") == "point":
            return _region_matches(center, accepted, scoring)
        return _point_in_rectangle(center, accepted) or _rectangle_iou(
            selection, accepted
        ) >= float(scoring.get("rectangleIou", 0.25))
    return False


def score_item(item: dict[str, Any], response: dict[str, Any]) -> Decimal | None:
    item_type = item["type"]
    points = _decimal(item.get("points", 0))
    answer = item.get("answerKey", {})
    fraction = Decimal("0")
    if item_type in {"multiple-choice", "dropdown"}:
        fraction = Decimal(response.get("optionId") in set(answer.get("optionIds", [])))
    elif item_type == "checkboxes":
        selected = set(response.get("optionIds", []))
        correct = set(answer.get("optionIds", []))
        if not item.get("scoring", {}).get("partialCredit", False):
            fraction = Decimal(selected == correct)
        else:
            all_options = {option["id"] for option in item.get("options", [])}
            incorrect = all_options - correct
            positive = Decimal(len(selected & correct)) / Decimal(max(1, len(correct)))
            penalty = Decimal(len(selected & incorrect)) / Decimal(max(1, len(incorrect)))
            fraction = max(Decimal("0"), min(Decimal("1"), positive - penalty))
    elif item_type in {"short-answer", "paragraph"} and item.get("manual", False):
        return None
    elif item_type in {"short-answer", "paragraph"}:
        submitted = normalize_short_answer(str(response.get("text", "")))
        variants = {normalize_short_answer(str(value)) for value in answer.get("variants", [])}
        keywords = {
            normalize_short_answer(str(value))
            for value in answer.get("keywords", [])
            if normalize_short_answer(str(value))
        }
        if submitted in variants:
            fraction = Decimal("1")
        elif keywords:
            matches = sum(keyword in submitted for keyword in keywords)
            fraction = (
                Decimal(matches) / Decimal(len(keywords))
                if item.get("scoring", {}).get("partialCredit", False)
                else Decimal(matches == len(keywords))
            )
        else:
            return None
    elif item.get("manual", False):
        return None
    elif item_type == "diagnostic-field":
        selection = response.get("selection")
        regions = answer.get("regions", [])
        region_present = bool(regions)
        region_correct = isinstance(selection, dict) and any(
            _region_matches(selection, accepted, item.get("scoring", {})) for accepted in regions
        )
        diagnoses = {normalize_short_answer(str(value)) for value in answer.get("diagnoses", [])}
        diagnosis_present = bool(diagnoses)
        diagnosis_correct = normalize_short_answer(str(response.get("diagnosis", ""))) in diagnoses
        if region_present and diagnosis_present:
            fraction = (Decimal(region_correct) + Decimal(diagnosis_correct)) / Decimal("2")
        elif region_present:
            fraction = Decimal(region_correct)
        elif diagnosis_present:
            fraction = Decimal(diagnosis_correct)
    elif item_type == "rating":
        value = response.get("value")
        rating = item.get("rating", {})
        try:
            if value is None:
                raise ValueError
            valid = int(value) == float(value) and 1 <= int(value) <= int(rating.get("max", 0))
        except (TypeError, ValueError, OverflowError):
            valid = False
        fraction = Decimal(valid) if item.get("answerKey", {}).get("value") is None else Decimal(
            value == item["answerKey"]["value"]
        )
    elif item_type in {"information", "section-information"}:
        return Decimal("0.000")
    return _quantize(points * fraction)
