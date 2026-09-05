from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from decimal import Decimal, InvalidOperation
from typing import Any, cast

from .assessment_contract import AssessmentContractError, CompiledAssessment

V1_SCHEMA = "pathlab.assessment/1"
V2_SCHEMA = "pathlab.assessment/2"
# Ten 475 KB captured images expand to less than 7 MB as data URLs. Keep a
# bounded 8 MB envelope with room for the rest of the assessment definition.
MAX_DEFINITION_BYTES = 8 * 1024 * 1024
MAX_SECTIONS = 75
MAX_ITEMS = 100
MAX_OPTIONS = 10
MAX_SLIDES = 50
MAX_MEDIA_ITEMS = 10
MAX_TITLE = 200
MAX_DESCRIPTION = 2_000
MAX_HELP_TEXT = 1_000
MAX_MESSAGE = 1_000
MAX_VALIDATION_MESSAGE = 500
MAX_FEEDBACK = 4_000
MAX_TEACHER_NOTES = 2_000
V2_ITEM_TYPES = {
    "multiple-choice",
    "checkboxes",
    "dropdown",
    "rating",
    "short-answer",
    "paragraph",
    "diagnostic-field",
    "section-information",
}
CHOICE_TYPES = {"multiple-choice", "checkboxes", "dropdown"}
RATING_STYLES = {"numbers", "stars", "hearts", "thumbs-up"}
PRIVATE_KEYS = {
    "answerKey",
    "acceptedAnswers",
    "regions",
    "diagnoses",
    "scoring",
    "feedback",
    "teacherNotes",
    "annotations",
    "annotationGeometry",
    "adminUrl",
    "filesystemPath",
}


def _require(condition: bool, code: str) -> None:
    if not condition:
        raise AssessmentContractError(code)


def _canonical_json(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def document_schema(document: dict[str, Any]) -> str:
    schema = document.get("schema")
    if schema is None:
        return V1_SCHEMA
    _require(schema in {V1_SCHEMA, V2_SCHEMA}, "ASSESSMENT_SCHEMA_INVALID")
    return str(schema)


def flatten_v2_items(document: dict[str, Any]) -> list[dict[str, Any]]:
    return [item for section in document.get("sections", []) for item in section.get("items", [])]


def _bounded_text(value: object, maximum: int, code: str, *, required: bool = False) -> str:
    _require(isinstance(value, str), code)
    text = str(value)
    _require(not required or bool(text.strip()), code)
    _require(len(text) <= maximum, code)
    return text


def _strip_private(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _strip_private(item) for key, item in value.items() if key not in PRIVATE_KEYS}
    if isinstance(value, list):
        return [_strip_private(item) for item in value]
    return value


def _validate_route(route: object, section_ids: set[str], option_ids: set[str]) -> None:
    _require(isinstance(route, dict), "ASSESSMENT_ROUTE_INVALID")
    route_data = cast(dict[str, Any], route)
    targets = [route_data.get("defaultSectionId")]
    rules = route_data.get("rules", [])
    _require(isinstance(rules, list), "ASSESSMENT_ROUTE_INVALID")
    for rule in rules:
        _require(isinstance(rule, dict), "ASSESSMENT_ROUTE_INVALID")
        rule_data = cast(dict[str, Any], rule)
        targets.append(rule_data.get("goToSectionId"))
        condition = rule_data.get("when")
        _require(isinstance(condition, dict), "ASSESSMENT_ROUTE_INVALID")
        option_id = cast(dict[str, Any], condition).get("optionId")
        if option_id is not None:
            _require(option_id in option_ids, "ASSESSMENT_ROUTE_INVALID")
    for target in targets:
        if target is not None:
            _require(target in section_ids, "ASSESSMENT_ROUTE_INVALID")


def _validate_question_media(media: object, slide_ids: set[str]) -> None:
    _require(isinstance(media, dict), "ASSESSMENT_MEDIA_INVALID")
    media_data = cast(dict[str, Any], media)
    media_kind = media_data.get("kind")
    _require(media_kind in {"slide-thumbnail", "uploaded-image"}, "ASSESSMENT_MEDIA_INVALID")
    asset_path = media_data.get("assetPath")
    if media_kind == "slide-thumbnail":
        media_slide = media_data.get("slideId")
        _require(isinstance(media_slide, str) and bool(media_slide), "ASSESSMENT_MEDIA_INVALID")
        if asset_path is not None:
            _require(
                isinstance(asset_path, str) and asset_path.startswith("/assessment-assets/"),
                "ASSESSMENT_MEDIA_INVALID",
            )
        slide_ids.add(cast(str, media_slide))
    else:
        _require(
            isinstance(asset_path, str)
            and len(asset_path) <= 700_000
            and asset_path.startswith(
                (
                    "data:image/jpeg;base64,",
                    "data:image/png;base64,",
                    "data:image/webp;base64,",
                )
            ),
            "ASSESSMENT_MEDIA_INVALID",
        )
    viewport = media_data.get("viewport")
    if viewport is not None:
        _require(isinstance(viewport, dict), "ASSESSMENT_MEDIA_INVALID")
        _require(
            all(isinstance(viewport.get(key), (int, float)) for key in ("x", "y", "scale")),
            "ASSESSMENT_MEDIA_INVALID",
        )
        _require(
            0 <= viewport["x"] <= 100
            and 0 <= viewport["y"] <= 100
            and 1 <= viewport["scale"] <= 3,
            "ASSESSMENT_MEDIA_INVALID",
        )
    capture = media_data.get("capture")
    captured_image = media_data.get("capturedImage")
    if captured_image is not None:
        _require(isinstance(captured_image, dict), "ASSESSMENT_MEDIA_INVALID")
        captured_path = captured_image.get("assetPath")
        _require(
            isinstance(captured_path, str)
            and len(captured_path) <= 700_000
            and captured_path.startswith("data:image/webp;base64,"),
            "ASSESSMENT_MEDIA_INVALID",
        )
        _require(
            isinstance(captured_image.get("width"), int)
            and isinstance(captured_image.get("height"), int)
            and isinstance(captured_image.get("bytes"), int)
            and 1 <= captured_image["width"] <= 1600
            and 1 <= captured_image["height"] <= 1600
            and 1 <= captured_image["bytes"] <= 475 * 1024,
            "ASSESSMENT_MEDIA_INVALID",
        )
    marks = media_data.get("marks", [])
    if capture is not None:
        _require(
            isinstance(capture, dict) and capture.get("kind") == "rectangle",
            "ASSESSMENT_MEDIA_INVALID",
        )
    for region in ([capture] if capture is not None else []) + (
        marks if isinstance(marks, list) else [None]
    ):
        _require(isinstance(region, dict), "ASSESSMENT_MEDIA_INVALID")
        region_kind = region.get("kind")
        _require(region_kind in {"point", "rectangle", "freehand"}, "ASSESSMENT_MEDIA_INVALID")
        if region_kind == "freehand":
            points = region.get("points")
            _require(
                isinstance(points, list) and 2 <= len(points) <= 2048,
                "ASSESSMENT_MEDIA_INVALID",
            )
            for point in points:
                _require(
                    isinstance(point, dict)
                    and all(isinstance(point.get(key), (int, float)) for key in ("x", "y"))
                    and 0 <= point["x"] <= 1
                    and 0 <= point["y"] <= 1,
                    "ASSESSMENT_MEDIA_INVALID",
                )
            if "label" in region:
                _bounded_text(region.get("label"), 120, "ASSESSMENT_MEDIA_INVALID")
            continue
        keys = ("x", "y") if region_kind == "point" else ("x", "y", "width", "height")
        _require(
            all(isinstance(region.get(key), (int, float)) for key in keys),
            "ASSESSMENT_MEDIA_INVALID",
        )
        _require(0 <= region["x"] <= 1 and 0 <= region["y"] <= 1, "ASSESSMENT_MEDIA_INVALID")
        if region_kind == "rectangle":
            _require(
                0 < region["width"] <= 1
                and 0 < region["height"] <= 1
                and region["x"] + region["width"] <= 1.000001
                and region["y"] + region["height"] <= 1.000001,
                "ASSESSMENT_MEDIA_INVALID",
            )
        if "label" in region:
            _bounded_text(region.get("label"), 120, "ASSESSMENT_MEDIA_INVALID")
    _require(isinstance(marks, list) and len(marks) <= 20, "ASSESSMENT_MEDIA_INVALID")
    if "alt" in media_data:
        _bounded_text(media_data.get("alt"), 500, "ASSESSMENT_MEDIA_INVALID")


def _validate_item(
    raw: object,
    *,
    section_ids: set[str],
    all_ids: set[str],
    slide_ids: set[str],
    position: int,
) -> dict[str, Any]:
    _require(isinstance(raw, dict), "ASSESSMENT_INVALID_ITEM")
    item = deepcopy(cast(dict[str, Any], raw))
    item_id = item.get("id")
    _require(isinstance(item_id, str) and bool(item_id), "ASSESSMENT_ITEM_ID_REQUIRED")
    item_id = cast(str, item_id)
    _require(item_id not in all_ids, "ASSESSMENT_DUPLICATE_ID")
    all_ids.add(item_id)
    item_type = item.get("type")
    _require(item_type in V2_ITEM_TYPES, "ASSESSMENT_ITEM_TYPE_INVALID")
    _bounded_text(item.get("prompt"), MAX_DESCRIPTION, "ASSESSMENT_PROMPT_REQUIRED", required=True)
    if "helpText" in item:
        _bounded_text(item["helpText"], MAX_HELP_TEXT, "ASSESSMENT_HELP_TEXT_LIMIT")
    if "teacherNotes" in item:
        _bounded_text(item["teacherNotes"], MAX_TEACHER_NOTES, "ASSESSMENT_TEACHER_NOTES_LIMIT")
    feedback = item.get("feedback", {})
    _require(isinstance(feedback, dict), "ASSESSMENT_FEEDBACK_INVALID")
    for value in feedback.values():
        _bounded_text(value, MAX_FEEDBACK, "ASSESSMENT_FEEDBACK_LIMIT")
    validation = item.get("validation", {})
    _require(isinstance(validation, dict), "ASSESSMENT_VALIDATION_INVALID")
    if "message" in validation:
        _bounded_text(
            validation["message"],
            MAX_VALIDATION_MESSAGE,
            "ASSESSMENT_VALIDATION_MESSAGE_LIMIT",
        )

    if item_type != "section-information":
        try:
            points = Decimal(str(item.get("points", "0")))
        except (InvalidOperation, ValueError):
            raise AssessmentContractError("ASSESSMENT_POINTS_INVALID") from None
        _require(points.is_finite() and points >= 0, "ASSESSMENT_POINTS_INVALID")

    options = item.get("options", [])
    _require(isinstance(options, list), "ASSESSMENT_OPTIONS_INVALID")
    _require(len(options) <= MAX_OPTIONS, "ASSESSMENT_OPTION_LIMIT")
    if item_type in CHOICE_TYPES:
        _require(len(options) >= 2, "ASSESSMENT_OPTIONS_REQUIRED")
    option_ids: set[str] = set()
    labels: set[str] = set()
    for option in options:
        _require(isinstance(option, dict), "ASSESSMENT_OPTIONS_INVALID")
        option_id = option.get("id")
        _require(isinstance(option_id, str) and bool(option_id), "ASSESSMENT_OPTION_ID_REQUIRED")
        _require(
            option_id not in all_ids and option_id not in option_ids,
            "ASSESSMENT_DUPLICATE_ID",
        )
        option_ids.add(option_id)
        all_ids.add(option_id)
        label = _bounded_text(
            option.get("label"), MAX_MESSAGE, "ASSESSMENT_OPTION_LABEL_REQUIRED", required=True
        )
        normalized_label = " ".join(label.split()).casefold()
        _require(normalized_label not in labels, "ASSESSMENT_DUPLICATE_OPTION_LABEL")
        labels.add(normalized_label)
        option_media_items = option.get("mediaItems", [])
        _require(isinstance(option_media_items, list), "ASSESSMENT_MEDIA_INVALID")
        option_media_collection = (
            [option["media"]] if option.get("media") is not None else []
        ) + option_media_items
        _require(len(option_media_collection) <= 3, "ASSESSMENT_MEDIA_LIMIT")
        for option_media in option_media_collection:
            _require(isinstance(option_media, dict), "ASSESSMENT_MEDIA_INVALID")
            media_kind = option_media.get("kind")
            _require(
                media_kind in {"slide-thumbnail", "uploaded-image"},
                "ASSESSMENT_MEDIA_INVALID",
            )
            asset_path = option_media.get("assetPath")
            if media_kind == "slide-thumbnail":
                media_slide = option_media.get("slideId")
                _require(
                    isinstance(media_slide, str) and bool(media_slide),
                    "ASSESSMENT_MEDIA_INVALID",
                )
                if asset_path is not None:
                    _require(
                        isinstance(asset_path, str)
                        and asset_path.startswith(("/assessment-assets/", "/tiles/"))
                        and ".." not in asset_path,
                        "ASSESSMENT_MEDIA_INVALID",
                    )
                slide_ids.add(media_slide)
            else:
                _require(
                    isinstance(asset_path, str)
                    and len(asset_path) <= 700_000
                    and asset_path.startswith(
                        (
                            "data:image/jpeg;base64,",
                            "data:image/png;base64,",
                            "data:image/webp;base64,",
                        )
                    ),
                    "ASSESSMENT_MEDIA_INVALID",
                )
            if "alt" in option_media:
                _bounded_text(option_media.get("alt"), 500, "ASSESSMENT_MEDIA_INVALID")

    answer_key = item.get("answerKey")
    if item_type in CHOICE_TYPES:
        _require(isinstance(answer_key, dict), "ASSESSMENT_ANSWER_KEY_REQUIRED")
        keys = cast(dict[str, Any], answer_key).get("optionIds", [])
        _require(isinstance(keys, list) and bool(keys), "ASSESSMENT_ANSWER_KEY_REQUIRED")
        _require(set(keys) <= option_ids, "ASSESSMENT_ANSWER_KEY_INVALID")

    if item_type == "rating":
        rating = item.get("rating")
        _require(isinstance(rating, dict), "ASSESSMENT_RATING_INVALID")
        rating_data = cast(dict[str, Any], rating)
        _require(rating_data.get("min") == 1, "ASSESSMENT_RATING_INVALID")
        maximum = rating_data.get("max")
        _require(isinstance(maximum, int) and 3 <= maximum <= 10, "ASSESSMENT_RATING_INVALID")
        _require(rating_data.get("style") in RATING_STYLES, "ASSESSMENT_RATING_INVALID")

    slide_id = item.get("slideId")
    if slide_id is not None:
        _require(isinstance(slide_id, str) and bool(slide_id), "ASSESSMENT_SLIDE_INVALID")
        slide_ids.add(slide_id)
    media = item.get("media")
    if media is not None:
        _require(isinstance(media, dict), "ASSESSMENT_MEDIA_INVALID")
        media_kind = media.get("kind")
        _require(media_kind in {"slide-thumbnail", "uploaded-image"}, "ASSESSMENT_MEDIA_INVALID")
        asset_path = media.get("assetPath")
        if media_kind == "slide-thumbnail":
            media_slide = media.get("slideId")
            _require(isinstance(media_slide, str) and bool(media_slide), "ASSESSMENT_MEDIA_INVALID")
            if asset_path is not None:
                _require(
                    isinstance(asset_path, str)
                    and asset_path.startswith(("/assessment-assets/", "/tiles/"))
                    and ".." not in asset_path,
                    "ASSESSMENT_MEDIA_INVALID",
                )
            slide_ids.add(media_slide)
        else:
            _require(
                isinstance(asset_path, str)
                and len(asset_path) <= 700_000
                and asset_path.startswith(
                    (
                        "data:image/jpeg;base64,",
                        "data:image/png;base64,",
                        "data:image/webp;base64,",
                    )
                ),
                "ASSESSMENT_MEDIA_INVALID",
            )
        viewport = media.get("viewport")
        if viewport is not None:
            _require(isinstance(viewport, dict), "ASSESSMENT_MEDIA_INVALID")
            _require(
                all(
                    isinstance(viewport.get(key), (int, float))
                    for key in ("x", "y", "scale")
                ),
                "ASSESSMENT_MEDIA_INVALID",
            )
            _require(
                0 <= viewport["x"] <= 100
                and 0 <= viewport["y"] <= 100
                and 1 <= viewport["scale"] <= 3,
                "ASSESSMENT_MEDIA_INVALID",
            )
        capture = media.get("capture")
        captured_image = media.get("capturedImage")
        if captured_image is not None:
            _require(isinstance(captured_image, dict), "ASSESSMENT_MEDIA_INVALID")
            captured_path = captured_image.get("assetPath")
            _require(
                isinstance(captured_path, str)
                and len(captured_path) <= 700_000
                and captured_path.startswith("data:image/webp;base64,"),
                "ASSESSMENT_MEDIA_INVALID",
            )
            _require(
                isinstance(captured_image.get("width"), int)
                and isinstance(captured_image.get("height"), int)
                and isinstance(captured_image.get("bytes"), int)
                and 1 <= captured_image["width"] <= 1600
                and 1 <= captured_image["height"] <= 1600
                and 1 <= captured_image["bytes"] <= 475 * 1024,
                "ASSESSMENT_MEDIA_INVALID",
            )
        marks = media.get("marks", [])
        if capture is not None:
            _require(
                isinstance(capture, dict) and capture.get("kind") == "rectangle",
                "ASSESSMENT_MEDIA_INVALID",
            )
        for region in ([capture] if capture is not None else []) + (
            marks if isinstance(marks, list) else [None]
        ):
            _require(isinstance(region, dict), "ASSESSMENT_MEDIA_INVALID")
            region_kind = region.get("kind")
            _require(region_kind in {"point", "rectangle", "freehand"}, "ASSESSMENT_MEDIA_INVALID")
            if region_kind == "freehand":
                points = region.get("points")
                _require(
                    isinstance(points, list) and 2 <= len(points) <= 2048,
                    "ASSESSMENT_MEDIA_INVALID",
                )
                for point in points:
                    _require(
                        isinstance(point, dict)
                        and all(isinstance(point.get(key), (int, float)) for key in ("x", "y"))
                        and 0 <= point["x"] <= 1
                        and 0 <= point["y"] <= 1,
                        "ASSESSMENT_MEDIA_INVALID",
                    )
                if "label" in region:
                    _bounded_text(region.get("label"), 120, "ASSESSMENT_MEDIA_INVALID")
                continue
            keys = ("x", "y") if region_kind == "point" else ("x", "y", "width", "height")
            _require(
                all(isinstance(region.get(key), (int, float)) for key in keys),
                "ASSESSMENT_MEDIA_INVALID",
            )
            _require(
                0 <= region["x"] <= 1 and 0 <= region["y"] <= 1,
                "ASSESSMENT_MEDIA_INVALID",
            )
            if region_kind == "rectangle":
                _require(
                    0 < region["width"] <= 1
                    and 0 < region["height"] <= 1
                    and region["x"] + region["width"] <= 1.000001
                    and region["y"] + region["height"] <= 1.000001,
                    "ASSESSMENT_MEDIA_INVALID",
                )
            if "label" in region:
                _bounded_text(region.get("label"), 120, "ASSESSMENT_MEDIA_INVALID")
        _require(
            isinstance(marks, list) and len(marks) <= 20,
            "ASSESSMENT_MEDIA_INVALID",
        )
        if "alt" in media:
            _bounded_text(media.get("alt"), 500, "ASSESSMENT_MEDIA_INVALID")

    media_items = item.get("mediaItems", [])
    _require(isinstance(media_items, list), "ASSESSMENT_MEDIA_INVALID")
    _require(
        len(media_items) <= MAX_MEDIA_ITEMS - (1 if media is not None else 0),
        "ASSESSMENT_MEDIA_LIMIT",
    )
    _require(not media_items or media is not None, "ASSESSMENT_MEDIA_INVALID")
    for additional_media in media_items:
        _validate_question_media(additional_media, slide_ids)

    if "routing" in item:
        _validate_route(item["routing"], section_ids, option_ids)
    item["position"] = position
    return item


def compile_assessment_v2(draft: dict[str, Any]) -> CompiledAssessment:
    _require(isinstance(draft, dict), "ASSESSMENT_INVALID_DOCUMENT")
    _require(document_schema(draft) == V2_SCHEMA, "ASSESSMENT_SCHEMA_INVALID")
    _bounded_text(draft.get("title"), MAX_TITLE, "ASSESSMENT_TITLE_LIMIT", required=True)
    if "description" in draft:
        _bounded_text(draft["description"], MAX_DESCRIPTION, "ASSESSMENT_DESCRIPTION_LIMIT")
    sections = draft.get("sections")
    _require(isinstance(sections, list) and bool(sections), "ASSESSMENT_SECTIONS_REQUIRED")
    sections = cast(list[Any], sections)
    _require(len(sections) <= MAX_SECTIONS, "ASSESSMENT_SECTION_LIMIT")

    section_ids: set[str] = set()
    for raw in sections:
        _require(isinstance(raw, dict), "ASSESSMENT_INVALID_SECTION")
        section_id = raw.get("id")
        _require(isinstance(section_id, str) and bool(section_id), "ASSESSMENT_SECTION_ID_REQUIRED")
        _require(section_id not in section_ids, "ASSESSMENT_DUPLICATE_ID")
        section_ids.add(section_id)

    all_ids = set(section_ids)
    slide_ids: set[str] = set()
    normalized_sections: list[dict[str, Any]] = []
    position = 0
    for section_position, raw in enumerate(sections):
        _require(isinstance(raw, dict), "ASSESSMENT_INVALID_SECTION")
        section = deepcopy(cast(dict[str, Any], raw))
        _bounded_text(
            section.get("title"), MAX_TITLE, "ASSESSMENT_SECTION_TITLE_REQUIRED", required=True
        )
        if "description" in section:
            _bounded_text(
                section["description"], MAX_DESCRIPTION, "ASSESSMENT_SECTION_DESCRIPTION_LIMIT"
            )
        section_slide = section.get("slideId")
        if section_slide is not None:
            _require(
                isinstance(section_slide, str) and bool(section_slide),
                "ASSESSMENT_SLIDE_INVALID",
            )
            slide_ids.add(section_slide)
        items = section.get("items")
        _require(isinstance(items, list), "ASSESSMENT_ITEMS_REQUIRED")
        items = cast(list[Any], items)
        normalized_items: list[dict[str, Any]] = []
        for raw_item in items:
            normalized_items.append(
                _validate_item(
                    raw_item,
                    section_ids=section_ids,
                    all_ids=all_ids,
                    slide_ids=slide_ids,
                    position=position,
                )
            )
            position += 1
        section["position"] = section_position
        section["items"] = normalized_items
        normalized_sections.append(section)

    _require(position > 0, "ASSESSMENT_ITEMS_REQUIRED")
    _require(position <= MAX_ITEMS, "ASSESSMENT_ITEM_LIMIT")
    _require(len(slide_ids) <= MAX_SLIDES, "ASSESSMENT_SLIDE_LIMIT")
    definition = {**deepcopy(draft), "schema": V2_SCHEMA, "sections": normalized_sections}
    encoded = _canonical_json(definition)
    _require(len(encoded) <= MAX_DEFINITION_BYTES, "ASSESSMENT_DEFINITION_LIMIT")
    return CompiledAssessment(
        definition=definition,
        learner_manifest=_strip_private(definition),
        checksum=hashlib.sha256(encoded).hexdigest(),
    )
