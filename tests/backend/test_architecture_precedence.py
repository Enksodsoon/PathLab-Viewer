from __future__ import annotations

from pathlib import Path

from scripts.validate_architecture_precedence import (
    ROOT,
    stale_reference_errors,
    validate_banner,
    validate_inventory,
    validate_repository,
)


def test_repository_architecture_precedence_is_complete() -> None:
    assert validate_repository(ROOT) == []


def test_inventory_rejects_missing_document() -> None:
    register = (
        "| Document | Status | Controlling canonical source for conflicts |\n"
        "|---|---|---|\n"
        "| `docs/architecture/ONE.md` | `CANONICAL` | accepted ADR |\n"
    )
    errors, _ = validate_inventory(
        register, {"docs/architecture/ONE.md", "docs/architecture/TWO.md"}
    )
    assert errors == [
        "missing architecture inventory rows: docs/architecture/TWO.md"
    ]


def test_inventory_rejects_invalid_status_and_empty_controller() -> None:
    register = (
        "| `docs/architecture/ONE.md` | `CURRENTISH` | - |\n"
    )
    errors, _ = validate_inventory(register, {"docs/architecture/ONE.md"})
    assert "invalid status 'CURRENTISH' for docs/architecture/ONE.md" in errors
    assert "missing conflict controller for docs/architecture/ONE.md" in errors


def test_legacy_document_requires_exact_early_banner() -> None:
    errors = validate_banner(
        Path("docs/architecture/OLD.md"),
        "SUPERSEDED",
        "# Old plan\n\nApproved for implementation.\n",
    )
    assert errors == [
        "docs/architecture/OLD.md: missing early SUPERSEDED precedence banner",
        "docs/architecture/OLD.md: banner does not link precedence register",
    ]


def test_stale_normative_reference_is_rejected() -> None:
    errors = stale_reference_errors(
        Path("docs/plan.md"),
        "PASSWORD_RECOVERY.md is the required production authority.",
        {"PASSWORD_RECOVERY.md"},
    )
    assert len(errors) == 1
    assert "stale normative reference" in errors[0]


def test_qualified_legacy_reference_is_accepted() -> None:
    errors = stale_reference_errors(
        Path("docs/plan.md"),
        (
            "PASSWORD_RECOVERY.md is required only as legacy migration input; "
            "the Final Production Endpoint and ADRs control conflicts."
        ),
        {"PASSWORD_RECOVERY.md"},
    )
    assert errors == []
