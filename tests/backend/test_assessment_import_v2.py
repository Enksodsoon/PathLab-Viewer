from copy import deepcopy

from test_assessment_contract_v2 import v2_document
from wsi_viewer.assessment_import_v2 import clone_complete_sections, import_individual_items


def test_individual_v2_import_refreshes_ids_keys_and_strips_routes() -> None:
    source = v2_document()
    destination = deepcopy(source)
    destination["sections"][0]["items"] = []  # type: ignore[index]
    document, imported = import_individual_items(
        destination, source, {"item-pattern"}
    )
    item = imported[0]
    assert item["id"] != "item-pattern"
    assert {option["id"] for option in item["options"]}.isdisjoint(
        {"option-lepidic", "option-solid"}
    )
    assert set(item["answerKey"]["optionIds"]) <= {
        option["id"] for option in item["options"]
    }
    assert "routing" not in item
    assert document["sections"][0]["items"] == [item]  # type: ignore[index]


def test_complete_section_clone_remaps_only_safe_internal_routes() -> None:
    sections = v2_document()["sections"]
    cloned = clone_complete_sections(sections)  # type: ignore[arg-type]
    source_ids = {section["id"] for section in sections}  # type: ignore[union-attr]
    cloned_ids = {section["id"] for section in cloned}
    assert source_ids.isdisjoint(cloned_ids)
    route = cloned[0]["items"][0]["routing"]
    assert route["defaultSectionId"] in cloned_ids
    assert route["rules"][0]["goToSectionId"] in cloned_ids
    assert route["rules"][0]["when"]["optionId"] in {
        option["id"] for option in cloned[0]["items"][0]["options"]
    }
