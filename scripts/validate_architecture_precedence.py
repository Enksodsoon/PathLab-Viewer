"""Validate architecture precedence inventory, banners, links, and references."""

from __future__ import annotations

import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REGISTER_PATH = Path("docs/architecture/ARCHITECTURE_PRECEDENCE.md")
VALID_STATUSES = {
    "CANONICAL",
    "SUPPORTING_CONTRACT",
    "CANONICAL_EXECUTION_PLAN",
    "BASELINE_ONLY",
    "MIGRATION_INPUT_ONLY",
    "SUPERSEDED",
    "EVIDENCE_ONLY",
    "NAVIGATION_ONLY",
}
NON_AUTHORITATIVE = {"BASELINE_ONLY", "MIGRATION_INPUT_ONLY", "SUPERSEDED"}
EXTERNAL_BANNERS = {
    Path("apps/web/DESIGN.md"): "BASELINE_ONLY",
    Path("docs/classroom/IMPLEMENTATION.md"): "BASELINE_ONLY",
    Path("docs/superpowers/specs/2026-08-14-pathlab-free-classroom-design.md"): (
        "SUPERSEDED"
    ),
    Path("docs/superpowers/plans/2026-08-14-pathlab-free-classroom.md"): "SUPERSEDED",
}
ROW_PATTERN = re.compile(
    r"^\| `(?P<path>docs/architecture/[^`]+)` "
    r"\| `(?P<status>[A-Z_]+)` \| (?P<controller>.+) \|$"
)
LINK_PATTERN = re.compile(r"\[[^\]]+\]\((?P<target>[^)]+)\)")
NORMATIVE_PATTERN = re.compile(
    r"\b(must|shall|required|approved|authoritative|authority|control|controls|"
    r"controlled|read first)\b",
    re.IGNORECASE,
)
QUALIFIER_PATTERN = re.compile(
    r"\b(baseline(?:-only)?|migration[- ]input(?:-only)?|legacy|superseded|"
    r"non-authoritative)\b",
    re.IGNORECASE,
)
CONTROLLER_PATTERN = re.compile(
    r"Architecture Precedence Register|Final Production Endpoint|"
    r"FINAL_PRODUCTION_ENDPOINT|SQLITE_TO_POSTGRESQL|ROLE_APPROVAL_MATRIX|"
    r"Production Qualification|Zero-Cash|\bADR(?:s)?\b|\bcontext\b",
    re.IGNORECASE,
)


def parse_inventory(register_text: str) -> list[tuple[str, str, str]]:
    """Return architecture inventory rows from the register."""

    rows: list[tuple[str, str, str]] = []
    for line in register_text.splitlines():
        match = ROW_PATTERN.match(line)
        if match:
            rows.append(
                (match["path"], match["status"], match["controller"].strip())
            )
    return rows


def validate_inventory(
    register_text: str, actual_paths: set[str]
) -> tuple[list[str], dict[str, str]]:
    """Check complete, unique inventory coverage and return path statuses."""

    errors: list[str] = []
    rows = parse_inventory(register_text)
    counts = Counter(path for path, _, _ in rows)
    duplicates = sorted(path for path, count in counts.items() if count != 1)
    if duplicates:
        errors.append(f"duplicate architecture inventory rows: {', '.join(duplicates)}")

    registered = set(counts)
    missing = sorted(actual_paths - registered)
    extra = sorted(registered - actual_paths)
    if missing:
        errors.append(f"missing architecture inventory rows: {', '.join(missing)}")
    if extra:
        errors.append(f"unknown architecture inventory rows: {', '.join(extra)}")

    statuses: dict[str, str] = {}
    for path, status, controller in rows:
        if status not in VALID_STATUSES:
            errors.append(f"invalid status {status!r} for {path}")
        if not controller or controller == "-":
            errors.append(f"missing conflict controller for {path}")
        statuses[path] = status
    return errors, statuses


def validate_banner(path: Path, status: str, text: str) -> list[str]:
    """Require a visible exact status and register link near the document title."""

    prefix = "\n".join(text.splitlines()[:12])
    errors: list[str] = []
    marker = f"Precedence status: `{status}`"
    if marker not in prefix:
        errors.append(f"{path.as_posix()}: missing early {status} precedence banner")
    if "ARCHITECTURE_PRECEDENCE.md" not in prefix:
        errors.append(f"{path.as_posix()}: banner does not link precedence register")
    return errors


def validate_markdown_links(root: Path, register_text: str) -> list[str]:
    """Check every local Markdown target in the precedence register."""

    errors: list[str] = []
    register = root / REGISTER_PATH
    for match in LINK_PATTERN.finditer(register_text):
        target = match["target"].split("#", 1)[0]
        if not target or "://" in target or target.startswith("mailto:"):
            continue
        resolved = (register.parent / target).resolve()
        if not resolved.exists():
            errors.append(f"{REGISTER_PATH.as_posix()}: broken local link {target}")
    return errors


def stale_reference_errors(
    path: Path, text: str, legacy_names: set[str]
) -> list[str]:
    """Reject normative use of a legacy plan without a qualifier and controller."""

    errors: list[str] = []
    lines = text.splitlines()
    for index, line in enumerate(lines):
        mentioned = sorted(name for name in legacy_names if name in line)
        if not mentioned:
            continue
        start = max(0, index - 2)
        end = min(len(lines), index + 3)
        window = " ".join(lines[start:end])
        if not NORMATIVE_PATTERN.search(window):
            continue
        if QUALIFIER_PATTERN.search(window) and CONTROLLER_PATTERN.search(window):
            continue
        errors.append(
            f"{path.as_posix()}:{index + 1}: stale normative reference to "
            f"{', '.join(mentioned)} lacks both legacy status and canonical controller"
        )
    return errors


def planning_markdown_paths(root: Path) -> list[Path]:
    """Return the repository-wide Markdown planning/reference surface."""

    paths = [root / "README.md", root / "CONTEXT-MAP.md", root / "apps/web/DESIGN.md"]
    paths.extend((root / "docs").rglob("*.md"))
    return sorted({path for path in paths if path.is_file()})


def validate_repository(root: Path = ROOT) -> list[str]:
    """Validate the repository's full precedence contract."""

    errors: list[str] = []
    register = root / REGISTER_PATH
    if not register.is_file():
        return [f"missing {REGISTER_PATH.as_posix()}"]
    register_text = register.read_text(encoding="utf-8")

    architecture_dir = root / "docs/architecture"
    actual_paths = {
        path.relative_to(root).as_posix()
        for path in architecture_dir.iterdir()
        if path.is_file()
        and path.suffix.lower() in {".md", ".docx"}
        and path != register
    }
    inventory_errors, statuses = validate_inventory(register_text, actual_paths)
    errors.extend(inventory_errors)
    errors.extend(validate_markdown_links(root, register_text))

    banner_paths = {
        Path(path): status
        for path, status in statuses.items()
        if status in NON_AUTHORITATIVE and path.endswith(".md")
    }
    banner_paths.update(EXTERNAL_BANNERS)
    for relative_path, status in sorted(banner_paths.items(), key=lambda item: str(item[0])):
        document = root / relative_path
        if not document.is_file():
            errors.append(f"missing bannered planning document {relative_path.as_posix()}")
            continue
        errors.extend(
            validate_banner(
                relative_path, status, document.read_text(encoding="utf-8")
            )
        )

    legacy_names = {Path(path).name for path in banner_paths}
    excluded = {register.resolve()}
    excluded.update((root / path).resolve() for path in banner_paths)
    for markdown_path in planning_markdown_paths(root):
        if markdown_path.resolve() in excluded:
            continue
        errors.extend(
            stale_reference_errors(
                markdown_path.relative_to(root),
                markdown_path.read_text(encoding="utf-8"),
                legacy_names,
            )
        )
    return errors


def main() -> int:
    """Run validation and print a compact audit result."""

    errors = validate_repository()
    if errors:
        print("Architecture precedence validation FAILED:")
        for error in errors:
            print(f"- {error}")
        return 1

    register_text = (ROOT / REGISTER_PATH).read_text(encoding="utf-8")
    rows = parse_inventory(register_text)
    legacy_count = sum(status in NON_AUTHORITATIVE for _, status, _ in rows)
    print(
        "Architecture precedence validation PASS: "
        f"{len(rows)} architecture documents classified; "
        f"{legacy_count} non-authoritative dispositions bannered; "
        "links and normative references resolved."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
