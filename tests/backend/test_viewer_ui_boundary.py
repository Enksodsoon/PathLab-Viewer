from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from scripts.validate_viewer_ui_boundary import DEFAULT_POLICY, validate


def make_repo(tmp_path: Path) -> tuple[Path, Path]:
    policy = json.loads(DEFAULT_POLICY.read_text(encoding="utf-8"))
    for relative in policy["releaseReferenceFiles"]:
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("", encoding="utf-8")
    (tmp_path / "apps/web/src/components/library/AppRail.tsx").write_text(
        "from '../Brand'\nfrom '@phosphor-icons/react'\nrole=\"meter\"\n",
        encoding="utf-8",
    )
    policy_path = tmp_path / "policy.json"
    policy_path.write_text(json.dumps(policy), encoding="utf-8")
    return tmp_path, policy_path


def test_current_boundary_is_clean() -> None:
    policy = validate()
    assert len(policy["retiredFiles"]) == 9


def test_retired_path_is_rejected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root, policy_path = make_repo(tmp_path)
    retired = json.loads(policy_path.read_text())["retiredFiles"][0]
    path = root / retired["path"]
    path.parent.mkdir(parents=True)
    path.write_text("different content", encoding="utf-8")
    monkeypatch.setattr("scripts.validate_viewer_ui_boundary.tracked_files", lambda _root: [])
    with pytest.raises(ValueError, match="retired package path returned"):
        validate(root, policy_path)


def test_retired_content_under_new_name_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, policy_path = make_repo(tmp_path)
    policy = json.loads(policy_path.read_text())
    copied = root / "copied.tsx"
    copied.write_bytes(b"retired bytes")
    policy["retiredFiles"][0]["contentSha256"] = hashlib.sha256(copied.read_bytes()).hexdigest()
    policy_path.write_text(json.dumps(policy), encoding="utf-8")
    monkeypatch.setattr(
        "scripts.validate_viewer_ui_boundary.tracked_files", lambda _root: [copied]
    )
    with pytest.raises(ValueError, match="retired package content returned"):
        validate(root, policy_path)


def test_release_reference_is_rejected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root, policy_path = make_repo(tmp_path)
    (root / "apps/web/package.json").write_text(
        "@pathlab/viewer-ui", encoding="utf-8"
    )
    monkeypatch.setattr("scripts.validate_viewer_ui_boundary.tracked_files", lambda _root: [])
    with pytest.raises(ValueError, match="retired package reference"):
        validate(root, policy_path)
