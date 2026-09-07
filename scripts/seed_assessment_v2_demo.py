"""Install the editable, non-sensitive Teacher Studio v2 demonstration draft."""

from __future__ import annotations

import argparse
import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from wsi_viewer.assessment_contract_v2 import compile_assessment_v2

DEFAULT_DRAFT_ID = "0624f05e-2a7c-4a8f-ba40-d4ddc8cc6be4"


def _choice(item_id: str, prompt: str, labels: list[str], *, kind: str = "multiple-choice") -> dict:
    options = [
        {"id": f"{item_id}-option-{index}", "label": label} for index, label in enumerate(labels, 1)
    ]
    return {
        "id": item_id,
        "type": kind,
        "prompt": prompt,
        "points": "1",
        "required": True,
        "options": options,
        "answerKey": {"optionIds": [options[0]["id"]]},
    }


def demo_document(slide_id: str | None = None) -> dict:
    gate = _choice(
        "demo-gate",
        "Which pattern should open the focused review section?",
        ["Solid growth", "Lepidic growth"],
        kind="dropdown",
    )
    gate["routing"] = {
        "rules": [
            {
                "when": {"operator": "equals", "optionId": "demo-gate-option-1"},
                "goToSectionId": "section-review",
            }
        ],
        "defaultSectionId": "section-application",
    }
    diagnostic = {
        "id": "demo-field",
        "type": "diagnostic-field",
        "prompt": "Mark the teaching focus and enter the best diagnosis.",
        "points": "2",
        "required": True,
        "helpText": "Use the privacy-passed synthetic slide thumbnail as orientation.",
        "answerKey": {
            "regions": [{"kind": "rectangle", "x": 0.3, "y": 0.25, "width": 0.3, "height": 0.3}],
            "diagnoses": ["pulmonary adenocarcinoma"],
        },
        "education": {
            "objective": "Recognize invasion",
            "competency": "Morphologic diagnosis",
            "difficulty": "intermediate",
            "tags": ["thoracic", "synthetic"],
        },
    }
    if slide_id:
        diagnostic.update(
            {
                "slideId": slide_id,
                "media": {
                    "kind": "slide-thumbnail",
                    "slideId": slide_id,
                    "alt": "Synthetic thoracic pathology teaching slide",
                },
            }
        )
    ratings = [
        {
            "id": f"rating-{style}",
            "type": "rating",
            "prompt": f"Rate confidence using {style}.",
            "points": "0",
            "required": True,
            "rating": {"min": 1, "max": 5, "style": style},
            "validation": {"required": True, "message": "Choose a confidence rating."},
        }
        for style in ("numbers", "stars", "hearts", "thumbs-up")
    ]
    return {
        "schema": "pathlab.assessment/2",
        "title": "Teacher Studio Essentials v2 — Editable Demo",
        "description": (
            "Non-sensitive synthetic teaching data demonstrating sections, routing, "
            "validation, manual grading, release controls, and every approved response family."
        ),
        "presentation": {"preset": "standard", "showProgress": True, "showSectionTitles": True},
        "settings": {"mode": "formative", "shuffleQuestions": True},
        "release": {
            "timing": "manual",
            "showScore": True,
            "showAnswers": False,
            "showAuthoredFeedback": False,
            "showManualFeedback": True,
            "showAnnotations": False,
        },
        "sections": [
            {
                "id": "section-screening",
                "title": "Screening and routing",
                "description": "A dropdown routes learners at section exit.",
                "items": [
                    gate,
                    _choice(
                        "demo-mc",
                        "Which finding best supports invasion?",
                        ["Desmoplastic stroma", "Orderly ciliated epithelium"],
                    ),
                    _choice(
                        "demo-checks",
                        "Select the compatible findings.",
                        ["Irregular glands", "Intracellular mucin", "Mature cartilage only"],
                        kind="checkboxes",
                    ),
                ],
            },
            {
                "id": "section-review",
                "title": "Focused review",
                "description": "Shown only when the routing condition is met.",
                "items": [
                    {
                        "id": "review-info",
                        "type": "section-information",
                        "prompt": "Review gland shape and stromal response before continuing.",
                    },
                    {
                        "id": "demo-short",
                        "type": "short-answer",
                        "prompt": "Name the predominant growth pattern.",
                        "points": "1",
                        "required": True,
                        "answerKey": {"variants": ["acinar", "acinar pattern"]},
                        "validation": {
                            "minimumLength": 3,
                            "maximumLength": 80,
                            "message": "Enter a concise pattern name.",
                        },
                    },
                ],
            },
            {
                "id": "section-application",
                "title": "Application and manual review",
                "items": [
                    diagnostic,
                    {
                        "id": "demo-paragraph",
                        "type": "paragraph",
                        "prompt": "Write a concise integrated teaching report.",
                        "points": "3",
                        "required": True,
                        "manual": True,
                        "teacherNotes": "Grade for morphology, interpretation, and clarity.",
                        "validation": {
                            "minimumLength": 20,
                            "maximumLength": 1000,
                            "message": "Write at least 20 characters.",
                        },
                        "feedback": {
                            "correct": "Strong integration.",
                            "incorrect": "Revisit morphology and lineage.",
                        },
                    },
                ],
            },
            {"id": "section-reflection", "title": "Confidence reflection", "items": ratings},
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", type=Path, default=Path("var/pathlab.sqlite3"))
    parser.add_argument("--draft-id", default=DEFAULT_DRAFT_ID)
    args = parser.parse_args()
    connection = sqlite3.connect(args.database.resolve())
    connection.row_factory = sqlite3.Row
    slide = connection.execute(
        "SELECT id FROM slides WHERE privacy_status = 'passed' "
        "AND render_mode = 'static_dzi' AND trashed_at IS NULL "
        "ORDER BY updated_at DESC LIMIT 1"
    ).fetchone()
    document = demo_document(slide["id"] if slide else None)
    compile_assessment_v2(document)
    now = datetime.now(UTC).replace(tzinfo=None).isoformat(sep=" ")
    with connection:
        updated = connection.execute(
            "UPDATE assessment_drafts SET title = ?, document = ?, "
            "revision = revision + 1, updated_at = ? WHERE id = ?",
            (document["title"], json.dumps(document, separators=(",", ":")), now, args.draft_id),
        ).rowcount
    if updated != 1:
        raise SystemExit(f"Draft {args.draft_id} was not found")
    print(
        f"Teacher Studio v2 demo ready: {args.draft_id}; "
        f"sections={len(document['sections'])}; slide={'yes' if slide else 'no'}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
