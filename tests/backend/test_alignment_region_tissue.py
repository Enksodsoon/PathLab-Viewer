from pathlib import Path

import numpy as np
import pytest
from PIL import Image, ImageDraw
from wsi_viewer.alignment import AlignmentRejected, map_registration_point
from wsi_viewer.alignment_regions import (
    RegionRejected,
    _polygon_supported,
    _tissue,
    build_region_registration,
)


def _pyramid(root: Path, name: str, image: Image.Image) -> Path:
    path = root / name
    tiles = path / "slide_files" / "8"
    tiles.mkdir(parents=True)
    (path / "slide.dzi").write_text(
        '<Image TileSize="256" Overlap="0" Format="png" '
        'xmlns="http://schemas.microsoft.com/deepzoom/2008">'
        '<Size Width="256" Height="256"/></Image>'
    )
    image.save(tiles / "0_0.png")
    return path


def _image(kind: str) -> Image.Image:
    image = Image.new("RGB", (256, 256), "white")
    draw = ImageDraw.Draw(image)
    if kind == "thin":
        draw.rectangle((125, 32, 130, 224), fill=(231, 221, 229))
    elif kind == "fragments":
        draw.rectangle((32, 32, 123, 224), fill=(231, 221, 229))
        draw.rectangle((132, 32, 224, 224), fill=(231, 221, 229))
    elif kind != "glass":
        color = (230, 230, 230) if kind == "achromatic" else (231, 221, 229)
        draw.rectangle((32, 32, 224, 224), fill=color)
        if kind == "lumen":
            draw.rectangle((124, 124, 131, 131), fill="white")
        elif kind == "large-hole":
            draw.rectangle((108, 108, 148, 148), fill="white")
    return image


def _registration(tmp_path: Path, source: str, target: str, point=(128, 128), points=None):
    metadata = {"width": 256, "height": 256}
    return build_region_registration(
        source_metadata=metadata,
        target_metadata=metadata,
        source_bounds=[0, 0, 255, 255],
        moving_points=points or [point],
        reference_points=points or [point],
        source_path=_pyramid(tmp_path, "source", _image(source)),
        target_path=_pyramid(tmp_path, "target", _image(target)),
        source_version="source-snapshot",
        target_version="target-snapshot",
        target_slide_id="target",
    )


@pytest.mark.parametrize("kind", ["faint", "achromatic", "lumen", "thin"])
def test_faint_tissue_small_internal_lumen_and_thin_fragment_are_usable(tmp_path, kind):
    registration = _registration(tmp_path, kind, kind)
    assert map_registration_point(registration, 128, 128) == pytest.approx((128, 128))
    assert map_registration_point(registration, 128, 128, inverse=True) == pytest.approx((128, 128))
    assert registration["status"] == "approximate"
    assert registration["evidence"]["anatomicallyQualified"] is False
    assert len(registration["triangles"]) <= 2048
    assert registration["evidence"]["supportCellVisits"] <= 8192
    for point in ((5, 128), (250, 128), (128, 5), (128, 250)):
        with pytest.raises(AlignmentRejected):
            map_registration_point(registration, *point)
        with pytest.raises(AlignmentRejected):
            map_registration_point(registration, *point, inverse=True)


@pytest.mark.parametrize("side", ["source", "target"])
@pytest.mark.parametrize("kind", ["glass", "fragments", "large-hole"])
def test_glass_fragment_gaps_and_large_holes_on_either_side_reject_landmark(tmp_path, side, kind):
    kinds = {"source": "faint", "target": "faint", side: kind}
    with pytest.raises(RegionRejected, match="REGION_SUPPORT_UNAVAILABLE|LANDMARK_ON_GLASS"):
        _registration(tmp_path, **kinds)


@pytest.mark.parametrize("side", ["source", "target"])
def test_supported_region_does_not_include_unmatched_glass_or_other_fragments(tmp_path, side):
    kinds = {"source": "faint", "target": "faint", side: "fragments"}
    registration = _registration(tmp_path, **kinds, point=(80, 128))
    assert map_registration_point(registration, 80, 128) == pytest.approx((80, 128))
    for inverse in (False, True):
        with pytest.raises(AlignmentRejected):
            map_registration_point(registration, 128, 128, inverse=inverse)


def test_fractional_cell_rounded_past_last_raster_sample_is_unsupported():
    points = np.asarray([[511.6, 511.6], [511.9, 511.6], [511.9, 511.9], [511.6, 511.9]])
    assert not _polygon_supported(points, np.ones((512, 512), dtype=np.uint8), (0, 0, 1))


def test_two_separated_landmarks_on_thin_fragment_both_have_forward_inverse_support(tmp_path):
    points = [(128, 60), (128, 196)]
    registration = _registration(tmp_path, "thin", "thin", points=points)
    for point in points:
        for inverse in (False, True):
            assert map_registration_point(registration, *point, inverse=inverse) == pytest.approx(
                point
            )


def test_downsampled_small_decoded_hole_does_not_fill_large_original_cavity(tmp_path):
    # Real DZI selection: 2048 original pixels at level 9 become 512 pixels.
    path = tmp_path / "large"
    tiles = path / "slide_files" / "9"
    tiles.mkdir(parents=True)
    (path / "slide.dzi").write_text(
        '<Image TileSize="512" Overlap="0" Format="png" '
        'xmlns="http://schemas.microsoft.com/deepzoom/2008">'
        '<Size Width="2048" Height="2048"/></Image>'
    )
    image = Image.new("RGB", (512, 512), (231, 221, 229))
    ImageDraw.Draw(image).rectangle((252, 252, 259, 259), fill="white")
    ImageDraw.Draw(image).rectangle((100, 100, 101, 101), fill="white")
    image.save(tiles / "0_0.png")
    mask, frame = _tissue(path, (0, 0, 2048, 2048))
    assert frame == (0, 0, 4)
    assert mask[256, 256] == 0  # 8 decoded pixels span 32 original pixels.
    assert mask[100, 100] == 1  # An enclosed 8-original-pixel lumen stays supported.
    assert mask[240, 240] == 1
