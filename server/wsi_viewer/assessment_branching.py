from __future__ import annotations

import hashlib
from typing import Any


def deterministic_order(item_ids: list[str], seed: str) -> list[str]:
    return sorted(
        item_ids,
        key=lambda item_id: (
            hashlib.sha256(f"{seed}:{item_id}".encode()).hexdigest(),
            item_id,
        ),
    )


def _condition_matches(condition: dict[str, Any], response: dict[str, Any] | None) -> bool:
    operator = condition.get("operator")
    if operator == "answered":
        return bool(response)
    if operator == "not-answered":
        return not response
    if response is None:
        return False
    selected = response.get("optionId")
    selected_many = response.get("optionIds", [])
    expected = condition.get("optionId", condition.get("value"))
    if operator == "equals":
        return selected == expected or response.get("value") == expected
    if operator == "contains":
        return expected in selected_many
    if operator == "greater-or-equal":
        try:
            actual = response.get("value")
            expected_value = condition.get("value")
            if actual is None or expected_value is None:
                return False
            return float(actual) >= float(expected_value)
        except (TypeError, ValueError):
            return False
    return False


def _section_destination(
    section: dict[str, Any], responses: dict[str, dict[str, Any]]
) -> str | None:
    default: str | None = None
    for item in section.get("items", []):
        routing = item.get("routing")
        if not isinstance(routing, dict):
            continue
        for rule in routing.get("rules", []):
            if _condition_matches(rule.get("when", {}), responses.get(item["id"])):
                return str(rule["goToSectionId"])
        if routing.get("defaultSectionId") is not None:
            default = str(routing["defaultSectionId"])
    return default


def reachable_section_ids(
    document: dict[str, Any], responses: dict[str, dict[str, Any]]
) -> list[str]:
    sections = document.get("sections", [])
    if not sections:
        return []
    by_id = {section["id"]: section for section in sections}
    index_by_id = {section["id"]: index for index, section in enumerate(sections)}
    reachable: list[str] = []
    current = str(sections[0]["id"])
    visited: set[str] = set()
    while current in by_id and current not in visited:
        visited.add(current)
        reachable.append(current)
        section = by_id[current]
        destination = _section_destination(section, responses)
        if destination is not None:
            current = destination
            continue
        next_index = index_by_id[current] + 1
        if next_index >= len(sections):
            break
        current = str(sections[next_index]["id"])
    return reachable


def active_responses(
    document: dict[str, Any], responses: dict[str, dict[str, Any]]
) -> dict[str, dict[str, Any]]:
    reachable = set(reachable_section_ids(document, responses))
    active_item_ids = {
        item["id"]
        for section in document.get("sections", [])
        if section["id"] in reachable
        for item in section.get("items", [])
    }
    return {
        item_id: response for item_id, response in responses.items() if item_id in active_item_ids
    }
