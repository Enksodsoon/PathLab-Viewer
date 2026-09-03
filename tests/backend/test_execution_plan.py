import pytest

from scripts.validate_execution_plan import (
    _ancestor_external_labels,
    _dependency_ids,
    _parse_card_fields,
    _parse_external_prerequisites,
    _parse_index_ids,
    _strip_known_dependency_atoms,
    _validate_dependency_states,
    validate_execution_plan,
)


def test_execution_plan_is_complete_and_internally_consistent() -> None:
    total, phase_counts = validate_execution_plan()

    assert total == 371
    assert phase_counts == {
        0: 23,
        1: 27,
        2: 33,
        3: 18,
        4: 57,
        5: 109,
        6: 41,
        7: 50,
        8: 13,
    }


def test_card_fields_are_anchored_unique_nonempty_and_ordered() -> None:
    valid = """## P0-T01 — sample

- **Outcome:** one result
- **Depends on:** none.
- **Read first:** one contract
- **Change surface:** one path
- **Implement:** none; perform the bounded audit.
- **Prove:** one check
- **Stop/hand off:** one stop
- **Unlocks:** P0-T02
"""
    assert _parse_card_fields(valid)["Outcome"] == "one result"

    duplicate = valid.replace(
        "- **Read first:** one contract",
        "- **Outcome:** duplicate\n- **Read first:** one contract",
    )
    with pytest.raises(ValueError, match="exactly once in canonical order"):
        _parse_card_fields(duplicate)

    empty = valid.replace("- **Prove:** one check", "- **Prove:**   ")
    with pytest.raises(ValueError, match="empty card fields"):
        _parse_card_fields(empty)

    empty_none_operation = valid.replace(
        "none; perform the bounded audit.", "none;"
    )
    with pytest.raises(ValueError, match="non-empty bounded operation"):
        _parse_card_fields(empty_none_operation)


def test_external_prerequisite_grammar_is_exact_and_labels_are_unique() -> None:
    entry = (
        "label=EP-TEST-HOST; kind=HARDWARE; requires=AVAILABLE; "
        "accountable=Infrastructure Owner; validity=exact test window; "
        "evidence=Signed Host Receipt"
    )
    assert _parse_external_prerequisites(entry)[0]["label"] == "EP-TEST-HOST"

    with pytest.raises(ValueError, match="six-key grammar"):
        _parse_external_prerequisites(entry.replace("; kind=", "; unknown=x; kind="))
    with pytest.raises(ValueError, match="six-key grammar"):
        _parse_external_prerequisites(entry + " trailing")
    with pytest.raises(ValueError, match="duplicate external prerequisite label"):
        _parse_external_prerequisites(entry + " | " + entry)


def test_dependency_tokens_ranges_and_group_states_are_bounded() -> None:
    definitions = {
        "P0-T01",
        "P0-T01A",
        "P0-T02",
        "P0-G01",
        "P1-T01",
    }
    assert _dependency_ids("`P0-T01`–`P0-T02` `MERGED`", definitions) == {
        "P0-T01",
        "P0-T01A",
        "P0-T02",
    }

    for expression in (
        "`P0-T01AA` `MERGED`",
        "`P0-T02`–`P0-T01` `MERGED`",
        "`P0-T01`–`P0-G01` `MERGED`",
        "`P0-T01`–`P1-T01` `MERGED`",
    ):
        with pytest.raises(ValueError):
            _dependency_ids(expression, definitions)

    _validate_dependency_states("`P0-T01` and `P0-T02` `MERGED`")
    with pytest.raises(ValueError, match="lacks an unambiguous"):
        _validate_dependency_states("`P0-T01` `MERGED` and `P0-T02`")


def test_unknown_dependency_code_and_prose_cannot_hide_in_backticks() -> None:
    with pytest.raises(ValueError, match="unknown dependency code token"):
        _strip_known_dependency_atoms(
            "`P0-T01` `MERGED` and `lawful corpus available`",
            definitions={"P0-T01"},
            declared_external_labels=set(),
            registered_heads=set(),
        )
    with pytest.raises(ValueError, match="unregistered internal receipt/state head"):
        _strip_known_dependency_atoms(
            "`P0-T01` `MERGED` with `BogusReceipt(READY)`",
            definitions={"P0-T01"},
            declared_external_labels=set(),
            registered_heads=set(),
        )
    with pytest.raises(ValueError, match="uncaught dependency prose"):
        _strip_known_dependency_atoms(
            "`P0-T01` `MERGED` after arbitrary approval",
            definitions={"P0-T01"},
            declared_external_labels=set(),
            registered_heads=set(),
        )


def test_external_receipt_must_be_declared_on_self_or_dependency_ancestry() -> None:
    graph = {"P0-T03": {"P0-T02"}, "P0-T02": {"P0-T01"}, "P0-T01": set()}
    declarations = {"P0-T01": {"EP-ROOT"}, "P0-T02": set(), "P0-T03": set()}
    ancestry = _ancestor_external_labels("P0-T03", graph, declarations)
    assert ancestry == {"EP-ROOT"}
    _, used = _strip_known_dependency_atoms(
        "`P0-T02` `MERGED` with `EP-ROOT` and `EP-MISSING` receipt heads",
        definitions=set(graph),
        declared_external_labels={"EP-ROOT", "EP-MISSING"},
        registered_heads=set(),
    )
    assert used - ancestry == {"EP-MISSING"}


def test_index_parser_expands_full_ranges_and_phase_relative_shorthand() -> None:
    definitions = {"P8-T01", "P8-T02", "P8-T12A"}
    assert _parse_index_ids("`P8-T01`–`P8-T02`; `T12A`", 8, definitions) == definitions
