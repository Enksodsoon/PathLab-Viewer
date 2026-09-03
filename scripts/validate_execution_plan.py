from __future__ import annotations

import re
import sys
from collections import Counter
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
PHASE_FILES = {
    0: "PHASE_0_CANONICAL_AND_FREEDOM.md",
    1: "PHASE_1_RESIDENT_FOUNDATION.md",
    2: "PHASE_2_TRUST_AND_OPERATIONS.md",
    3: "PHASE_3_IMAGING.md",
    4: "PHASE_4_LEARNING.md",
    5: "PHASE_5_SPECIALIST_CONTEXTS.md",
    6: "PHASE_6_PORTABILITY_AND_RECOVERY.md",
    7: "PHASE_7_PREQUALIFICATION.md",
    8: "PHASE_8_PRODUCTION.md",
}

TASK_ID_TEXT = r"P[0-8]-(?:T|G)\d+[A-Z]?"
TASK_ID = re.compile(rf"(?<![A-Z0-9])({TASK_ID_TEXT})(?![A-Z0-9-])")
EXACT_TASK_ID = re.compile(rf"{TASK_ID_TEXT}")
TASK_LIKE = re.compile(r"(?<![A-Z0-9])P\d+-(?:T|G)[A-Za-z0-9-]+")
HEADING_DEFINITION = re.compile(rf"(?m)^## ({TASK_ID_TEXT})(?![A-Z0-9-])")
TABLE_DEFINITION = re.compile(
    rf"(?m)^\|\s*`({TASK_ID_TEXT})`\s*\|"
)
SECOND_LEVEL_HEADING = re.compile(r"(?m)^## ")
MARKDOWN_LINK = re.compile(r"(?<!!)\[[^\]]+\]\(([^)]+)\)")
CARD_FIELD = re.compile(
    r"(?ms)^- \*\*(Outcome|Depends on|External prerequisites|Read first|"
    r"Change surface|Implement|Prove|Stop/hand off|Unlocks):\*\*[ \t]*"
    r"(.*?)(?=^- \*\*(?:Outcome|Depends on|External prerequisites|Read first|"
    r"Change surface|Implement|Prove|Stop/hand off|Unlocks):\*\*|\Z)"
)
TASK_RANGE = re.compile(
    rf"(?<![A-Z0-9])({TASK_ID_TEXT})(?![A-Z0-9-])\s*[–—]\s*"
    rf"(?<![A-Z0-9])({TASK_ID_TEXT})(?![A-Z0-9-])"
)
TASK_PARTS = re.compile(
    r"P(?P<phase>[0-8])-(?P<kind>T|G)(?P<number>\d+)(?P<suffix>[A-Z]?)"
)
DEPENDENCY_STATE = re.compile(
    r"\b(?:PLANNED|IMPLEMENTED|CHECKED_LOCAL|CHECKED_PROTECTED|MERGED|DEPLOYED|"
    r"PILOT_VALIDATED|PRODUCTION_QUALIFIED|ACTIVATED|ACTIVATION_SUSPENDED|"
    r"FROZEN|READY|RUNNING|ACTIVE|COMPLETED|SUCCESS|PARTIAL|NEGATIVE|"
    r"NOT_EVALUABLE|SELECTED)\b",
    re.IGNORECASE,
)

REQUIRED_CARD_FIELDS = (
    "Outcome",
    "Depends on",
    "Read first",
    "Change surface",
    "Implement",
    "Prove",
    "Stop/hand off",
    "Unlocks",
)

VAGUE_DEPENDENCY_PATTERNS = (
    re.compile(r"\ball contexts\b", re.IGNORECASE),
    re.compile(r"\ball Phase \d", re.IGNORECASE),
    re.compile(r"\bevery earlier Phase\b", re.IGNORECASE),
    re.compile(r"\bowning Phase\b", re.IGNORECASE),
    re.compile(r"\bgovernance status tasks\b", re.IGNORECASE),
    re.compile(r"\bcomplete deployment/workload inventory\b", re.IGNORECASE),
    re.compile(r"\ball P7 gate results\b", re.IGNORECASE),
    re.compile(r"\bPhase 2 key/protection contracts\b", re.IGNORECASE),
    re.compile(r"\bTeacher Authoring logical database/migration\b", re.IGNORECASE),
    re.compile(r"\bcurrent complete portability build\b", re.IGNORECASE),
    re.compile(r"\bhealthy backup/restore\b", re.IGNORECASE),
    re.compile(r"\bevery required phase/campaign result\b", re.IGNORECASE),
    re.compile(r"\bterminal preflight results\b", re.IGNORECASE),
    re.compile(r"\bapplicable child response-kind contracts\b", re.IGNORECASE),
    re.compile(r"\bcanonical Edge evidence schemas\b", re.IGNORECASE),
    re.compile(r"\bcurrent deployment/evidence\b", re.IGNORECASE),
    re.compile(r"\ball evidence current\b", re.IGNORECASE),
)

# These conditions are deliberately not task dependencies.  A task card must
# declare them in ``External prerequisites`` so a fresh chat records the
# accountable party, validity, subject fingerprint, and immutable receipt
# separately from repository lifecycle evidence.
EXTERNAL_PREREQUISITE_PATTERNS = (
    re.compile(r"\b(?:human|accountable) authority\b", re.IGNORECASE),
    re.compile(r"\b(?:rights?|relicensing|lawful)\b", re.IGNORECASE),
    re.compile(r"\b(?:hardware|storage|fleet|media|network)\b", re.IGNORECASE),
    re.compile(r"\b(?:resources?|operators?|keepers?|reviewers?)\b", re.IGNORECASE),
    re.compile(r"\b(?:physical )?clients?\b", re.IGNORECASE),
    re.compile(r"\bassistive technolog(?:y|ies)\b", re.IGNORECASE),
    re.compile(r"\b(?:corpus|dataset snapshot|fixtures?)\b", re.IGNORECASE),
    re.compile(r"\b(?:tool|implementation) access\b", re.IGNORECASE),
    re.compile(r"\b(?:invoice|provider statement)s?\b", re.IGNORECASE),
    re.compile(r"\bnamed (?:people|persons?)\b", re.IGNORECASE),
)

EXTERNAL_PREREQUISITE_KINDS = {
    "HUMAN_AUTHORITY",
    "RIGHTS",
    "HARDWARE",
    "DATA_OR_CORPUS",
    "NETWORK_IDENTITY",
    "TOOL_OR_IMPLEMENTATION",
    "COST_OR_ALLOWANCE",
}

EXACT_TASK_WITH_STATE = re.compile(
    rf"(?P<task>{TASK_ID_TEXT})=(?P<state>"
    r"PLANNED|IMPLEMENTED|CHECKED_LOCAL|CHECKED_PROTECTED|MERGED|DEPLOYED|"
    r"PILOT_VALIDATED|PRODUCTION_QUALIFIED|ACTIVATED|ACTIVATION_SUSPENDED|"
    r"FROZEN|READY|RUNNING|ACTIVE|COMPLETED|SUCCESS|PARTIAL|NEGATIVE|"
    r"NOT_EVALUABLE|SELECTED)"
)
TITLE_HEAD = re.compile(
    r"\b(?:[A-Z][A-Za-z0-9]*(?:[ /-][A-Z][A-Za-z0-9]*)*)[ ](?:Receipt|State)\b"
)
EXPLICIT_INTERNAL_HEADS = {
    "Backup Freshness State",
    "CampaignCheckpointReceipt",
    "G38 Cleanup/Result Receipt",
}

# Dependency prose is a deliberately small grammar of binding qualifiers.  New
# prose must be made machine-readable or explicitly added here in review; an
# arbitrary backtick span is never a suppression mechanism.
ALLOWED_DEPENDENCY_WORDS = {
    "a", "account", "active", "admission", "admitted", "ai", "all", "an",
    "and", "are", "atomically", "backup", "be", "bound", "by", "caliper",
    "campaign", "campaign-bound", "candidate", "case", "chains", "check",
    "child", "cleanup", "clinical", "closure", "complete", "complete-context",
    "completed", "contract", "coordinated", "covering", "credential",
    "cross-profile", "current", "cursor", "cutover", "cycle", "declared",
    "dependency", "deployment-selection", "dicom-object", "dicomweb", "edge",
    "eqa", "every", "exact", "exact-subject", "exactly", "fallback", "fhir",
    "fingerprint", "for", "freshness", "from", "frozen", "full", "g38",
    "gate", "generation", "head", "heads", "here", "host", "identical",
    "immutable", "implementation", "import", "in", "including", "inferred",
    "inputs", "instant", "integration", "interop", "interval", "its",
    "journey", "ledger", "linked", "lti", "manifest", "manifests", "matching",
    "may", "merged", "must", "named", "no", "node-set", "none", "ome-zarr",
    "on", "one", "oneroster", "operated-campaign", "operation", "or", "parent",
    "persistence", "phase", "phase-candidate", "pilot", "plus", "prerequisite",
    "prerequisites", "primary", "profile", "proposal", "protected", "protection",
    "qti", "receipt", "receipts", "release", "release-bound", "requires",
    "research", "result", "results", "roots", "run", "runtime", "same",
    "schedule", "schema", "second", "set", "snapshot", "stack", "state",
    "tariff", "teacher", "terminal", "the", "their", "through", "to", "tuple",
    "unchanged", "unnamed", "use", "valid", "waived", "where", "with",
    "within", "workload", "wsi",
}


def _numbered(prefix: str, first: int, last: int) -> set[str]:
    return {f"{prefix}{number:02d}" for number in range(first, last + 1)}


EXPECTED_IDS = {
    0: _numbered("P0-T", 1, 12)
    | {
        "P0-T01A", "P0-T02A", "P0-T03A", "P0-T05A", "P0-T09A", "P0-T10A",
        "P0-T10B", "P0-T10C", "P0-T10D", "P0-T10E", "P0-T10F",
    },
    1: _numbered("P1-T", 1, 25) | {"P1-T11A", "P1-T22A"},
    2: _numbered("P2-T", 1, 27)
    | {"P2-T02A", "P2-T02B", "P2-T16A", "P2-T18A", "P2-T18B", "P2-T18C"},
    3: _numbered("P3-T", 1, 18),
    4: _numbered("P4-T", 0, 30)
    | {"P4-T06A", "P4-T12A", "P4-T20A", "P4-T20B"}
    | {f"P4-T13{suffix}" for suffix in "ABCDEFGHI"}
    | {"P4-T19A"}
    | {f"P4-T22{suffix}" for suffix in "ABCDEFGHI"}
    | {"P4-T29A", "P4-T29B", "P4-T29C"},
    5: _numbered("P5-T", 0, 40)
    | {"P5-T01A"}
    | {f"P5-T02{suffix}" for suffix in "ABCDEFGHIJ"}
    | {"P5-T04A", "P5-T04B"}
    | {f"P5-T09{suffix}" for suffix in "ABCDEFGHIJKLMNOPQRS"}
    | {f"P5-T15{suffix}" for suffix in "ABCDE"}
    | {"P5-T20A", "P5-T20B", "P5-T20C", "P5-T25A", "P5-T27A"}
    | {"P5-T25B"}
    | {f"P5-T26{suffix}" for suffix in "ABCDEFGHIJKLMNOPQ"}
    | {"P5-T30A", "P5-T30B", "P5-T30C"}
    | {f"P5-T39{suffix}" for suffix in "ABCDE"},
    6: _numbered("P6-T", 1, 36)
    | {"P6-T24A"}
    | {f"P6-T34{suffix}" for suffix in "ABCD"},
    7: _numbered("P7-T", 1, 20)
    | _numbered("P7-G", 1, 20)
    | {"P7-G09A", "P7-G09B", "P7-G12A", "P7-G12B"}
    | {"P7-G14A", "P7-G14B"}
    | {f"P7-G15{suffix}" for suffix in "ABCD"},
    8: _numbered("P8-T", 1, 12) | {"P8-T12A"},
}

REFERENCE_FILES = (
    "DEPENDENCY_WAVES.md",
    "TASK_INDEX.md",
    "TRACEABILITY.md",
)


def _card_blocks(text: str) -> list[tuple[str, str]]:
    headings = list(SECOND_LEVEL_HEADING.finditer(text))
    blocks: list[tuple[str, str]] = []
    for index, heading in enumerate(headings):
        definition = HEADING_DEFINITION.match(text, heading.start())
        if definition is None:
            continue
        end = headings[index + 1].start() if index + 1 < len(headings) else len(text)
        blocks.append((definition.group(1), text[heading.start() : end]))
    return blocks


def _link_target(raw_target: str) -> str | None:
    target = raw_target.strip()
    if target.startswith("<") and ">" in target:
        target = target[1 : target.index(">")]
    else:
        target = target.split(maxsplit=1)[0]
    if not target or target.startswith(("#", "http://", "https://", "mailto:")):
        return None
    return target.split("#", maxsplit=1)[0]


def _task_sort_key(identifier: str) -> tuple[int, str, int, int]:
    match = TASK_PARTS.fullmatch(identifier)
    if match is None:  # pragma: no cover - callers only pass validated task ids
        raise ValueError(f"invalid task id: {identifier}")
    suffix = match.group("suffix")
    return (
        int(match.group("phase")),
        match.group("kind"),
        int(match.group("number")),
        0 if not suffix else ord(suffix) - ord("A") + 1,
    )


def _parse_card_fields(block: str) -> dict[str, str]:
    matches = list(CARD_FIELD.finditer(block))
    names = [match.group(1) for match in matches]
    expected = list(REQUIRED_CARD_FIELDS)
    if "External prerequisites" in names:
        expected.insert(2, "External prerequisites")
    if names != expected:
        raise ValueError(
            "card fields must occur exactly once in canonical order; "
            f"found {names!r}, expected {expected!r}"
        )
    fields = {match.group(1): match.group(2).strip() for match in matches}
    empty = [name for name in names if not fields[name]]
    if empty:
        raise ValueError(f"empty card fields: {', '.join(empty)}")
    implement = fields["Implement"]
    if re.fullmatch(r"(?i)none\s*;?", implement):
        raise ValueError("Implement 'none;' must name a non-empty bounded operation")
    if re.match(r"(?i)^none\b", implement) and not re.match(
        r"(?is)^none;\s*\S", implement
    ):
        raise ValueError("non-product Implement must use 'none;' plus an operation")
    return fields


EXTERNAL_ENTRY = re.compile(
    r"label=(?P<label>[A-Z0-9][A-Z0-9-]*); "
    r"kind=(?P<kind>[A-Z_]+); "
    r"requires=(?P<requires>[^;|\r\n]+); "
    r"accountable=(?P<accountable>[^;|\r\n]+); "
    r"validity=(?P<validity>[^;|\r\n]+); "
    r"evidence=(?P<evidence>(?:[A-Za-z0-9]+(?:-[A-Za-z0-9]+)+|"
    r"(?:signed immutable )?[A-Z][A-Za-z0-9 -]*(?:Receipt|Manifest)\.?))"
)


def _parse_external_prerequisites(value: str) -> list[dict[str, str]]:
    entries: list[dict[str, str]] = []
    labels: set[str] = set()
    for number, raw_entry in enumerate(value.split(" | "), start=1):
        match = EXTERNAL_ENTRY.fullmatch(raw_entry)
        if match is None:
            raise ValueError(
                f"external prerequisite {number} does not match the exact ordered "
                "six-key grammar"
            )
        entry = match.groupdict()
        if any(value != value.strip() for value in entry.values()):
            raise ValueError(f"external prerequisite {number} has padded values")
        if entry["kind"] not in EXTERNAL_PREREQUISITE_KINDS:
            raise ValueError(
                f"external prerequisite {number} has invalid kind: {entry['kind']}"
            )
        if entry["label"] in labels:
            raise ValueError(f"duplicate external prerequisite label: {entry['label']}")
        labels.add(entry["label"])
        entries.append(entry)
    return entries


def _expand_task_range(
    start: str, end: str, definitions: set[str]
) -> set[str]:
    start_key = _task_sort_key(start)
    end_key = _task_sort_key(end)
    if start_key[:2] != end_key[:2]:
        raise ValueError(f"cross-phase or cross-kind task range: {start}–{end}")
    if start_key > end_key:
        raise ValueError(f"reversed task range: {start}–{end}")
    if start not in definitions or end not in definitions:
        raise ValueError(f"undefined task range endpoint: {start}–{end}")
    return {
        identifier
        for identifier in definitions
        if _task_sort_key(identifier)[:2] == start_key[:2]
        and start_key <= _task_sort_key(identifier) <= end_key
    }


def _dependency_ids(expression: str, definitions: set[str]) -> set[str]:
    normalized = expression.replace("`", "")
    malformed = [
        token
        for token in TASK_LIKE.findall(normalized)
        if EXACT_TASK_ID.fullmatch(token) is None
    ]
    if malformed:
        raise ValueError(f"malformed task token(s): {', '.join(sorted(set(malformed)))}")
    dependencies = set(TASK_ID.findall(normalized))
    for start, end in TASK_RANGE.findall(normalized):
        dependencies.update(_expand_task_range(start, end, definitions))
    return dependencies


def _normalized_head(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.casefold())


def _registered_internal_heads(root: Path) -> set[str]:
    path = root / "docs" / "architecture" / "RECEIPT_SCHEMA_REGISTRY.md"
    if not path.is_file():
        return set()
    heads: set[str] = set()
    for bold in re.findall(r"\*\*([^*]+)\*\*", path.read_text(encoding="utf-8")):
        match = re.search(r"^(.+?\b(?:Receipt|State))\b", bold)
        if match:
            heads.add(_normalized_head(match.group(1)))
    return heads


def _strip_known_dependency_atoms(
    expression: str,
    *,
    definitions: set[str],
    declared_external_labels: set[str],
    registered_heads: set[str],
) -> tuple[str, set[str]]:
    used_external: set[str] = set()

    def strip_code(match: re.Match[str]) -> str:
        token = match.group(1)
        exact_task = EXACT_TASK_ID.fullmatch(token)
        task_with_state = EXACT_TASK_WITH_STATE.fullmatch(token)
        if exact_task or task_with_state:
            task = token if exact_task else task_with_state.group("task")
            if task not in definitions:
                raise ValueError(f"undefined dependency task token: `{token}`")
            return " "
        if re.fullmatch(r"=(?:[A-Z][A-Z0-9_]*)", token):
            if DEPENDENCY_STATE.fullmatch(token[1:]) is None:
                raise ValueError(f"invalid grouped task disposition: `{token}`")
            return " "
        if DEPENDENCY_STATE.fullmatch(token):
            return " "
        if token in declared_external_labels:
            used_external.add(token)
            return " "
        head_match = re.fullmatch(r"(.+?(?:Receipt|State))(?:\(([A-Z_]+)\))?", token)
        if head_match:
            head = _normalized_head(head_match.group(1))
            if head not in registered_heads and head not in {
                _normalized_head(value) for value in EXPLICIT_INTERNAL_HEADS
            }:
                raise ValueError(f"unregistered internal receipt/state head: `{token}`")
            if head_match.group(2) is not None and not head_match.group(2):
                raise ValueError(f"empty internal head disposition: `{token}`")
            return " "
        raise ValueError(f"unknown dependency code token: `{token}`")

    prose = re.sub(r"`([^`]+)`", strip_code, expression)
    for head in sorted(EXPLICIT_INTERNAL_HEADS, key=len, reverse=True):
        prose = re.sub(re.escape(head), " ", prose)
    for match in list(TITLE_HEAD.finditer(prose)):
        normalized = _normalized_head(match.group(0))
        if normalized not in registered_heads and normalized not in {
            _normalized_head(value) for value in EXPLICIT_INTERNAL_HEADS
        }:
            raise ValueError(
                f"unregistered internal receipt/state head: {match.group(0)}"
            )
        prose = prose.replace(match.group(0), " ")
    prose = TASK_RANGE.sub(" ", prose)
    prose = TASK_ID.sub(" ", prose)
    prose = DEPENDENCY_STATE.sub(" ", prose)
    words = {word.casefold() for word in re.findall(r"[A-Za-z][A-Za-z0-9_-]*", prose)}
    unknown = sorted(words - ALLOWED_DEPENDENCY_WORDS)
    if unknown:
        raise ValueError(f"uncaught dependency prose: {', '.join(unknown)}")
    return prose, used_external


def _validate_dependency_states(expression: str) -> None:
    """Require a disposition for every exact task token/range group.

    A suffix disposition applies to all unassigned references since the prior
    disposition.  Only ``active``/``completed`` and ``<state> from`` are prefix
    forms.  This rejects ambiguous constructs such as ``A MERGED and B``.
    """

    normalized = expression.replace("`", "")
    for clause in normalized.split(";"):
        task_matches = list(TASK_ID.finditer(clause))
        if not task_matches:
            continue
        assigned: set[int] = set()
        compact_spans: list[tuple[int, int]] = []
        for compact in EXACT_TASK_WITH_STATE.finditer(clause):
            compact_spans.append(compact.span())
            for index, task in enumerate(task_matches):
                if compact.start() <= task.start() and task.end() <= compact.end():
                    assigned.add(index)
        states = [
            state
            for state in DEPENDENCY_STATE.finditer(clause)
            if not any(start <= state.start() < end for start, end in compact_spans)
        ]
        previous_state_end = 0
        for state_index, state in enumerate(states):
            state_name = state.group(0).upper()
            next_state_start = (
                states[state_index + 1].start()
                if state_index + 1 < len(states)
                else len(clause)
            )
            after = clause[state.end() : next_state_start]
            preceding_candidates = [
                index
                for index, task in enumerate(task_matches)
                if previous_state_end <= task.start() < state.start()
                and index not in assigned
            ]
            prefix_word = state_name in {"ACTIVE", "COMPLETED"}
            is_prefix = (
                prefix_word and not preceding_candidates
            ) or bool(
                re.match(r"\s+(?:results?\s+)?from\b", after, re.IGNORECASE)
            )
            if is_prefix:
                candidates = [
                    index
                    for index, task in enumerate(task_matches)
                    if state.end() <= task.start() < next_state_start
                ]
            else:
                candidates = preceding_candidates
            assigned.update(candidates)
            previous_state_end = state.end()
        missing = [
            task.group(0)
            for index, task in enumerate(task_matches)
            if index not in assigned
        ]
        if missing:
            raise ValueError(
                "task dependency lacks an unambiguous required state/result: "
                + ", ".join(missing)
            )


def _ancestor_external_labels(
    task: str,
    dependency_graph: dict[str, set[str]],
    external_declarations: dict[str, set[str]],
) -> set[str]:
    labels = set(external_declarations.get(task, set()))
    pending = list(dependency_graph.get(task, set()))
    seen: set[str] = set()
    while pending:
        dependency = pending.pop()
        if dependency in seen:
            continue
        seen.add(dependency)
        labels.update(external_declarations.get(dependency, set()))
        pending.extend(dependency_graph.get(dependency, set()))
    return labels


def _find_cycle(graph: dict[str, set[str]]) -> list[str] | None:
    visited: set[str] = set()
    active: set[str] = set()
    trail: list[str] = []

    def visit(node: str) -> list[str] | None:
        if node in active:
            return trail[trail.index(node) :] + [node]
        if node in visited:
            return None
        visited.add(node)
        active.add(node)
        trail.append(node)
        for dependency in sorted(graph.get(node, set())):
            cycle = visit(dependency)
            if cycle is not None:
                return cycle
        trail.pop()
        active.remove(node)
        return None

    for node in sorted(graph):
        cycle = visit(node)
        if cycle is not None:
            return cycle
    return None


def _table_first_column(
    text: str, start_heading: str | None, end_heading: str
) -> set[str]:
    if start_heading is not None:
        text = text.split(start_heading, maxsplit=1)[1]
    text = text.split(end_heading, maxsplit=1)[0]
    names: set[str] = set()
    for line in text.splitlines():
        if not line.startswith("|"):
            continue
        first = line.strip("|").split("|", maxsplit=1)[0].strip()
        if not first or first.startswith("---") or first in {
            "Capability",
            "Feature-matrix capability",
        }:
            continue
        names.add(first)
    return names


RELATIVE_TASK_ID = re.compile(r"(?<!P[0-8]-)\b([TG]\d+[A-Z]?)\b")
RELATIVE_TASK_RANGE = re.compile(
    r"(?<!P[0-8]-)\b([TG]\d+[A-Z]?)\b\s*[–—]\s*"
    r"(?<!P[0-8]-)\b([TG]\d+[A-Z]?)\b"
)


def _parse_index_ids(cell: str, phase: int, definitions: set[str]) -> set[str]:
    normalized = cell.replace("`", "")
    identifiers = set(TASK_ID.findall(normalized))
    for start, end in TASK_RANGE.findall(normalized):
        identifiers.update(_expand_task_range(start, end, definitions))
    for start, end in RELATIVE_TASK_RANGE.findall(normalized):
        identifiers.update(
            _expand_task_range(f"P{phase}-{start}", f"P{phase}-{end}", definitions)
        )
    for relative in RELATIVE_TASK_ID.findall(normalized):
        identifiers.add(f"P{phase}-{relative}")
    malformed = sorted(identifier for identifier in identifiers if identifier not in definitions)
    if malformed:
        raise ValueError(f"undefined or malformed indexed IDs: {', '.join(malformed)}")
    return identifiers


def validate_execution_plan(root: Path = REPOSITORY_ROOT) -> tuple[int, dict[int, int]]:
    execution_root = root / "docs" / "execution"
    errors: list[str] = []
    definitions: dict[str, Path] = {}
    counts: Counter[int] = Counter()
    card_fields: dict[str, dict[str, str]] = {}
    external_declarations: dict[str, set[str]] = {}

    for phase, filename in PHASE_FILES.items():
        path = execution_root / filename
        if not path.is_file():
            errors.append(f"missing phase file: {path.relative_to(root)}")
            continue
        text = path.read_text(encoding="utf-8")
        table_ids = TABLE_DEFINITION.findall(text)
        if table_ids:
            errors.append(
                f"{filename}: compressed table definitions are not one-chat cards: "
                f"{', '.join(sorted(table_ids))}"
            )
        ids = HEADING_DEFINITION.findall(text) + table_ids
        found = set(ids)
        if len(found) != len(ids):
            duplicates = sorted(
                identifier
                for identifier, count in Counter(ids).items()
                if count > 1
            )
            errors.append(f"{filename}: duplicate definitions: {', '.join(duplicates)}")
        missing = sorted(EXPECTED_IDS[phase] - found)
        unexpected = sorted(found - EXPECTED_IDS[phase])
        if missing:
            errors.append(f"{filename}: missing expected IDs: {', '.join(missing)}")
        if unexpected:
            errors.append(f"{filename}: unexpected IDs: {', '.join(unexpected)}")
        counts[phase] = len(found)
        for identifier in found:
            if identifier in definitions:
                errors.append(
                    f"duplicate definition across files: {identifier} in "
                    f"{definitions[identifier].name} and {filename}"
                )
            definitions[identifier] = path
        for identifier, block in _card_blocks(text):
            try:
                fields = _parse_card_fields(block)
            except ValueError as error:
                errors.append(
                    f"{filename}: {identifier} invalid card contract: {error}"
                )
                continue
            card_fields[identifier] = fields
            external_declarations[identifier] = set()
            if "External prerequisites" in fields:
                try:
                    entries = _parse_external_prerequisites(
                        fields["External prerequisites"]
                    )
                except ValueError as error:
                    errors.append(
                        f"{filename}: {identifier} invalid External prerequisites: "
                        f"{error}"
                    )
                else:
                    external_declarations[identifier] = {
                        entry["label"] for entry in entries
                    }

    definition_ids = set(definitions)
    dependency_graph: dict[str, set[str]] = {}
    used_external_labels: dict[str, set[str]] = {}
    all_external_labels = (
        set().union(*external_declarations.values())
        if external_declarations
        else set()
    )
    registered_heads = _registered_internal_heads(root)
    for identifier, fields in card_fields.items():
        expression = fields["Depends on"]
        if re.match(r"(?i)^none\b", expression):
            if not re.fullmatch(r"(?i)none[.]?", expression.strip()):
                errors.append(
                    f"{definitions[identifier].name}: {identifier} must keep a no-"
                    "dependency expression exactly 'none'; move procedure text to "
                    "Implement"
                )
            dependency_graph[identifier] = set()
            used_external_labels[identifier] = set()
            continue
        if not TASK_ID.search(expression):
            errors.append(
                f"{definitions[identifier].name}: {identifier} dependency has no "
                "stable task ID"
            )
        for vague in VAGUE_DEPENDENCY_PATTERNS:
            if vague.search(expression):
                errors.append(
                    f"{definitions[identifier].name}: {identifier} has vague dependency: "
                    f"{vague.pattern}"
                )
        try:
            dependency_prose, used_labels = _strip_known_dependency_atoms(
                expression,
                definitions=definition_ids,
                declared_external_labels=all_external_labels,
                registered_heads=registered_heads,
            )
            used_external_labels[identifier] = used_labels
        except ValueError as error:
            errors.append(
                f"{definitions[identifier].name}: {identifier} invalid dependency "
                f"grammar: {error}"
            )
            used_external_labels[identifier] = set()
            dependency_prose = expression
        for external in EXTERNAL_PREREQUISITE_PATTERNS:
            if external.search(dependency_prose):
                errors.append(
                    f"{definitions[identifier].name}: {identifier} puts an external "
                    f"prerequisite in Depends on: {external.pattern}"
                )
        try:
            _validate_dependency_states(expression)
        except ValueError as error:
            errors.append(
                f"{definitions[identifier].name}: {identifier} invalid dependency "
                f"states: {error}"
            )
        try:
            dependencies = _dependency_ids(expression, definition_ids)
        except ValueError as error:
            errors.append(
                f"{definitions[identifier].name}: {identifier} invalid dependency "
                f"range/token: {error}"
            )
            dependencies = set()
        undefined_dependencies = sorted(dependencies - definition_ids)
        if undefined_dependencies:
            errors.append(
                f"{definitions[identifier].name}: {identifier} has undefined dependencies: "
                f"{', '.join(undefined_dependencies)}"
            )
        if identifier in dependencies:
            errors.append(f"{definitions[identifier].name}: {identifier} depends on itself")
        dependency_graph[identifier] = dependencies & definition_ids

    cycle = _find_cycle(dependency_graph)
    if cycle is not None:
        errors.append(f"dependency cycle: {' -> '.join(cycle)}")

    for identifier, labels in used_external_labels.items():
        unavailable = sorted(
            labels
            - _ancestor_external_labels(
                identifier, dependency_graph, external_declarations
            )
        )
        if unavailable:
            errors.append(
                f"{definitions[identifier].name}: {identifier} external receipt "
                "label is not declared on the card or dependency ancestry: "
                f"{', '.join(unavailable)}"
            )

    reference_paths = [execution_root / filename for filename in PHASE_FILES.values()]
    reference_paths.extend(execution_root / filename for filename in REFERENCE_FILES)
    for path in reference_paths:
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8")
        undefined = sorted(set(TASK_ID.findall(text)) - set(definitions))
        if undefined:
            errors.append(f"{path.name}: undefined task references: {', '.join(undefined)}")

    for path in sorted(execution_root.glob("*.md")):
        text = path.read_text(encoding="utf-8")
        for raw_target in MARKDOWN_LINK.findall(text):
            target = _link_target(raw_target)
            if target is None:
                continue
            resolved = (path.parent / target).resolve()
            if not resolved.is_file():
                errors.append(f"{path.name}: broken local link: {target}")

    expected_total = sum(len(identifiers) for identifiers in EXPECTED_IDS.values())
    if len(definitions) != expected_total:
        errors.append(
            f"defined task total is {len(definitions)}; expected {expected_total}"
        )

    index_path = execution_root / "TASK_INDEX.md"
    if index_path.is_file():
        index_lines = index_path.read_text(encoding="utf-8").splitlines()
        indexed_counts: dict[int, int] = {}
        indexed_ids: dict[int, set[str]] = {}
        indexed_total: int | None = None
        indexed_task_packages: int | None = None
        indexed_gate_packages: int | None = None
        for line in index_lines:
            columns = [column.strip() for column in line.strip("|").split("|")]
            if len(columns) < 3:
                continue
            if columns[0].isdigit():
                try:
                    phase = int(columns[0])
                    indexed_counts[phase] = int(columns[2])
                    indexed_ids[phase] = _parse_index_ids(
                        columns[1], phase, definition_ids
                    )
                except ValueError:
                    errors.append(f"TASK_INDEX.md: invalid phase count row: {line}")
            elif columns[0] == "**Total**":
                total_text = columns[2].replace("*", "")
                try:
                    indexed_total = int(total_text)
                except ValueError:
                    errors.append(f"TASK_INDEX.md: invalid total row: {line}")
                decomposition = re.fullmatch(
                    r"(\d+) task packages plus (\d+) exact-release "
                    r"gate/start/monitor/closure packages",
                    columns[1],
                )
                if decomposition is None:
                    errors.append(
                        "TASK_INDEX.md: total decomposition must use the exact "
                        "task/gate package grammar"
                    )
                else:
                    indexed_task_packages = int(decomposition.group(1))
                    indexed_gate_packages = int(decomposition.group(2))
        actual_counts = dict(sorted(counts.items()))
        if indexed_counts != actual_counts:
            errors.append(
                f"TASK_INDEX.md: phase counts {indexed_counts} do not match {actual_counts}"
            )
        for phase, expected in EXPECTED_IDS.items():
            indexed = indexed_ids.get(phase, set())
            if indexed != expected:
                missing = sorted(expected - indexed, key=_task_sort_key)
                unexpected = sorted(indexed - expected, key=_task_sort_key)
                errors.append(
                    f"TASK_INDEX.md: Phase {phase} ID set mismatch; missing "
                    f"{missing}, unexpected {unexpected}"
                )
        if indexed_total != expected_total:
            errors.append(
                f"TASK_INDEX.md: total {indexed_total} does not match {expected_total}"
            )
        expected_gate_packages = sum(
            1 for identifier in definition_ids if "-G" in identifier
        )
        expected_task_packages = expected_total - expected_gate_packages
        if (indexed_task_packages, indexed_gate_packages) != (
            expected_task_packages,
            expected_gate_packages,
        ):
            errors.append(
                "TASK_INDEX.md: decomposition "
                f"{indexed_task_packages}+{indexed_gate_packages} does not match "
                f"{expected_task_packages}+{expected_gate_packages}={expected_total}"
            )

    feature_path = root / "docs" / "architecture" / "FEATURE_COMPLETION_MATRIX.md"
    traceability_path = execution_root / "TRACEABILITY.md"
    if feature_path.is_file() and traceability_path.is_file():
        traceability_text = traceability_path.read_text(encoding="utf-8")
        feature_names = _table_first_column(
            feature_path.read_text(encoding="utf-8"),
            None,
            "## Completion semantics",
        )
        traced_names = _table_first_column(
            traceability_text,
            "## Feature Completion Matrix coverage",
            "## Bounded-context coverage",
        )
        missing_traceability = sorted(feature_names - traced_names)
        if missing_traceability:
            errors.append(
                "TRACEABILITY.md: missing Feature Completion Matrix rows: "
                f"{', '.join(missing_traceability)}"
            )
        traced_task_ids = _dependency_ids(traceability_text, definition_ids)
        missing_task_traceability = sorted(
            definition_ids - traced_task_ids, key=_task_sort_key
        )
        if missing_task_traceability:
            errors.append(
                "TRACEABILITY.md: task packages missing from traceability: "
                f"{', '.join(missing_task_traceability)}"
            )

    if errors:
        raise ValueError("\n".join(errors))
    return len(definitions), dict(sorted(counts.items()))


def main() -> int:
    try:
        total, counts = validate_execution_plan()
    except (OSError, UnicodeError, ValueError) as error:
        print(f"Execution plan invalid:\n{error}", file=sys.stderr)
        return 1
    phase_summary = ", ".join(f"P{phase}={count}" for phase, count in counts.items())
    print(f"Execution plan valid: {total} packages ({phase_summary})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
