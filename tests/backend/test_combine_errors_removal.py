from __future__ import annotations

from pathlib import Path

import pytest

from scripts.validate_combine_errors_removal import (
    DEFAULT_INVENTORY,
    DEFAULT_LOCK,
    DEFAULT_PATCH,
    DEFAULT_WEB_DOCKERFILE,
    DEFAULT_WORKSPACE,
    validate,
)


def test_current_graph_and_inventory_exclude_combine_errors() -> None:
    inventory = validate()
    assert all(record["name"] != "combine-errors" for record in inventory["records"])


def test_resolved_combine_errors_is_rejected(tmp_path: Path) -> None:
    lock = tmp_path / "pnpm-lock.yaml"
    lock.write_text(DEFAULT_LOCK.read_text() + "\n# combine-errors\n", encoding="utf-8")
    with pytest.raises(ValueError, match="resolved pnpm graph"):
        validate(lock, DEFAULT_WORKSPACE, DEFAULT_INVENTORY, DEFAULT_PATCH)


def test_tampered_patch_is_rejected(tmp_path: Path) -> None:
    patch = tmp_path / "tus.patch"
    patch.write_bytes(DEFAULT_PATCH.read_bytes() + b"\n# tampered\n")
    with pytest.raises(ValueError, match="exact tus-js-client patch hash"):
        validate(DEFAULT_LOCK, DEFAULT_WORKSPACE, DEFAULT_INVENTORY, patch)


def test_windows_checkout_line_endings_preserve_patch_identity(tmp_path: Path) -> None:
    patch = tmp_path / "tus.patch"
    patch.write_text(
        DEFAULT_PATCH.read_text(encoding="utf-8").replace("\n", "\r\n"),
        encoding="utf-8",
        newline="",
    )
    validate(DEFAULT_LOCK, DEFAULT_WORKSPACE, DEFAULT_INVENTORY, patch)


def test_web_image_without_patch_input_is_rejected(tmp_path: Path) -> None:
    dockerfile = tmp_path / "Dockerfile.web"
    dockerfile.write_text(
        DEFAULT_WEB_DOCKERFILE.read_text().replace("COPY patches ./patches\n", ""),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="web image does not copy"):
        validate(
            DEFAULT_LOCK,
            DEFAULT_WORKSPACE,
            DEFAULT_INVENTORY,
            DEFAULT_PATCH,
            dockerfile,
        )
