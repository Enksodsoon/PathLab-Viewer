from __future__ import annotations

import secrets
from copy import deepcopy
from typing import Any


def document_items(document: dict[str, Any]) -> list[dict[str, Any]]:
    if document.get("schema") == "pathlab.assessment/2":
        return [
            item
            for section in document.get("sections", [])
            for item in section.get("items", [])
        ]
    return list(document.get("items", []))


def fresh_item(source: dict[str, Any], *, keep_routing: bool = False) -> dict[str, Any]:
    item = deepcopy(source)
    item["id"] = secrets.token_hex(16)
    option_ids: dict[str, str] = {}
    for option in item.get("options", []):
        old_id = str(option.get("id", ""))
        option["id"] = secrets.token_hex(16)
        option_ids[old_id] = option["id"]
    answer = item.get("answerKey")
    if isinstance(answer, dict) and isinstance(answer.get("optionIds"), list):
        answer["optionIds"] = [
            option_ids[value] for value in answer["optionIds"] if value in option_ids
        ]
    if keep_routing and isinstance(item.get("routing"), dict):
        for rule in item["routing"].get("rules", []):
            condition = rule.get("when", {})
            option_id = condition.get("optionId")
            if option_id in option_ids:
                condition["optionId"] = option_ids[option_id]
    else:
        item.pop("routing", None)
    return item


def import_individual_items(
    destination: dict[str, Any], source: dict[str, Any], requested_ids: set[str]
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    selected = [
        fresh_item(item)
        for item in document_items(source)
        if str(item.get("id")) in requested_ids
    ]
    if len(selected) != len(requested_ids):
        raise KeyError("ASSESSMENT_ITEM_NOT_FOUND")
    document = deepcopy(destination)
    if document.get("schema") == "pathlab.assessment/2":
        sections = document.setdefault("sections", [])
        if not sections:
            sections.append(
                {
                    "id": secrets.token_hex(16),
                    "title": "Imported questions",
                    "description": "",
                    "items": [],
                }
            )
        sections[0]["items"] = [*sections[0].get("items", []), *selected]
    else:
        document["items"] = [*document.get("items", []), *selected]
    return document, selected


def clone_complete_sections(sections: list[dict[str, Any]]) -> list[dict[str, Any]]:
    section_ids = {str(section["id"]): secrets.token_hex(16) for section in sections}
    result: list[dict[str, Any]] = []
    for source in sections:
        section = deepcopy(source)
        section["id"] = section_ids[str(source["id"])]
        section["items"] = [fresh_item(item, keep_routing=True) for item in source.get("items", [])]
        for item in section["items"]:
            routing = item.get("routing")
            if not isinstance(routing, dict):
                continue
            if routing.get("defaultSectionId") in section_ids:
                routing["defaultSectionId"] = section_ids[routing["defaultSectionId"]]
            else:
                routing.pop("defaultSectionId", None)
            routing["rules"] = [
                {**rule, "goToSectionId": section_ids[rule["goToSectionId"]]}
                for rule in routing.get("rules", [])
                if rule.get("goToSectionId") in section_ids
            ]
        result.append(section)
    return result
