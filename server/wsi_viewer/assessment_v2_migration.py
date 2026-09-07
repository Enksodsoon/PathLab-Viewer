from __future__ import annotations

import hashlib
from copy import deepcopy
from typing import Any

from .assessment_contract_v2 import V2_SCHEMA


def migrate_v1_document(document: dict[str, Any], source_id: str) -> dict[str, Any]:
    section_id = f"section-{hashlib.sha256(source_id.encode()).hexdigest()[:24]}"
    items: list[dict[str, Any]] = []
    for raw in document.get("items", []):
        item = deepcopy(raw)
        if item.get("type") == "information":
            item["type"] = "section-information"
        items.append(item)
    return {
        "schema": V2_SCHEMA,
        "title": document.get("title", "Untitled assessment"),
        "description": document.get("description", ""),
        "sections": [
            {
                "id": section_id,
                "title": "Assessment",
                "description": "",
                "items": items,
            }
        ],
        "presentation": {
            "preset": "standard",
            "showProgress": True,
            "showSectionTitles": True,
        },
        "settings": deepcopy(document.get("settings", {})),
        "release": {
            "showScore": True,
            "showAnswers": False,
            "showAuthoredFeedback": False,
            "showManualFeedback": False,
        },
    }
