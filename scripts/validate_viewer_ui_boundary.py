from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_POLICY = ROOT / "docs" / "supply-chain" / "viewer-ui-clean-room-policy.json"


def tracked_files(root: Path) -> list[Path]:
    output = subprocess.check_output(
        ["git", "ls-files", "-z"], cwd=root, text=False
    )
    return [root / item.decode() for item in output.split(b"\0") if item]


def validate(root: Path = ROOT, policy_path: Path = DEFAULT_POLICY) -> dict[str, Any]:
    policy = json.loads(policy_path.read_text(encoding="utf-8"))
    retired = policy["retiredFiles"]
    if len(retired) != 9 or len({item["path"] for item in retired}) != 9:
        raise ValueError("policy must bind exactly nine unique retired package files")

    tracked = tracked_files(root)
    retired_hashes = {item["contentSha256"] for item in retired}
    for item in retired:
        if (root / item["path"]).exists():
            raise ValueError(f"retired package path returned: {item['path']}")
    for path in tracked:
        if not path.is_file():
            continue
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest in retired_hashes:
            relative = path.relative_to(root).as_posix()
            raise ValueError(f"retired package content returned: {relative}")

    for relative in policy["releaseReferenceFiles"]:
        text = (root / relative).read_text(encoding="utf-8")
        for token in policy["forbiddenReleaseTokens"]:
            if token in text:
                raise ValueError(f"retired package reference in {relative}: {token}")

    app_rail = (root / "apps/web/src/components/library/AppRail.tsx").read_text(
        encoding="utf-8"
    )
    for required in ("from '../Brand'", "from '@phosphor-icons/react'", 'role="meter"'):
        if required not in app_rail:
            raise ValueError(f"clean-room AppRail contract missing: {required}")
    return policy


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--policy", type=Path, default=DEFAULT_POLICY)
    args = parser.parse_args()
    try:
        policy = validate(policy_path=args.policy)
    except (OSError, ValueError, json.JSONDecodeError, subprocess.CalledProcessError) as exc:
        print(f"viewer-ui boundary FAIL: {exc}")
        return 1
    print(f"viewer-ui boundary PASS: {len(policy['retiredFiles'])} retired files absent")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
