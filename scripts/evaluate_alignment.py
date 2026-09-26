from __future__ import annotations

import argparse
import json
from pathlib import Path

from wsi_viewer.alignment_evaluation import evaluate_landmarks


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate annotated slide-alignment landmarks")
    parser.add_argument(
        "manifest", type=Path, help="Private JSON file containing a landmarks array"
    )
    parser.add_argument("--output", type=Path, help="Optional aggregate JSON output path")
    args = parser.parse_args()
    payload = json.loads(args.manifest.read_text(encoding="utf-8"))
    report = evaluate_landmarks(payload["landmarks"])
    rendered = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")
    return 0 if report["qualified"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
