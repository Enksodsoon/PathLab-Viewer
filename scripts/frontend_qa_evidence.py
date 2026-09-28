"""Build an honest local QA ledger from explicit Playwright JSON receipts.

Source candidates are discovery aids, never counted as passed controls. Browser
test results prove only their asserted scenarios, not every state of a widget.
"""

import argparse
import base64
import csv
import hashlib
import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def cases(suite, parents=()):
    lineage = (*parents, suite.get("title", ""))
    for spec in suite.get("specs", []):
        for test in spec.get("tests", []):
            yield spec, test, lineage
    for child in suite.get("suites", []):
        yield from cases(child, lineage)


def write_csv(destination, rows, fields):
    with destination.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--mocked", type=Path, action="append", default=[])
    parser.add_argument("--fullstack", type=Path, action="append", default=[])
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    ledger = []
    receipts = []
    runtime_controls = []
    for kind, paths in (("mocked UI", args.mocked), ("real isolated backend", args.fullstack)):
        for source in paths:
            report = json.loads(source.read_text(encoding="utf-8-sig"))
            receipts.append(
                {
                    "path": str(source.resolve()),
                    "kind": kind,
                    "sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
                    "stats": report.get("stats"),
                }
            )
            for suite in report.get("suites", []):
                for spec, test, _ in cases(suite):
                    results = test.get("results", [])
                    status = results[-1].get("status", "not-run") if results else "not-run"
                    ledger.append(
                        {
                            "surface": spec.get("file", suite.get("file", "")),
                            "scenario_and_preconditions": spec["title"],
                            "control_action_expected_and_persistence": "See source assertions",
                            "source_line": spec.get("line", ""),
                            "device_browser": test.get("projectName", ""),
                            "evidence_kind": kind,
                            "status": status,
                            "evidence": str(source.resolve()),
                            "duration_ms": results[-1].get("duration", "") if results else "",
                            "limitation": "Scenario only; skipped/not-run is not passed",
                        }
                    )
                    for attachment in results[-1].get("attachments", []) if results else []:
                        if attachment.get("name") != "reachable-controls.json":
                            continue
                        raw = (
                            base64.b64decode(attachment["body"])
                            if attachment.get("body")
                            else Path(attachment["path"]).read_bytes()
                        )
                        for control in json.loads(raw):
                            runtime_controls.append(
                                {
                                    "route": control["route"],
                                    "control": control["label"],
                                    "element": control.get("tag", ""),
                                    "action": control["event"],
                                    "disabled": control.get("disabled", False),
                                    "expanded": control.get("expanded"),
                                    "scenario": spec["title"],
                                    "scenario_status": status,
                                    "device_browser": test.get("projectName", ""),
                                    "evidence": str(source.resolve()),
                                    "control_state_status": "ENCOUNTERED_ONLY"
                                    if control["event"] == "encountered"
                                    else "EXERCISED_IN_SCENARIO",
                                    "limitation": (
                                        "Use scenario assertions for expected and durable results; "
                                        "an event alone is not a pass"
                                    ),
                                }
                            )
    write_csv(args.output / "scenario-ledger.csv", ledger, list(ledger[0]) if ledger else [])
    write_csv(
        args.output / "runtime-controls.csv",
        runtime_controls,
        list(runtime_controls[0]) if runtime_controls else [],
    )

    candidates = []
    for source in sorted((ROOT / "apps/web/src").rglob("*.tsx")):
        content = source.read_text(encoding="utf-8")
        pattern = r"<(button|input|select|textarea|a|summary)\b([^>]*?)>"
        for match in re.finditer(pattern, content, re.S):
            label = re.search(r'aria-label="([^"]+)"', match[2])
            candidates.append(
                {
                    "source": source.relative_to(ROOT).as_posix(),
                    "line": content[: match.start()].count("\n") + 1,
                    "element": match[1],
                    "literal_aria_label": label[1] if label else "See source / associated label",
                    "status": "REQUIRES_REACHABILITY_AND_STATE_MAPPING",
                    "limitation": "May be gated, nested, or unused; not a pass claim",
                }
            )
    write_csv(args.output / "control-candidates.csv", candidates, list(candidates[0]))
    changed_paths = subprocess.check_output(
        ["git", "ls-files", "--modified", "--others", "--exclude-standard"], cwd=ROOT, text=True
    ).splitlines()
    file_hashes = {
        name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
        for name in changed_paths
        if (ROOT / name).is_file()
    }
    manifest = {
        "base_commit": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip(),
        "working_diff_sha256": hashlib.sha256(
            subprocess.check_output(["git", "diff", "HEAD"], cwd=ROOT)
        ).hexdigest(),
        "receipts": receipts,
        "changed_file_sha256": file_hashes,
        "scenario_rows": len(ledger),
        "static_control_candidates": len(candidates),
        "runtime_control_observations": len(runtime_controls),
        "complete_control_state_coverage": False,
        "note": "Retain untracked tests; commit before release qualification.",
    }
    (args.output / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(
        json.dumps(
            {
                "scenarioRows": len(ledger),
                "staticCandidates": len(candidates),
                "completeCoverage": False,
            }
        )
    )


if __name__ == "__main__":
    main()
