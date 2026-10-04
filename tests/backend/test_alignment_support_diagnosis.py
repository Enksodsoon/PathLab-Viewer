"""Saved-transform diagnostics must distinguish tissue holes and mask projection."""

import importlib.util
from pathlib import Path

import numpy as np
import pytest


@pytest.fixture
def diagnosis():
    path = Path(__file__).resolve().parents[2] / "scripts" / "diagnose_alignment_support.py"
    spec = importlib.util.spec_from_file_location("support_diagnosis", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_enclosed_background_is_separate_from_external_glass(diagnosis):
    mask = np.zeros((40, 40), np.uint8)
    mask[5:35, 5:35] = 255
    mask[15:25, 15:25] = 0
    assert diagnosis.point_kind(mask, [20, 20]) == "enclosed-background-mask-hole"
    assert diagnosis.point_kind(mask, [0, 0]) == "external-background"
    assert diagnosis.point_kind(mask, [10, 10]) == "tissue"
    assert diagnosis.point_kind(mask, [40, 40]) == "outside-frame"


def test_fixed_affine_grid_separates_support_filtering_and_anisotropic_bug(diagnosis):
    mask = np.zeros((256, 512), np.uint8)
    mask[70:190, 40:470] = 255
    raw, scalar, axis = diagnosis.fixed_grid_meshes(
        mask, mask, [[1, 0, 0], [0, 1, 0]], [4096, 4096], [4096, 4096]
    )
    assert len(raw) > len(scalar)
    assert len(axis) > len(scalar)
    assert diagnosis.covers(raw, [2000, 2500])
    assert diagnosis.covers(axis, [2000, 2500])
    assert not diagnosis.covers(scalar, [2000, 2500])
    assert not diagnosis.covers(raw, [0, 0])
