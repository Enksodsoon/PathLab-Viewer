import hashlib
import json
import math
import re
from decimal import Decimal
from typing import Any, NoReturn

SCHEMA = "pathlab.study-pack/1"
SCHEMA_V2 = "pathlab.study-pack/2"
MAX_PACK_BYTES = 2 * 1024 * 1024
MAX_SLIDES = 50
MAX_TASKS = 500
PREVIEW_VERSION = "pathlab.study-preview/1"


def parse_json(raw: bytes) -> dict[str, Any]:
    if not raw or len(raw) > MAX_PACK_BYTES:
        raise ValueError("STUDY_PACK_SIZE_INVALID")

    def unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("STUDY_PACK_DUPLICATE_FIELD")
            result[key] = value
        return result

    def reject_constant(_: str) -> NoReturn:
        raise ValueError("STUDY_PACK_NUMBER_INVALID")

    value: Any = json.loads(raw, object_pairs_hook=unique_object, parse_constant=reject_constant)
    if not isinstance(value, dict):
        raise ValueError("STUDY_PACK_OBJECT_REQUIRED")
    return value


def canonical_json(value: Any) -> str:
    if value is None:
        return "null"
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("STUDY_PACK_NUMBER_INVALID")
        decimal = Decimal(str(value))
        return "0" if decimal.is_zero() else format(decimal.normalize(), "f")
    if isinstance(value, list):
        return "[" + ",".join(canonical_json(item) for item in value) + "]"
    if isinstance(value, dict):
        if not all(isinstance(key, str) for key in value):
            raise ValueError("STUDY_PACK_KEY_INVALID")
        return (
            "{"
            + ",".join(
                canonical_json(key) + ":" + canonical_json(value[key]) for key in sorted(value)
            )
            + "}"
        )
    raise ValueError("STUDY_PACK_VALUE_INVALID")


def content_checksum(definition: dict[str, Any]) -> str:
    core = {
        key: value for key, value in definition.items() if key not in {"checksum", "facultyPreview"}
    }
    return hashlib.sha256(canonical_json(core).encode("utf-8")).hexdigest()


def _text(value: Any, *, maximum: int) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise ValueError("STUDY_PACK_TEXT_INVALID")
    return value.strip()


def _unit(value: Any, *, positive: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("STUDY_PACK_COORDINATE_INVALID")
    number = float(value)
    lower_ok = number > 0 if positive else number >= 0
    if not math.isfinite(number) or not lower_ok or number > 1:
        raise ValueError("STUDY_PACK_COORDINATE_INVALID")
    return number


def validate_study_pack(definition: dict[str, Any]) -> str:
    if len(canonical_json(definition).encode("utf-8")) > MAX_PACK_BYTES:
        raise ValueError("STUDY_PACK_SIZE_INVALID")
    schema = definition.get("schema")
    if schema not in {SCHEMA, SCHEMA_V2}:
        raise ValueError("STUDY_PACK_SCHEMA_UNSUPPORTED")
    pack_key = _text(definition.get("packKey"), maximum=120)
    if not re.fullmatch(r"[A-Za-z0-9._-]+", pack_key):
        raise ValueError("STUDY_PACK_KEY_INVALID")
    version = definition.get("version")
    if isinstance(version, bool) or not isinstance(version, int) or version < 1:
        raise ValueError("STUDY_PACK_VERSION_INVALID")
    for name, maximum in (
        ("title", 240),
        ("author", 240),
        ("license", 240),
        ("provenance", 1000),
        ("revision", 120),
    ):
        _text(definition.get(name), maximum=maximum)
    languages = definition.get("languages")
    if (
        not isinstance(languages, list)
        or not languages
        or not all(language in {"en", "th"} for language in languages)
    ):
        raise ValueError("STUDY_PACK_LANGUAGES_INVALID")
    if schema == SCHEMA_V2:
        if languages != ["en"]:
            raise ValueError("STUDY_PACK_V2_ENGLISH_ONLY")
        knowledge_checksum = _text(definition.get("knowledgePackChecksum"), maximum=64)
        if not re.fullmatch(r"[a-f0-9]{64}", knowledge_checksum):
            raise ValueError("STUDY_PACK_KNOWLEDGE_INVALID")

    slides = definition.get("slides")
    if not isinstance(slides, list) or not 1 <= len(slides) <= MAX_SLIDES:
        raise ValueError("STUDY_PACK_SLIDES_INVALID")
    slide_ids: set[str] = set()
    for slide in slides:
        if not isinstance(slide, dict):
            raise ValueError("STUDY_PACK_SLIDE_INVALID")
        slide_id = _text(slide.get("viewerSlideId"), maximum=100)
        checksum = _text(slide.get("sha256"), maximum=64)
        _text(slide.get("displayName"), maximum=200)
        if slide_id in slide_ids or not re.fullmatch(r"[a-f0-9]{64}", checksum):
            raise ValueError("STUDY_PACK_SLIDE_INVALID")
        slide_ids.add(slide_id)
        if schema == SCHEMA_V2:
            evidence_checksum = _text(slide.get("evidenceBundleSha256"), maximum=64)
            if not re.fullmatch(r"[a-f0-9]{64}", evidence_checksum):
                raise ValueError("STUDY_PACK_EVIDENCE_INVALID")

    tasks = definition.get("tasks")
    if not isinstance(tasks, list) or not 1 <= len(tasks) <= MAX_TASKS:
        raise ValueError("STUDY_PACK_TASKS_INVALID")
    task_ids: set[str] = set()
    for task in tasks:
        if not isinstance(task, dict):
            raise ValueError("STUDY_PACK_TASK_INVALID")
        task_id = _text(task.get("id"), maximum=120)
        if task_id in task_ids or not re.fullmatch(r"[A-Za-z0-9._-]+", task_id):
            raise ValueError("STUDY_PACK_TASK_INVALID")
        task_ids.add(task_id)
        if _text(task.get("slideId"), maximum=100) not in slide_ids:
            raise ValueError("STUDY_PACK_TASK_SLIDE_INVALID")
        _text(task.get("prompt"), maximum=2000)
        hints = task.get("hints", [])
        if not isinstance(hints, list) or len(hints) > 3:
            raise ValueError("STUDY_PACK_HINTS_INVALID")
        for hint in hints:
            _text(hint, maximum=2000)
        _text(task.get("explanation"), maximum=8000)
        sources = task.get("sources")
        if not isinstance(sources, list) or not sources or len(sources) > 10:
            raise ValueError("STUDY_PACK_SOURCES_INVALID")
        for source in sources:
            if not isinstance(source, dict):
                raise ValueError("STUDY_PACK_SOURCE_INVALID")
            _text(source.get("title"), maximum=500)
            url = _text(source.get("url"), maximum=1000)
            if not url.startswith("https://"):
                raise ValueError("STUDY_PACK_SOURCE_INVALID")
        if schema == SCHEMA_V2:
            claim_ids = task.get("claimIds")
            if not isinstance(claim_ids, list) or not 1 <= len(claim_ids) <= 10:
                raise ValueError("STUDY_PACK_CLAIMS_INVALID")
            if len(set(claim_ids)) != len(claim_ids):
                raise ValueError("STUDY_PACK_CLAIMS_INVALID")
            for claim_id in claim_ids:
                if not re.fullmatch(r"[A-Za-z0-9._-]{1,160}", _text(claim_id, maximum=160)):
                    raise ValueError("STUDY_PACK_CLAIMS_INVALID")
        task_type = task.get("type")
        if task_type == "multiple-choice":
            options = task.get("options")
            if not isinstance(options, list) or not 2 <= len(options) <= 10:
                raise ValueError("STUDY_PACK_OPTIONS_INVALID")
            normalized = [_text(option, maximum=1000) for option in options]
            answer = _text(task.get("answerKey"), maximum=1000)
            if len(set(normalized)) != len(normalized) or answer not in normalized:
                raise ValueError("STUDY_PACK_ANSWER_KEY_INVALID")
        elif task_type == "spatial":
            x = _unit(task.get("targetX"))
            y = _unit(task.get("targetY"))
            width = _unit(task.get("targetWidth"), positive=True)
            height = _unit(task.get("targetHeight"), positive=True)
            tolerance = _unit(task.get("tolerance"), positive=True)
            if x + width > 1 or y + height > 1 or tolerance > 0.5:
                raise ValueError("STUDY_PACK_COORDINATE_INVALID")
        else:
            raise ValueError("STUDY_PACK_TASK_TYPE_UNSUPPORTED")

    checksum = content_checksum(definition)
    if definition.get("checksum") != checksum:
        raise ValueError("STUDY_PACK_CHECKSUM_INVALID")
    preview = definition.get("facultyPreview")
    if not isinstance(preview, dict) or preview.get("packChecksum") != checksum:
        raise ValueError("STUDY_PACK_PREVIEW_REQUIRED")
    if preview.get("previewVersion") != PREVIEW_VERSION:
        raise ValueError("STUDY_PACK_PREVIEW_REQUIRED")
    _text(preview.get("reviewedAt"), maximum=40)
    return checksum


def prepare_study_pack(definition: dict[str, Any]) -> tuple[dict[str, Any], str]:
    """Validate an unpublished core using the exact publication contract."""
    core = {
        key: value for key, value in definition.items() if key not in {"checksum", "facultyPreview"}
    }
    checksum = content_checksum(core)
    candidate = {
        **core,
        "checksum": checksum,
        "facultyPreview": {
            "packChecksum": checksum,
            "previewVersion": PREVIEW_VERSION,
            "reviewedAt": "validation-only",
        },
    }
    validate_study_pack(candidate)
    return core, checksum


def learner_definition(definition: dict[str, Any]) -> dict[str, Any]:
    tasks: list[dict[str, Any]] = []
    for source in definition["tasks"]:
        task = {
            key: source[key]
            for key in ("id", "type", "slideId", "prompt", "options", "hints", "claimIds")
            if key in source
        }
        tasks.append(task)
    result = {
        "schema": definition["schema"],
        "packKey": definition["packKey"],
        "version": definition["version"],
        "title": definition["title"],
        "languages": definition["languages"],
        "slides": [
            {
                "viewerSlideId": slide["viewerSlideId"],
                "displayName": slide["displayName"],
                "tileSource": f"/api/v1/study/slides/{slide['viewerSlideId']}/tiles/slide.dzi",
                **(
                    {
                        "evidenceBundleSha256": slide["evidenceBundleSha256"],
                        "evidenceUrl": (
                            f"/api/v1/study/slides/{slide['viewerSlideId']}/evidence/"
                            f"{slide['evidenceBundleSha256']}"
                        ),
                    }
                    if definition["schema"] == SCHEMA_V2
                    else {}
                ),
            }
            for slide in definition["slides"]
        ],
        "tasks": tasks,
    }
    if definition["schema"] == SCHEMA_V2:
        result["knowledgePackChecksum"] = definition["knowledgePackChecksum"]
        result["knowledgePackUrl"] = (
            f"/api/v1/study/knowledge/{definition['knowledgePackChecksum']}"
        )
    return result


def score_task(task: dict[str, Any], submission: dict[str, Any]) -> bool:
    if task["type"] == "multiple-choice":
        selected = submission.get("selectedOption")
        return isinstance(selected, str) and selected == task["answerKey"]
    x = submission.get("x")
    y = submission.get("y")
    if (
        isinstance(x, bool)
        or isinstance(y, bool)
        or not isinstance(x, (int, float))
        or not isinstance(y, (int, float))
    ):
        raise ValueError("STUDY_SUBMISSION_INVALID")
    center_x = task["targetX"] + task["targetWidth"] / 2
    center_y = task["targetY"] + task["targetHeight"] / 2
    tolerance = task["tolerance"]
    return bool(abs(float(x) - center_x) <= tolerance and abs(float(y) - center_y) <= tolerance)


def normalized_spatial_error(task: dict[str, Any], submission: dict[str, Any]) -> float | None:
    if task.get("type") != "spatial":
        return None
    x = submission.get("x")
    y = submission.get("y")
    if not isinstance(x, (int, float)) or isinstance(x, bool):
        return None
    if not isinstance(y, (int, float)) or isinstance(y, bool):
        return None
    center_x = float(task["targetX"]) + float(task["targetWidth"]) / 2
    center_y = float(task["targetY"]) + float(task["targetHeight"]) / 2
    distance = math.hypot(float(x) - center_x, float(y) - center_y)
    return min(1.0, distance / math.sqrt(2))
