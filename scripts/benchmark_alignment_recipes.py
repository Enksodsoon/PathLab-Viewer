"""Run a private explicit pair manifest through the bounded registration supervisor."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from wsi_viewer.alignment_benchmark import run_benchmark


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument(
        "--recipes",
        default="native,valis,wsireg,hisalign,deeperhistreg-classical,deeperhistreg-learned,native-wsireg,valis-rigid-wsireg,native-valis",
    )
    parser.add_argument("--screening", action="store_true")
    parser.add_argument("--no-resume", action="store_true")
    parser.add_argument(
        "--repeat-runs",
        type=int,
        default=0,
        help="Additional fresh child runs; host filesystem cache may be warm",
    )
    parser.add_argument("--timeout-seconds", type=int, default=600)
    parser.add_argument("--memory-gib", type=float, default=7)
    parser.add_argument("--reset-immutable-regional-cache", action="store_true")
    parser.add_argument("--immutable-input-root", type=Path)
    args = parser.parse_args()
    report = run_benchmark(
        json.loads(args.manifest.read_text(encoding="utf-8")),
        args.output_dir,
        args.recipes.split(","),
        screening=args.screening,
        resume=not args.no_resume,
        timeout_seconds=args.timeout_seconds,
        memory_bytes=int(args.memory_gib * 1024**3),
        repeat_runs=args.repeat_runs,
        reset_immutable_regional_cache=args.reset_immutable_regional_cache,
        immutable_input_root=args.immutable_input_root,
    )
    print(json.dumps({"winners": report["winners"], "finalists": report["finalists"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
