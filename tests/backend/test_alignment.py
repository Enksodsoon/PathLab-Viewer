from __future__ import annotations

import numpy as np
import pytest
from PIL import Image, ImageDraw, ImageEnhance
from wsi_viewer.alignment import (
    AlignmentRejected,
    RegistrationResult,
    compose_transforms,
    map_bounds,
    map_point,
    register_pair,
    rescale_registration,
)


def _tissue(seed: int = 7) -> Image.Image:
    rng = np.random.default_rng(seed)
    image = Image.new("RGB", (720, 520), "white")
    draw = ImageDraw.Draw(image)
    draw.ellipse((80, 70, 620, 440), fill=(224, 162, 188), outline=(92, 44, 100), width=8)
    draw.rectangle((250, 140, 510, 350), fill=(238, 190, 208), outline=(70, 55, 105), width=6)
    for _ in range(90):
        x = int(rng.integers(115, 590))
        y = int(rng.integers(100, 415))
        radius = int(rng.integers(3, 10))
        draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=(70, 48, 116))
    return image


def _affine_variant(reference: Image.Image) -> Image.Image:
    moved = reference.rotate(8, resample=Image.Resampling.BICUBIC, expand=False, fillcolor="white")
    translated = Image.new("RGB", reference.size, "white")
    translated.paste(moved, (24, -17))
    # Simulate a stain change without changing structure.
    red, green, blue = translated.split()
    return Image.merge("RGB", (ImageEnhance.Contrast(blue).enhance(1.2), red, green))


def test_register_pair_maps_corresponding_structure_across_stains() -> None:
    reference = _tissue()
    moving = _affine_variant(reference)

    result = register_pair(reference, moving, max_dimension=900)
    mapped = map_point(result.moving_to_reference, 384.0, 243.0)

    assert result.status == "ready"
    assert result.inlier_count >= 8
    assert result.confidence >= 0.55
    assert mapped[0] == pytest.approx(360.0, abs=12.0)
    assert mapped[1] == pytest.approx(260.0, abs=12.0)
    assert result.reference_support[0] < result.reference_support[2]
    assert result.moving_support[1] < result.moving_support[3]


def test_register_pair_rejects_blank_slide() -> None:
    with pytest.raises(AlignmentRejected, match="insufficient tissue"):
        register_pair(_tissue(), Image.new("RGB", (720, 520), "white"))


def test_register_pair_rejects_unrelated_tissue() -> None:
    unrelated = Image.new("RGB", (720, 520), "white")
    draw = ImageDraw.Draw(unrelated)
    for x in range(30, 690, 45):
        draw.line((x, 30, 720 - x // 2, 490), fill=(35, 85, 60), width=4)

    with pytest.raises(AlignmentRejected, match="reliable correspondence"):
        register_pair(_tissue(), unrelated)


def test_register_pair_matches_separate_fragments_and_ignores_slide_edge() -> None:
    reference = Image.new("RGB", (800, 600), "white")
    draw = ImageDraw.Draw(reference)
    draw.rounded_rectangle((90, 110, 260, 470), radius=35, fill=(224, 168, 194))
    draw.polygon([(500, 90), (650, 135), (610, 500), (470, 450)], fill=(218, 156, 188))
    draw.ellipse((340, 420, 410, 500), fill=(210, 145, 180))
    moving = reference.rotate(24, resample=Image.Resampling.BICUBIC, fillcolor="white")
    moving_array = np.asarray(moving).copy()
    tissue = np.min(moving_array, axis=2) < 245
    moving_array[tissue] = (95, 82, 105)
    moving = Image.fromarray(moving_array)
    artifact = ImageDraw.Draw(moving)
    artifact.rectangle((0, 580, 799, 599), fill=(185, 185, 185))

    result = register_pair(reference, moving, max_dimension=900)

    assert result.status == "ready"
    assert result.confidence >= 0.55
    assert result.reference_support[1] < 120
    assert result.reference_support[3] < 520


def test_rescale_registration_converts_thumbnail_map_to_full_slide_coordinates() -> None:
    thumbnail = RegistrationResult(
        status="ready",
        moving_to_reference=[[1, 0, -10], [0, 1, -5]],
        reference_support=(5, 4, 95, 76),
        moving_support=(2, 3, 98, 78),
        confidence=0.9,
        inlier_count=20,
        match_count=25,
        median_error_pixels=2,
        control_points=[{"moving": [20, 30], "reference": [15, 25], "errorPixels": 2}],
    )

    full = rescale_registration(
        thumbnail,
        reference_thumbnail_size=(100, 80),
        moving_thumbnail_size=(100, 80),
        reference_full_size=(1000, 800),
        moving_full_size=(2000, 1600),
    )

    assert full.moving_to_reference == [[0.5, 0.0, -100.0], [0.0, 0.5, -50.0]]
    assert full.reference_support == (50.0, 40.0, 950.0, 760.0)
    assert full.moving_support == (40.0, 60.0, 1960.0, 1560.0)
    assert full.median_error_pixels == 20.0
    assert full.control_points == [
        {"moving": [400.0, 600.0], "reference": [150.0, 250.0], "errorPixels": 20.0}
    ]


def test_map_point_rejects_invalid_transform() -> None:
    with pytest.raises(ValueError, match="2x3"):
        map_point([[1.0, 0.0], [0.0, 1.0]], 1.0, 2.0)


def test_composes_secondary_reference_coordinates() -> None:
    moving_to_anchor = [[1.0, 0.0, 10.0], [0.0, 1.0, -5.0]]
    anchor_to_reference = [[0.0, -2.0, 100.0], [2.0, 0.0, 20.0]]

    composed = compose_transforms(anchor_to_reference, moving_to_anchor)

    assert map_point(composed, 4.0, 7.0) == pytest.approx(
        map_point(anchor_to_reference, *map_point(moving_to_anchor, 4.0, 7.0))
    )
    assert map_bounds(anchor_to_reference, (0.0, 0.0, 10.0, 20.0)) == (
        60.0,
        20.0,
        100.0,
        40.0,
    )
