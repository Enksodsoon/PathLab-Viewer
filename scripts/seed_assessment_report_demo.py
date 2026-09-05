"""Expand and stress the local synthetic assessment report.

This utility is intentionally narrow: it refuses to touch an administration unless
its settings identify it as a synthetic fixture. It also takes an online SQLite
backup before changing the fixture and is idempotent once the mixed-format items
have been added.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import sys
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from wsi_viewer.assessment_contract import compile_assessment


DEFAULT_DRAFT_ID = "0624f05e-2a7c-4a8f-ba40-d4ddc8cc6be4"


DEMO_ITEMS = [
    {
        "id": "q7",
        "type": "checkboxes",
        "prompt": "Select all findings that support invasive pulmonary adenocarcinoma.",
        "points": "2",
        "options": [
            {"id": "q7a", "label": "Irregular malignant glands"},
            {"id": "q7b", "label": "Desmoplastic stroma"},
            {"id": "q7c", "label": "Orderly ciliated epithelium"},
            {"id": "q7d", "label": "Mature cartilage only"},
        ],
        "answerKey": {"optionIds": ["q7a", "q7b"]},
        "scoring": {"partialCredit": True},
    },
    {
        "id": "q8",
        "type": "short-answer",
        "prompt": "Name the predominant histologic pattern shown.",
        "points": "1",
        "answerKey": {"variants": ["acinar", "acinar pattern", "acinar adenocarcinoma"]},
    },
    {
        "id": "q9",
        "type": "short-answer",
        "prompt": "State one additional stain you would request and why.",
        "points": "1",
        "manual": True,
    },
    {
        "id": "q10",
        "type": "diagnostic-field",
        "prompt": "On the H&E whole-slide image, mark the desmoplastic invasive gland-forming focus and enter the most likely diagnosis.",
        "points": "2",
        "answerKey": {
            "regions": [{"kind": "rectangle", "x": 0.28, "y": 0.22, "width": 0.34, "height": 0.38}],
            "diagnoses": ["pulmonary adenocarcinoma", "lung adenocarcinoma"],
        },
        "scoring": {"pointTolerance": 0.06, "rectangleIou": 0.25},
    },
    {
        "id": "q11",
        "type": "information",
        "prompt": "Reference: compare the marked focus with the adjacent preserved alveolar architecture.",
    },
    {
        "id": "q12",
        "type": "paragraph",
        "prompt": "Integrate the morphology and ancillary findings into a concise final report.",
        "points": "2",
        "manual": True,
    },
]


SHORT_ANSWERS = [
    "Acinar", "Acinar pattern", "acinar adenocarcinoma", "Papillary", "Acinar",
    "Acinar pattern", "Solid", "acinar", "Lepidic", "Acinar", "Papillary", "Acinar pattern",
]
MANUAL_SHORT = [
    "TTF-1 to support pulmonary origin.", "Napsin A for glandular differentiation.",
    "p40 to exclude squamous differentiation.", "ALK because targeted therapy may be relevant.",
    "TTF-1 and Napsin A as a focused panel.", "Mucin stain to confirm intracellular mucin.",
    "CK7 with TTF-1 to support lung origin.", "PD-L1 for treatment planning.",
    "EGFR molecular testing after confirmation.", "Napsin A because the morphology is gland-forming.",
    "p40 and synaptophysin to assess the differential.", "TTF-1 to support primary lung adenocarcinoma.",
]
PARAGRAPHS = [
    "Invasive acinar adenocarcinoma with mucin production and desmoplastic stromal response.",
    "Pulmonary adenocarcinoma, acinar predominant, supported by TTF-1 and Napsin A.",
    "Malignant gland-forming epithelial neoplasm consistent with primary lung adenocarcinoma.",
    "Invasive adenocarcinoma with irregular glands infiltrating fibrotic stroma.",
    "Acinar predominant pulmonary adenocarcinoma; correlate with molecular testing.",
    "Primary lung adenocarcinoma with mucinous differentiation and stromal invasion.",
    "Invasive glandular carcinoma, favor pulmonary adenocarcinoma.",
    "Pulmonary adenocarcinoma showing acinar architecture and desmoplasia.",
    "Adenocarcinoma of lung origin; no small-cell morphology is identified.",
    "Invasive acinar adenocarcinoma with cytologic atypia and prominent nucleoli.",
    "Primary pulmonary adenocarcinoma, acinar pattern, pending ancillary confirmation.",
    "Lung adenocarcinoma with infiltrative glands and intracellular mucin.",
]

FIRST_NAMES = (
    "Amina", "Anong", "Arthit", "Boonmee", "Chanya", "Dara", "Eka", "Farah", "Hana", "Intan",
    "Jirawat", "Kanya", "Lalita", "Malee", "Narin", "Nicha", "Omar", "Pattra", "Ploy", "Qasim",
    "Rina", "Siriporn", "Somchai", "Thanawat", "Uma", "Virote", "Wiyada", "Xavier", "Yasmin", "Zain",
)
LAST_NAMES = (
    "Akarapong", "Boonchai", "Charoen", "Decha", "Faruqi", "Gunawan", "Halim", "Ismail", "Jindakul", "Kittisak",
    "Lim", "Mahmood", "Narong", "Osman", "Phromdee", "Prasert", "Rahman", "Raksakul", "SaeLim", "Sirisuk",
)


def _base_response(item_id: str, index: int) -> dict:
    if item_id in {"q1", "q2", "q3", "q4", "q5"}:
        question = int(item_id[1:])
        correct = (index * (question + 2) + question) % 11 >= (question % 4) + 2
        return {"optionId": f"{item_id}{'a' if correct else 'b'}"}
    if item_id == "q6":
        return {"text": PARAGRAPHS[(index * 3) % len(PARAGRAPHS)]}
    return _response_payload(item_id, index)


def _base_earned(item_id: str, index: int) -> Decimal | None:
    if item_id in {"q1", "q2", "q3", "q4", "q5"}:
        return Decimal("1") if _base_response(item_id, index)["optionId"].endswith("a") else Decimal("0")
    if item_id == "q6":
        return None
    return _earned(item_id, index)


def _json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _decode(value: object) -> dict:
    return json.loads(value) if isinstance(value, str) else dict(value or {})


def _response_payload(item_id: str, index: int) -> dict:
    if item_id == "q7":
        band = index % 12
        choices = (["q7a", "q7b"] if band < 7 else ["q7a"] if band < 10 else ["q7c"])
        return {"optionIds": choices}
    if item_id == "q8":
        return {"text": SHORT_ANSWERS[index % len(SHORT_ANSWERS)]}
    if item_id == "q9":
        return {"text": MANUAL_SHORT[index % len(MANUAL_SHORT)]}
    if item_id == "q10":
        band = index % 12
        if band < 6:
            return {"selection": {"kind": "point", "x": 0.36 + band * 0.025, "y": 0.31 + (band % 3) * 0.035}, "diagnosis": "Pulmonary adenocarcinoma"}
        if band < 9:
            return {"selection": {"kind": "point", "x": 0.42, "y": 0.38}, "diagnosis": "Squamous cell carcinoma"}
        return {"selection": {"kind": "point", "x": 0.82, "y": 0.78}, "diagnosis": "Squamous cell carcinoma"}
    return {"text": PARAGRAPHS[index % len(PARAGRAPHS)]}


def _earned(item_id: str, index: int) -> Decimal | None:
    if item_id == "q7":
        band = index % 12
        return Decimal("2") if band < 7 else Decimal("1") if band < 10 else Decimal("0")
    if item_id == "q8":
        return Decimal("1") if index % 12 in {0, 1, 2, 4, 5, 7, 9, 11} else Decimal("0")
    if item_id == "q10":
        band = index % 12
        return Decimal("2") if band < 6 else Decimal("1") if band < 9 else Decimal("0")
    return None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", type=Path, default=Path("var/pathlab.sqlite3"))
    parser.add_argument("--draft-id", default=DEFAULT_DRAFT_ID)
    parser.add_argument("--learners", type=int, default=100, help="Target submitted learner count for the stress fixture")
    args = parser.parse_args()
    if not 12 <= args.learners <= 500:
        raise SystemExit("--learners must be between 12 and 500")
    database_path = args.database.resolve()
    backup_dir = database_path.parent.parent / ".codex-backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    backup_path = backup_dir / f"pathlab-before-mixed-report-{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}.sqlite3"

    connection = sqlite3.connect(database_path)
    connection.row_factory = sqlite3.Row
    draft = connection.execute("SELECT * FROM assessment_drafts WHERE id = ?", (args.draft_id,)).fetchone()
    if draft is None:
        raise SystemExit(f"Draft {args.draft_id} was not found")
    version = connection.execute(
        "SELECT * FROM assessment_versions WHERE draft_id = ? ORDER BY version DESC LIMIT 1", (args.draft_id,)
    ).fetchone()
    administration = connection.execute(
        "SELECT * FROM assessment_administrations WHERE version_id = ? ORDER BY created_at DESC LIMIT 1", (version["id"],)
    ).fetchone()
    settings = _decode(administration["settings"])
    if settings.get("syntheticFixture") is not True:
        raise SystemExit("Refusing to modify a non-synthetic assessment administration")

    document = _decode(draft["document"])
    installed = any(item.get("id") == "q7" for item in document.get("items", []))

    backup_connection = sqlite3.connect(backup_path)
    connection.backup(backup_connection)
    backup_connection.close()

    if not installed:
        document["items"] = [*document.get("items", []), *DEMO_ITEMS]

    slide = connection.execute(
        "SELECT id FROM slides WHERE case_id = 'DEMO-THORAX-02' LIMIT 1"
    ).fetchone()
    if slide is None:
        raise SystemExit("The synthetic classroom WSI fixture is missing; run seed_classroom_demo.py first")
    for item in document["items"]:
        if item.get("id") == "q10":
            item["slideId"] = slide["id"]
            item["prompt"] = DEMO_ITEMS[3]["prompt"]

    compiled = compile_assessment(document)
    attempts = connection.execute(
        "SELECT id, participant_id FROM assessment_attempts WHERE administration_id = ? ORDER BY started_at, id", (administration["id"],)
    ).fetchall()
    if not attempts:
        raise SystemExit("Synthetic administration has no attempts")

    now = datetime.now(timezone.utc).replace(tzinfo=None).isoformat(sep=" ")
    with connection:
        connection.execute(
            "UPDATE assessment_drafts SET document = ?, revision = revision + 1, updated_at = ? WHERE id = ?",
            (_json(document), now, args.draft_id),
        )
        connection.execute(
            "UPDATE assessment_versions SET schema = ?, checksum = ?, definition = ?, learner_manifest = ? WHERE id = ?",
            ("pathlab.assessment/1", compiled.checksum, _json(compiled.definition), _json(compiled.learner_manifest), version["id"]),
        )
        if not installed:
            for index, attempt in enumerate(attempts):
                for item_id in ("q7", "q8", "q9", "q10", "q12"):
                    connection.execute(
                        "INSERT INTO assessment_responses (id, attempt_id, item_id, revision, response, updated_at) VALUES (?, ?, ?, 1, ?, ?)",
                        (str(uuid.uuid4()), attempt["id"], item_id, _json(_response_payload(item_id, index)), now),
                    )
                previous = connection.execute(
                    "SELECT * FROM assessment_score_versions WHERE attempt_id = ? ORDER BY version DESC LIMIT 1", (attempt["id"],)
                ).fetchone()
                breakdown = _decode(previous["breakdown"])
                added = Decimal("0")
                for item_id in ("q7", "q8", "q9", "q10", "q12"):
                    earned = _earned(item_id, index)
                    breakdown[item_id] = None if earned is None else str(earned)
                    if earned is not None:
                        added += earned
                score_id = str(uuid.uuid4())
                connection.execute(
                    "INSERT INTO assessment_score_versions (id, attempt_id, version, points, maximum_points, breakdown, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (score_id, attempt["id"], int(previous["version"]) + 1, str(Decimal(str(previous["points"])) + added), "15", _json(breakdown), now),
                )
                connection.execute(
                    "UPDATE assessment_gradebook_rows SET score_version_id = ?, status = 'needs_grading' WHERE administration_id = ? AND participant_id = ?",
                    (score_id, administration["id"], attempt["participant_id"]),
                )

        for attempt in attempts:
            latest_score = connection.execute(
                "SELECT id FROM assessment_score_versions WHERE attempt_id = ? ORDER BY version DESC LIMIT 1",
                (attempt["id"],),
            ).fetchone()
            connection.execute(
                "UPDATE assessment_gradebook_rows SET score_version_id = ?, status = 'needs_grading' WHERE administration_id = ? AND participant_id = ?",
                (latest_score["id"], administration["id"], attempt["participant_id"]),
            )

        current_count = len(attempts)
        for index in range(current_count, args.learners):
            token = f"pathlab-report-stress-{index + 1:03d}"
            learner_id = str(uuid.uuid5(uuid.NAMESPACE_URL, token + ":learner"))
            participant_id = str(uuid.uuid5(uuid.NAMESPACE_URL, token + ":participant"))
            attempt_id = str(uuid.uuid5(uuid.NAMESPACE_URL, token + ":attempt"))
            score_id = str(uuid.uuid5(uuid.NAMESPACE_URL, token + ":score"))
            first_name = FIRST_NAMES[index % len(FIRST_NAMES)]
            last_name = LAST_NAMES[(index * 7) % len(LAST_NAMES)]
            display_name = f"{first_name} {last_name}"
            student_id = f"88{index + 1:05d}"
            login_hash = hashlib.sha256(token.encode()).hexdigest()
            connection.execute(
                "INSERT INTO learner_profiles (id, organization_id, teaching_pseudonym, status, schema_version, login_identifier_hash, student_id, first_name, last_name, display_name, group_name, subgroup_name, email, roster_metadata, created_at, updated_at) VALUES (?, ?, ?, 'active', 1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (learner_id, administration["organization_id"], token, login_hash, student_id, first_name, last_name, display_name, f"Year {2 + index % 3}", f"Lab {chr(65 + index % 5)}", f"{first_name.lower()}.{last_name.lower()}{index + 1}@example.edu", _json({"campus": "Main campus" if index % 3 else "Clinical campus", "advisor": f"Dr. {LAST_NAMES[index % len(LAST_NAMES)]}"}), now, now),
            )
            connection.execute(
                "INSERT INTO assessment_roster_snapshots (id, administration_id, learner_id, login_identifier_hash, display_name, status) VALUES (?, ?, ?, ?, ?, 'active')",
                (str(uuid.uuid5(uuid.NAMESPACE_URL, token + ":snapshot")), administration["id"], learner_id, login_hash, display_name),
            )
            connection.execute(
                "INSERT INTO assessment_participants (id, administration_id, learner_id, kind, receipt_hash, created_at) VALUES (?, ?, ?, 'roster', NULL, ?)",
                (participant_id, administration["id"], learner_id, now),
            )
            connection.execute(
                "INSERT INTO assessment_attempts (id, administration_id, participant_id, ordinal, status, order_seed, started_at, submitted_at) VALUES (?, ?, ?, 1, 'submitted', ?, ?, ?)",
                (attempt_id, administration["id"], participant_id, hashlib.sha256((token + ':order').encode()).hexdigest(), now, now),
            )
            breakdown: dict[str, str | None] = {}
            earned_total = Decimal("0")
            for item in document["items"]:
                item_id = item["id"]
                if item.get("type") != "information":
                    connection.execute(
                        "INSERT INTO assessment_responses (id, attempt_id, item_id, revision, response, updated_at) VALUES (?, ?, ?, 1, ?, ?)",
                        (str(uuid.uuid5(uuid.NAMESPACE_URL, token + f":response:{item_id}")), attempt_id, item_id, _json(_base_response(item_id, index)), now),
                    )
                earned = _base_earned(item_id, index)
                breakdown[item_id] = None if earned is None else str(earned)
                if earned is not None:
                    earned_total += earned
            connection.execute(
                "INSERT INTO assessment_score_versions (id, attempt_id, version, points, maximum_points, breakdown, created_at) VALUES (?, ?, 1, ?, '15', ?, ?)",
                (score_id, attempt_id, str(earned_total), _json(breakdown), now),
            )
            connection.execute(
                "INSERT INTO assessment_gradebook_rows (id, administration_id, participant_id, score_version_id, status) VALUES (?, ?, ?, ?, 'needs_grading')",
                (str(uuid.uuid5(uuid.NAMESPACE_URL, token + ":gradebook")), administration["id"], participant_id, score_id),
            )
        connection.execute(
            "DELETE FROM assessment_aggregate_snapshots WHERE administration_id = ?", (administration["id"],)
        )

    final_count = connection.execute(
        "SELECT COUNT(*) FROM assessment_attempts WHERE administration_id = ?", (administration["id"],)
    ).fetchone()[0]
    response_count = connection.execute(
        "SELECT COUNT(*) FROM assessment_responses r JOIN assessment_attempts a ON a.id = r.attempt_id WHERE a.administration_id = ?",
        (administration["id"],),
    ).fetchone()[0]
    print(f"Stress fixture ready: {final_count} submitted learners and {response_count} item responses.")
    print(f"WSI sample slide: {slide['id']} (synthetic H&E teaching fixture; not patient data).")
    print(f"Backup: {backup_path}")
    print(f"Draft: {args.draft_id}; administration: {administration['id']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
